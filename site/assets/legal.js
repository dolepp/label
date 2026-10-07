(() => {
  const version = "2026-10-06";
  let accepted = false;
  try { accepted = localStorage.getItem("twas_cookie_notice") === version; } catch (_) {}
  if (!accepted && !window.TwasConsentManager) {
    const banner = document.createElement("aside"); banner.className="cookie-notice";banner.setAttribute("aria-label","Cookie");
    banner.innerHTML='<strong>Cookie для работы кабинета</strong><p>Используем необходимые cookie для входа и сохраняем настройки в браузере.</p><button type="button">Принять необходимые</button><a href="/legal/cookies/" target="_blank" rel="noopener">Подробнее</a>';
    banner.querySelector("button").onclick=()=>{try{localStorage.setItem("twas_cookie_notice",version);}catch(_){}banner.remove();};document.body.append(banner);
  }
  const receipts = new Set();
  window.twasRecordLegalConsent = async (apiBase, specified) => {
    let scope = specified;
    let personal = specified && document.getElementById(`${specified}PersonalConsent`)?.checked;
    let terms = specified && document.getElementById(`${specified}TermsConsent`)?.checked;
    if (!scope) {
      const active = document.activeElement?.closest("form");
      const form = active || [...document.querySelectorAll("form[data-legal-ready]")].find(item => !item.closest(".hidden") && item.querySelector("[data-personal-consent]:checked"));
      scope = form?.id || (form ? "service-request" : "");
      personal = !!form?.querySelector("[data-personal-consent]:checked,input[name=consent]:checked");
      terms = !!form?.querySelector("[data-terms-consent]:checked");
      if (!personal && document.getElementById("profilePersonalConsent")?.checked) {scope="profile";personal=true;}
    }
    if (!personal || !scope) return;
    const key = `${scope}:${terms}`;
    if (receipts.has(key)) return;
    const response = await fetch(`${apiBase}/api/legal/consent`, {method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({version,scope,personal_data:true,terms:!!terms})});
    if (!response.ok) throw new Error("Не удалось сохранить согласие. Повторите отправку.");
    receipts.add(key);
  };
  function decorate(form) {
    if (form.dataset.legalReady || form.closest("#teleprompterTool") || form.closest(".license-dialog")) return;
    if (/VerifyForm$/.test(form.id)) return;
    if (!form.querySelector('input[type="email"],input[name="email"],#loginCode,#authCode,input[name="message"],textarea[name="message"]') && !["loginForm","releaseForm","profileEditForm","emailAuthForm","accountEmailForm"].includes(form.id) && !form.closest("#modalHost")) return;
    form.dataset.legalReady="1";
    const label=document.createElement("label");label.className="legal-check";
    label.innerHTML='<input type="checkbox" required data-personal-consent>Даю отдельное <a href="/legal/consent/" target="_blank" rel="noopener">согласие на обработку персональных данных</a>. <a href="/legal/privacy/" target="_blank" rel="noopener">Политика обработки данных</a>.';
    const submit=form.querySelector('[type="submit"]');submit?submit.before(label):form.append(label);
    if (["loginForm","emailAuthForm","releaseForm"].includes(form.id)) {
      const terms=document.createElement("label");terms.className="legal-check";
      terms.innerHTML=`<input type="checkbox" required data-terms-consent>Принимаю <a href="/legal/${form.id==="releaseForm"?"offer":"terms"}/" target="_blank" rel="noopener">${form.id==="releaseForm"?"оферту на выбранную услугу":"пользовательское соглашение"}</a>.`;
      label.after(terms);
    }
  }
  function scan(){document.querySelectorAll("form").forEach(decorate);}
  scan();new MutationObserver(scan).observe(document.body,{childList:true,subtree:true});
  document.addEventListener("submit",event=>{
    const form=event.target;if (!form.dataset.legalReady)return;
    if ([...form.querySelectorAll('[data-personal-consent],[data-terms-consent]')].some(input=>!input.checked)) {
      event.preventDefault();event.stopImmediatePropagation();form.reportValidity();
    }
  },true);
})();
