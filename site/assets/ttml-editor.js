(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const editor = $("ttmlEditor");
  if (!editor) return;
  const audio = $("ttmlAudio"), hold = $("ttmlHold");
  let file = null, fileUrl = null, lines = [], timings = [], holding = null;
  let tracks = [], source = null, screen = "setup", loadVersion = 0, controller = null;
  let previewEnd = null, keyboardHolding = false;
  const escape = text => String(text || "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"}[char]));
  const time = seconds => {
    const ms = Math.max(0,Math.round(seconds * 1000));
    return `${String(Math.floor(ms/3600000)).padStart(2,"0")}:${String(Math.floor(ms/60000)%60).padStart(2,"0")}:${String(Math.floor(ms/1000)%60).padStart(2,"0")}.${String(ms%1000).padStart(3,"0")}`;
  };
  function status(text, error = false) {$("ttmlStatus").textContent = text;$("ttmlStatus").classList.toggle("is-error",error);}
  function show(next) {
    screen = next;
    for (const step of ["setup","record","result"]) $("ttml"+step[0].toUpperCase()+step.slice(1)).classList.toggle("hidden",step!==next);
    $("ttmlStepLabel").textContent = {setup:"1 / 3 · Аудио и текст",record:"2 / 3 · Запись таймингов",result:"3 / 3 · Проверка и сохранение"}[next];
    if (next!=="record") {abortHold();audio.pause();}
  }
  function ready(){ $("ttmlNext").disabled = !file || !Number.isFinite(audio.duration) || audio.duration <= 0 || !$("ttmlText").value.trim(); }
  function renderRecording() {
    const index=timings.length, complete=index>=lines.length;
    $("ttmlCounter").textContent=`${Math.min(index+1,lines.length)} / ${lines.length} строк · записано ${index}`;
    $("ttmlPrevious").textContent=lines[index-1]||"";$("ttmlCurrent").textContent=complete?"Все строки записаны":lines[index]||"";$("ttmlFollowing").textContent=lines[index+1]||"";
    hold.disabled=complete || audio.paused || screen!=="record";
    if (!holding) hold.textContent=complete?"Готово":audio.paused?"Сначала запустите трек":"Удерживайте во время строки";
    $("ttmlUndo").disabled=!index;$("ttmlFinish").disabled=!complete || !lines.length;
  }
  function loadFile(next, track=null) {
    abortHold();audio.pause();previewEnd=null;
    if (fileUrl) URL.revokeObjectURL(fileUrl);
    file=next;source=track;timings=[];lines=[];holding=null;
    fileUrl=URL.createObjectURL(next);audio.src=fileUrl;audio.load();
    $("ttmlAudioName").textContent=track?`${track.artist} — ${track.title}`:next.name;
    $("ttmlNext").disabled=true;
    status("Загружаю аудио…");
  }
  function options(select, requireAudio) {
    const previous=select.value;select.replaceChildren(new Option("Выберите трек",""));
    for (const track of tracks) {
      const option=new Option(`${track.artist?track.artist+" — ":""}${track.title}${requireAudio&&!track.audioUrl?" · аудио не загружено":""}`,String(track.id));
      option.disabled=requireAudio&&!track.audioUrl;select.append(option);
    }
    if ([...select.options].some(item=>item.value===previous)) select.value=previous;
  }
  async function open() {
    window.TwasTeleprompter?.pause();editor.classList.remove("hidden");document.body.classList.add("ttml-open");$("ttmlClose").focus();
    const seed=window.TwasTeleprompter?.seed();
    if (!file && seed?.audioFile) {loadFile(seed.audioFile);if (!$("ttmlText").value) $("ttmlText").value=seed.text||"";}
    try {
      tracks=await window.TwasReleaseTools?.listTracks()||[];
      options($("ttmlSourceRelease"),true);options($("ttmlTargetRelease"),false);
      $("ttmlReleaseHint").textContent=tracks.length?"Аудио уже загруженного трека подставится автоматически.":"Нет доступных треков. Можно загрузить аудио с устройства.";
    } catch(error) {$("ttmlReleaseHint").textContent="Не удалось загрузить релизы. Аудио с устройства доступно.";}
  }
  function close() {
    abortHold();audio.pause();editor.classList.add("hidden");document.body.classList.remove("ttml-open");$("ttmlEditorLink").focus();
  }
  function beginHold() {
    if (screen!=="record" || holding!==null || audio.paused || audio.ended || timings.length>=lines.length) return;
    const begin=audio.currentTime,last=timings.at(-1);
    if (last && begin<last.end-0.002) {status("Перемотка пересекает предыдущую строку. Перезапишите её или продолжите после её конца.",true);return;}
    holding=Math.max(begin,last?.end||0);previewEnd=null;hold.classList.add("is-holding");hold.textContent="Записываю строку… отпустите в конце";status("Начало строки зафиксировано.");
  }
  function endHold() {
    if (holding===null) return;
    const begin=holding,end=Math.min(audio.currentTime,audio.duration);
    holding=null;keyboardHolding=false;hold.classList.remove("is-holding");
    if (end<=begin+0.01) {status("Удерживайте кнопку до конца строки. Короткое нажатие не записано.",true);renderRecording();return;}
    timings.push({begin,end,text:lines[timings.length]});
    status(timings.length===lines.length?"Все строки записаны. Дослушайте трек или нажмите «Готово».":"Строка записана. Следующая строка готова.");renderRecording();
  }
  function abortHold() {
    holding=null;keyboardHolding=false;hold.classList.remove("is-holding");
    if (lines.length) renderRecording();
  }
  function xml() {
    if (!lines.length || timings.length!==lines.length) throw new Error("Сначала запишите все строки.");
    return '<?xml version="1.0" encoding="UTF-8"?>\n<tt xmlns="http://www.w3.org/ns/ttml" xmlns:ttp="http://www.w3.org/ns/ttml#parameter" xml:lang="ru" ttp:timeBase="media"><head/><body><div>\n'+timings.map((line,index)=>`  <p xml:id="line${index+1}" begin="${time(line.begin)}" end="${time(line.end)}">${escape(line.text)}</p>`).join("\n")+'\n</div></body></tt>\n';
  }
  function ttmlFile() {
    const name=(source?.title||file?.name?.replace(/\.[^.]+$/,"")||"lyrics").replace(/[<>:"/\\|?*\u0000-\u001f]/g,"_").slice(0,160);
    return new File([xml()],`${name}.ttml`,{type:"application/ttml+xml"});
  }
  function finish() {
    if (timings.length!==lines.length || !lines.length) return;
    show("result");
    $("ttmlTimeline").innerHTML=timings.map((line,index)=>`<div class="ttml-timeline-row"><span>${index+1}</span><div><p>${escape(line.text)}</p><small>${time(line.begin)} → ${time(line.end)}</small></div><button type="button" class="secondary" data-preview="${index}">Слушать</button></div>`).join("");
    if (source) $("ttmlTargetRelease").value=String(source.id);
    status("TTML готов. Файл можно скачать или отправить к релизу.");
  }
  $("ttmlEditorLink").onclick=event=>{event.preventDefault();open();};$("ttmlClose").onclick=close;
  $("ttmlAudioInput").onchange=()=>{
    const next=$("ttmlAudioInput").files[0];if(!next)return;
    if (!next.type.startsWith("audio/")&&!/\.(wav|mp3|flac|m4a|ogg|aac)$/i.test(next.name)) {status("Выберите аудиофайл.",true);return;}
    loadVersion++;controller?.abort();$("ttmlSourceRelease").value="";loadFile(next);
  };
  $("ttmlSourceRelease").onchange=async()=>{
    const track=tracks.find(item=>String(item.id)===$("ttmlSourceRelease").value);
    loadVersion++;controller?.abort();if (!track?.audioUrl)return;
    const version=loadVersion;controller=new AbortController();$("ttmlNext").disabled=true;status("Загружаю аудио релиза…");
    try {
      const response=await fetch(track.audioUrl,{credentials:"include",signal:controller.signal});
      if(!response.ok)throw new Error("Не удалось получить аудио. Загрузите WAV с устройства.");
      const blob=await response.blob();if(version!==loadVersion)return;
      const ext=blob.type.includes("wav")?"wav":blob.type.includes("flac")?"flac":blob.type.includes("ogg")?"ogg":blob.type.includes("mp4")?"m4a":"mp3";
      $("ttmlAudioInput").value="";loadFile(new File([blob],`${track.title}.${ext}`,{type:blob.type||"audio/mpeg"}),track);
    }catch(error){if(error.name!=="AbortError"){status(error.message,true);ready();}}
  };
  $("ttmlText").oninput=ready;
  audio.onloadedmetadata=()=>{ready();status("Аудио готово. Вставьте текст и переходите к записи.");};
  audio.onerror=()=>{status("Браузер не смог открыть аудио. Попробуйте WAV или MP3.",true);$("ttmlNext").disabled=true;};
  $("ttmlNext").onclick=()=>{
    if ($("ttmlNext").disabled)return;
    lines=$("ttmlText").value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
    if (!lines.length)return;
    timings=[];audio.currentTime=0;show("record");renderRecording();status("Запустите трек и удерживайте кнопку во время каждой строки.");
  };
  audio.addEventListener("play",renderRecording);
  audio.addEventListener("pause",()=>{if(audio.ended&&holding!==null)endHold();else abortHold();renderRecording();});
  audio.addEventListener("ended",()=>{endHold();renderRecording();if(timings.length<lines.length)status("Трек закончился, но остались строки. Перезапишите последнюю строку или начните заново.",true);});
  audio.addEventListener("timeupdate",()=>{if(previewEnd!==null&&audio.currentTime>=previewEnd){previewEnd=null;audio.pause();}});
  hold.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();hold.setPointerCapture(event.pointerId);beginHold();});
  hold.addEventListener("pointerup",event=>{event.preventDefault();const box=hold.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom){abortHold();audio.pause();status("Удержание прервано. Запишите строку снова.");}else endHold();});
  hold.addEventListener("pointercancel",()=>{abortHold();audio.pause();status("Удержание прервано. Эта строка не записана.");});
  hold.addEventListener("lostpointercapture",()=>{if(holding!==null){abortHold();audio.pause();}});
  hold.addEventListener("contextmenu",event=>event.preventDefault());
  document.addEventListener("keydown",event=>{
    if(editor.classList.contains("hidden"))return;
    if(event.code==="Escape"){event.preventDefault();event.stopImmediatePropagation();close();return;}
    if(event.code!=="Space" || screen!=="record" || event.target.closest("input,textarea,select"))return;
    event.preventDefault();event.stopPropagation();if(!event.repeat){keyboardHolding=true;beginHold();}
  },true);
  document.addEventListener("keyup",event=>{if(event.code==="Space"&&keyboardHolding){event.preventDefault();endHold();}},true);
  function interruption(){if(editor.classList.contains("hidden"))return;if(holding!==null)status("Запись строки прервана — запишите её снова.");abortHold();audio.pause();}
  window.addEventListener("blur",interruption);document.addEventListener("visibilitychange",()=>{if(document.hidden)interruption();});
  $("ttmlUndo").onclick=()=>{abortHold();audio.pause();const previous=timings.pop();if(previous)audio.currentTime=Math.max(0,previous.begin-1);renderRecording();status("Строка отменена. Запустите трек и запишите её снова.");};
  $("ttmlRestart").onclick=()=>{if(timings.length&&!confirm("Удалить записанные тайминги и начать заново?"))return;abortHold();audio.pause();timings=[];audio.currentTime=0;renderRecording();status("Готово к новой записи.");};
  $("ttmlBack").onclick=()=>{if(timings.length&&!confirm("Вернуться к тексту? При следующем запуске тайминги будут записаны заново."))return;show("setup");ready();};
  $("ttmlFinish").onclick=finish;
  $("ttmlRevise").onclick=()=>{previewEnd=null;show("record");renderRecording();};
  $("ttmlTimeline").onclick=event=>{const button=event.target.closest("[data-preview]");if(!button)return;const line=timings[Number(button.dataset.preview)];audio.currentTime=line.begin;previewEnd=line.end;audio.play().catch(()=>status("Не удалось запустить аудио.",true));};
  $("ttmlDownload").onclick=()=>{try{const next=ttmlFile(),url=URL.createObjectURL(next),link=document.createElement("a");link.href=url;link.download=next.name;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(error){status(error.message,true);}};
  $("ttmlUse").onclick=()=>{try{window.TwasTeleprompter?.loadRecording({audioFile:file,ttmlFile:ttmlFile(),artist:source?.artist||window.TwasTeleprompter?.seed().artist,title:source?.title||window.TwasTeleprompter?.seed().title||file.name.replace(/\.[^.]+$/,"")});close();}catch(error){status(error.message,true);}};
  $("ttmlAttach").onclick=async()=>{
    const target=tracks.find(track=>String(track.id)===$("ttmlTargetRelease").value);
    if(!target){status("Выберите свой релиз. Для отправки нужно войти в аккаунт.",true);return;}
    if(!$("ttmlAttachPersonalConsent").checked){status("Подтвердите отдельное согласие перед отправкой.",true);return;}
    if(target.hasLyrics&&!confirm("У трека уже есть текст. Заменить его новым TTML?"))return;
    $("ttmlAttach").disabled=true;
    try{const result=await window.TwasReleaseTools.attachLyrics(target.id,ttmlFile());target.hasLyrics=true;status(result?.telegram_synced===false?"TTML сохранён у релиза и доступен команде. Доставка файла в Telegram пока не выполнена.":"TTML отправлен к релизу и доступен команде лейбла.");}
    catch(error){status(error.message,true);}
    finally{$("ttmlAttach").disabled=false;}
  };
})();
