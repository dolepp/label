(() => {
  const $=id=>document.getElementById(id),base=(document.querySelector('meta[name="twas-api-base"]')?.content||location.origin).replace(/\/$/,'');
  const slug=location.pathname.startsWith('/l/')?location.pathname.split('/')[2]:new URLSearchParams(location.search).get('slug');
  if(!slug||!/^[a-z0-9][a-z0-9_-]{2,79}$/.test(slug)){$('smartlinkTitle').textContent='Ссылка не найдена';$('smartlinkCaption').textContent='Проверьте адрес релиза.';return;}
  if(location.pathname.startsWith('/listen/'))history.replaceState(null,'','/l/'+slug);
  fetch(`${base}/api/smartlinks/${encodeURIComponent(slug)}`,{credentials:'omit'}).then(async response=>{const data=await response.json();if(!response.ok||!data.success)throw new Error(data.error||'Не удалось открыть релиз');return data;}).then(data=>{
    $('smartlinkTitle').textContent=data.release.title;$('smartlinkArtist').textContent=data.release.artist;document.title=`${data.release.artist} — ${data.release.title} · TWAS Label`;
    const cover=$('smartlinkCover');cover.src=base+data.release.cover_url;cover.onload=()=>{cover.classList.remove('hidden');$('smartlinkNoCover').classList.add('hidden');};cover.onerror=()=>cover.classList.add('hidden');
    const icons={yandex:'Я',vk:'VK',apple:'♫',spotify:'S',zvuk:'З',deezer:'D',youtube:'▶',amazon:'a',mts:'М'};
    for(const item of data.links){const link=document.createElement('a');link.className='smartlink-button';link.dataset.platform=item.key;link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
      const icon=document.createElement('span');icon.className='smartlink-platform-icon';icon.textContent=icons[item.key]||'♫';const title=document.createElement('b');title.textContent=item.label;const action=document.createElement('span');action.textContent='Слушать ↗';link.append(icon,title,action);
      link.onclick=()=>window.TwasAnalytics?.track('platform_click',{context:'smartlink',platform:item.key,release_id:data.release.id});$('smartlinkButtons').append(link);}
    $('smartlinkShare').classList.remove('hidden');$('smartlinkShare').onclick=async()=>{const url=location.origin+'/l/'+slug;try{if(navigator.share)await navigator.share({title:document.title,url});else{await navigator.clipboard.writeText(url);$('smartlinkShare').textContent='Ссылка скопирована';}}catch(error){if(error.name!=='AbortError')$('smartlinkError').textContent='Скопируйте адрес из строки браузера.';}};
  }).catch(error=>{$('smartlinkTitle').textContent='Релиз недоступен';$('smartlinkCaption').textContent='';$('smartlinkError').textContent=error.message;});
})();
