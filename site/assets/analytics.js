(() => {
  "use strict";
  const VERSION="2026-10-07",KEY="twas_tracking_consent";
  const apiBase=(document.querySelector('meta[name="twas-api-base"]')?.content.trim()||location.origin).replace(/\/$/,"");
  let consent={analytics:false,ads:false},configured={},started=new Set(),settingsDialog=null;
  const eventNames=new Set(['page_view','auth_success','release_submitted','checkout_started','payment_success','tool_open','ttml_completed','ttml_download','ttml_attached','video_exported','smartlink_created','platform_click']);
  const contexts=new Set(['','home','services','tools','profile','releases','promos','teleprompter','ttml','smartlink','legal','lyrics_video']);
  let known=false,ready=false;
  try{const saved=JSON.parse(localStorage.getItem(KEY)||'null');if(saved?.version===VERSION){consent={analytics:saved.analytics===true,ads:saved.ads===true};known=true;}}catch(_){}
  window.TwasConsentManager=true;
  function safeReferrer(){try{return document.referrer?new URL(document.referrer).origin:'';}catch(_){return '';}}
  function cleanLocation(){return location.origin+(location.pathname.startsWith('/l/')?location.pathname:location.pathname.startsWith('/legal/')||location.pathname.startsWith('/lyrics-video/')?location.pathname:'/'+(contexts.has(location.hash.slice(1))?location.hash:''));}
  function safeToLoad(){return !/tgWebAppData|access_token|id_token|code=|password=/i.test(location.search+location.hash);}
  function script(src){const node=document.createElement('script');node.async=true;node.src=src;node.dataset.twasTracker='1';document.head.append(node);}
  function initialize(){
    if(!safeToLoad())return;
    if(consent.analytics&&configured.yandex_id&&!started.has('yandex')){
      window.ym=window.ym||function(){(window.ym.a=window.ym.a||[]).push(arguments);};window.ym.l=Date.now();
      window.ym(Number(configured.yandex_id),'init',{defer:true,webvisor:false,clickmap:false,trackLinks:false,accurateTrackBounce:true,url:cleanLocation(),referrer:safeReferrer()});
      script('https://mc.yandex.ru/metrika/tag.js');started.add('yandex');
    }
    if(consent.analytics&&configured.google_id&&!started.has('google')){
      window.dataLayer=window.dataLayer||[];window.gtag=window.gtag||function(){window.dataLayer.push(arguments);};
      window.gtag('consent','default',{analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});
      window.gtag('consent','update',{analytics_storage:'granted'});window.gtag('js',new Date());
      window.gtag('config',configured.google_id,{send_page_view:false,allow_google_signals:false,allow_ad_personalization_signals:false,page_location:cleanLocation(),page_referrer:safeReferrer()});
      script('https://www.googletagmanager.com/gtag/js?id='+configured.google_id);started.add('google');
    }
    if(consent.ads&&configured.meta_id&&!started.has('meta')){
      if(!window.fbq){const queue=function(){queue.callMethod?queue.callMethod.apply(queue,arguments):queue.queue.push(arguments);};queue.push=queue;queue.loaded=true;queue.version='2.0';queue.queue=[];window.fbq=queue;window._fbq=queue;}
      window.fbq('consent','grant');window.fbq('set','autoConfig',false,configured.meta_id);window.fbq('init',configured.meta_id);
      script('https://connect.facebook.net/en_US/fbevents.js');started.add('meta');
    }
    if(consent.ads&&configured.vk_id&&!started.has('vk')){window._tmr=window._tmr||[];script('https://top-fwz1.mail.ru/js/code.js');started.add('vk');}
  }
  function track(event,params={}){
    if(!ready||!eventNames.has(event)||!safeToLoad())return;
    const context=contexts.has(params.context)?params.context:'';
    const payload={event,context,platform:['yandex','vk','apple','spotify','zvuk','deezer','youtube','amazon','mts'].includes(params.platform)?params.platform:''};
    if(Number.isSafeInteger(params.release_id)&&params.release_id>0)payload.release_id=params.release_id;
    if(consent.analytics){
      fetch(apiBase+'/api/analytics/event',{method:'POST',credentials:'omit',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,analytics_consent:true,consent_version:VERSION})}).catch(()=>{});
      if(started.has('google'))window.gtag('event',event,{...payload,page_location:cleanLocation(),page_title:'TWAS Label',page_referrer:safeReferrer()});
      if(started.has('yandex')){
        if(event==='page_view')window.ym(Number(configured.yandex_id),'hit',cleanLocation(),{title:'TWAS Label',referer:safeReferrer()});
        else window.ym(Number(configured.yandex_id),'reachGoal',event,payload);
      }
    }
    if(consent.ads){
      if(started.has('meta'))window.fbq(event==='page_view'?'track':'trackCustom',event==='page_view'?'PageView':event,{context,platform:payload.platform});
      if(started.has('vk'))window._tmr.push(event==='page_view'?{id:configured.vk_id,type:'pageView',start:Date.now(),url:cleanLocation(),referrer:safeReferrer()}:{id:configured.vk_id,type:'reachGoal',goal:event});
    }
  }
  function pageView(params={}){track('page_view',{context:location.pathname.startsWith('/lyrics-video/')?'lyrics_video':location.pathname.startsWith('/l/')?'smartlink':location.pathname.startsWith('/legal/')?'legal':location.hash.slice(1)||'home',...params});}
  function apply(next){
    const revoked=(consent.analytics&&!next.analytics)||(consent.ads&&!next.ads);
    consent=next;try{localStorage.setItem(KEY,JSON.stringify({version:VERSION,...consent,updated_at:new Date().toISOString()}));}catch(_){}
    document.querySelector('.cookie-notice')?.remove();settingsDialog?.close();known=true;
    if(revoked){window.gtag?.('consent','update',{analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});window.fbq?.('consent','revoke');for(const item of document.cookie.split(';')){const name=item.split('=')[0].trim();if(/^(_ga|_gid|_gat|_ym|_fbp|_fbc|_tmr|tmr_)/.test(name)){for(const domain of ['',location.hostname,'.'+location.hostname,'.'+location.hostname.split('.').slice(-2).join('.')])document.cookie=name+'=; Max-Age=0; path=/'+(domain?'; domain='+domain:'');}}location.reload();return;}
    initialize();pageView();
  }
  function settings(){
    settingsDialog?.remove();settingsDialog=document.createElement('dialog');settingsDialog.className='tracking-dialog';
    settingsDialog.innerHTML='<h2>Cookie и аналитика</h2><p>Необходимые cookie обеспечивают вход и работу кабинета.</p><label><input type="checkbox" checked disabled> Необходимые · всегда включены</label><label><input type="checkbox" name="analytics"> Аналитика · Яндекс Метрика, Google Analytics и обезличенная статистика действий</label><label><input type="checkbox" name="ads"> Рекламные пиксели · VK Реклама и Meta</label><p>Тексты форм, контакты, паспортные данные и баланс в события не передаются. <a href="/legal/cookies/" target="_blank" rel="noopener">Подробнее</a>.</p><div><button type="button" data-save>Сохранить выбор</button><button type="button" data-close>Закрыть</button></div>';
    settingsDialog.querySelector('[name=analytics]').checked=consent.analytics;settingsDialog.querySelector('[name=ads]').checked=consent.ads;
    settingsDialog.querySelector('[data-save]').onclick=()=>apply({analytics:settingsDialog.querySelector('[name=analytics]').checked,ads:settingsDialog.querySelector('[name=ads]').checked});
    settingsDialog.querySelector('[data-close]').onclick=()=>settingsDialog.close();document.body.append(settingsDialog);settingsDialog.showModal();
  }
  if(!known){
    const banner=document.createElement('aside');banner.className='cookie-notice';banner.setAttribute('aria-label','Cookie');
    banner.innerHTML='<strong>Cookie и статистика сайта</strong><p>Необходимые cookie помогают войти в кабинет. Аналитику и рекламные пиксели подключаем только с вашего согласия.</p><div class="tracking-buttons"><button type="button" data-essential>Только необходимые</button><button type="button" data-settings>Настроить</button><button type="button" data-all>Принять все</button></div><a href="/legal/cookies/" target="_blank" rel="noopener">О cookie</a>';
    banner.querySelector('[data-essential]').onclick=()=>apply({analytics:false,ads:false});banner.querySelector('[data-settings]').onclick=settings;banner.querySelector('[data-all]').onclick=()=>apply({analytics:true,ads:true});document.body.append(banner);
  }
  const footer=document.querySelector('footer')||document.body;const button=document.createElement('button');button.type='button';button.className='tracking-settings-button';button.textContent='Настройки cookie';button.onclick=settings;footer.append(button);
  window.TwasAnalytics={track,pageView,settings,consent:()=>({...consent})};
  fetch(apiBase+'/api/analytics/config',{credentials:'omit'}).then(response=>response.json()).then(data=>{if(data.success){configured=data.configuration||{};ready=true;initialize();if(known)pageView();}}).catch(()=>{});
  window.addEventListener('twas:navigation',event=>{initialize();pageView(event.detail||{});});
})();
