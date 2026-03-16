// peridocs-ui.js — unified UI state: theme, cooldowns, modals, toasts, feedback/entry, privacy toast 
// save-state 2026-03-15T11:46:30-05:00 (YYYYMMDDhhmm)
// ==========================================

document.addEventListener("DOMContentLoaded", () => {

  // ---------------------- Variables / Root ---------------------- //
  const root = document.documentElement;
  const rootStyles = getComputedStyle(root);

  // ---------------------- Extract CSS Variables ---------------------- //
  const COLORS = {
    bg: rootStyles.getPropertyValue('--bg').trim(),
    card: rootStyles.getPropertyValue('--card').trim(),
    muted: rootStyles.getPropertyValue('--muted').trim(),
    accent: rootStyles.getPropertyValue('--accent').trim(),
    accentHover: rootStyles.getPropertyValue('--accent-hover').trim(),
    text: rootStyles.getPropertyValue('--text').trim(),
    white: rootStyles.getPropertyValue('--white').trim(),
    toastSuccess: rootStyles.getPropertyValue('--toast-bg').trim(), // fallback to --toast-bg
  };

  const DIMENSIONS = {
    buttonHeight: rootStyles.getPropertyValue('--button-height').trim(),
    toggleWidth: rootStyles.getPropertyValue('--toggle-width').trim(),
    toggleHeight: rootStyles.getPropertyValue('--toggle-height').trim(),
    toggleKnobSize: rootStyles.getPropertyValue('--toggle-knob-size').trim(),
    toggleKnobMargin: rootStyles.getPropertyValue('--toggle-knob-margin').trim(),
    toggleKnobTransformOn: rootStyles.getPropertyValue('--toggle-knob-transform-on').trim(),
    space1: rootStyles.getPropertyValue('--space-1').trim(),
    space2: rootStyles.getPropertyValue('--space-2').trim(),
  };

  const UI_ELEMENTS = {
    modals: Array.from(document.querySelectorAll(".modal"))
      .reduce((acc, modal) => { if (modal.id) acc[modal.id] = modal; return acc; }, {}),
    modalOpenBtns: document.querySelectorAll("[data-modal-type].modal-open-btn"),
    modalCloseBtns: document.querySelectorAll(".close-btn"),
    feedbackForm: document.querySelector("#feedback-form"),
    entryForm: document.querySelector("#entry-form"),
    deleteForm: document.getElementById("delete-form"),
    deleteSubmit: document.getElementById("delete-submit"),
    consentToggle: document.getElementById("consent-toggle"),
    submitBtn: document.querySelector('#entry-form button[type="submit"]'),
    themeBtn: document.getElementById('theme-toggle-btn'),
    entryWrapper: document.getElementById("entry-wrapper"),
    toastContainer: document.querySelector("#general-toast-container"),
    privacyToast: document.querySelector("#privacy-toast"),
    copyBtns: document.querySelectorAll("[data-safe-text].copy-btn"),
    menuToggle: document.getElementById('menu-toggle-btn'),
    headerMenu: document.querySelector('.header-menu'),
  };

  const CONSENT_SESSION_KEY = "PeriDocs_ConsentGranted";
  const OVERLAY_SHOWN_KEY = "PeriDocs_ConsentOverlayShown";
  const COOLDOWN_MS = 30_000;

  const State = {
    _KEY_THEME: 'PeriDocs_Theme',
    _KEY_COOLDOWNS: 'PeriDocsCooldowns',
    getTheme(defaultVal='light') {
      try { const val = localStorage.getItem(this._KEY_THEME); return val !== null ? JSON.parse(val) : defaultVal; } 
      catch { return defaultVal; }
    },
    setTheme(val) {
      try { localStorage.setItem(this._KEY_THEME, JSON.stringify(val)); } catch {}
    },
    loadCooldowns() {
      try { return JSON.parse(localStorage.getItem(this._KEY_COOLDOWNS)) || {}; } 
      catch { return {}; }
    },
    saveCooldowns(state) {
      try { localStorage.setItem(this._KEY_COOLDOWNS, JSON.stringify(state)); } catch {}
    }
  };

  let consentGranted = sessionStorage.getItem(CONSENT_SESSION_KEY) === "true";

  // ---------------------- Consent Toggle ---------------------- //
  function applyConsentState(granted) {
    consentGranted = granted;
    const overlayAlreadyShown = sessionStorage.getItem(OVERLAY_SHOWN_KEY) === "true";

    if (UI_ELEMENTS.entryWrapper) {
      if (granted) {
        if (!overlayAlreadyShown) {
          UI_ELEMENTS.entryWrapper.setAttribute("data-locked", "true");
          sessionStorage.setItem(OVERLAY_SHOWN_KEY, "true");
          setTimeout(() => UI_ELEMENTS.entryWrapper.setAttribute("data-locked", "false"), 2000);
        } else {
          UI_ELEMENTS.entryWrapper.setAttribute("data-locked", "false");
        }
      } else {
        UI_ELEMENTS.entryWrapper.setAttribute("data-locked", "true");
      }
    }

    if (UI_ELEMENTS.entryForm?.querySelector("textarea"))
      UI_ELEMENTS.entryForm.querySelector("textarea").disabled = !granted;
    if (UI_ELEMENTS.submitBtn) UI_ELEMENTS.submitBtn.disabled = !granted;

    if (UI_ELEMENTS.consentToggle) {
      UI_ELEMENTS.consentToggle.setAttribute("data-state", granted ? "on" : "off");
      UI_ELEMENTS.consentToggle.setAttribute("aria-checked", granted ? "true" : "false");
      const knob = UI_ELEMENTS.consentToggle.querySelector(".toggle-knob");
      const label = UI_ELEMENTS.consentToggle.querySelector(".toggle-label");
      if (knob) knob.style.transform = granted ? `translateX(${DIMENSIONS.toggleKnobTransformOn})` : `translateX(0)`;
      if (label) label.textContent = granted ? " Consent Given" : "Consent Requested";
      UI_ELEMENTS.consentToggle.style.background = granted ? COLORS.accent : 'rgba(255,255,255,0.2)';
      UI_ELEMENTS.consentToggle.style.color = granted ? COLORS.white : COLORS.text;
    }

    sessionStorage.setItem(CONSENT_SESSION_KEY, granted ? "true" : "false");
  }

  applyConsentState(consentGranted);

  UI_ELEMENTS.consentToggle?.addEventListener("click", e => {
    e.stopPropagation();
    UI_ELEMENTS.consentToggle.disabled = true;
    setTimeout(() => UI_ELEMENTS.consentToggle.disabled = false, 3000);
    applyConsentState(!consentGranted);
  });

  // ---------------------- Toast Helper ---------------------- //
  const activeToasts = [];
  function showToast(message, type='info', duration=2500) {
  if (!UI_ELEMENTS.toastContainer) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;       // type class drives color
  toast.textContent = message;

  UI_ELEMENTS.toastContainer.appendChild(toast);
  activeToasts.push(toast);

  // Animate in
  requestAnimationFrame(() => toast.classList.add('show'));

  // Animate out
  setTimeout(() => {
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => {
      toast.remove();
      const idx = activeToasts.indexOf(toast);
      if (idx > -1) activeToasts.splice(idx, 1);
    }, 400);
  }, duration);
}

  // ---------------------- Modal System ---------------------- //
  function getModal(type) { return UI_ELEMENTS.modals[`${type}-modal`] || null; }
  function openModal(type="feedback") {
    const modal = getModal(type);
    if (!modal) return;
    modal.classList.add("is-active");
    document.body.style.overflow = "hidden";
    const ta = modal.querySelector("textarea");
    if (ta) { ta.value=""; ta.dataset.type=type; ta.focus(); }
  }
  function closeModal(type="feedback") {
    const modal = getModal(type);
    if (!modal) return;
    modal.classList.remove("is-active");
    document.body.style.overflow = "";
  }

  UI_ELEMENTS.modalOpenBtns.forEach(btn => btn.addEventListener("click", () => openModal(btn.dataset.modalType)));
  UI_ELEMENTS.modalCloseBtns.forEach(btn => btn.addEventListener("click", () => {
    const modal = btn.closest(".modal");
    if (!modal || !modal.id) return;
    closeModal(modal.id.replace("-modal",""));
  }));

  window.addEventListener("click", e => {
    const modal = e.target.closest(".modal");
    if (modal && e.target === modal) closeModal(modal.id.replace("-modal",""));
  });

  document.addEventListener("keydown", e => { if (e.key==="Escape") Object.values(UI_ELEMENTS.modals).forEach(m=>m.classList.contains("is-active")&&closeModal(m.id.replace("-modal",""))); });

  window.openModal = openModal;
  window.closeModal = closeModal;

  // ---------------------- Theme Toggle ---------------------- //
  root.setAttribute('data-theme', State.getTheme());
  if (UI_ELEMENTS.themeBtn) UI_ELEMENTS.themeBtn.textContent = root.getAttribute('data-theme')==='dark'?'Light Mode':'Dark Mode';
  UI_ELEMENTS.themeBtn?.addEventListener('click', () => {
    const newTheme = root.getAttribute('data-theme')==='dark'?'light':'dark';
    root.setAttribute('data-theme', newTheme);
    State.setTheme(newTheme);
    UI_ELEMENTS.themeBtn.textContent = newTheme==='dark'?'Light Mode':'Dark Mode';
  });

  // ---------------------- Cooldown Helper ---------------------- //
  function canSubmit(type) {
    const now = Date.now();
    const state = State.loadCooldowns();
    if (state[type] && now-state[type]<COOLDOWN_MS) {
      showToast(`Please wait ${Math.ceil((COOLDOWN_MS-(now-state[type]))/1000)}s before submitting again`,'error');
      return false;
    }
    state[type]=now;
    State.saveCooldowns(state);
    return true;
  }

  // ---------------------- Copy Buttons ---------------------- //
  function copySafeTextToClipboard(safeText) {
    if (!safeText) return;
    navigator.clipboard.writeText(safeText).then(()=>showToast("Copy to clipboard successful!","success")).catch(err=>{console.error(err);showToast("Copy to clipboard failed. Please contact support.","error");});
  }
  UI_ELEMENTS.copyBtns.forEach(btn=>btn.addEventListener("click",()=>copySafeTextToClipboard(btn.dataset.safeText)));
  window.copySafeTextToClipboard = copySafeTextToClipboard;

  // ---------------------- Generic Form Submission ---------------------- //
  async function submitFormHandler(form, options) {
    if (!form) return;
    form.addEventListener("submit", async e => {
      e.preventDefault();
      if (!canSubmit(options.type)) return;
      const payload = options.payloadFormatter(form);
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled=true;

      try {
        const res = await fetch(form.action, options.fetchOptions(payload));
        if (!res.ok) throw new Error('Network response not ok');
        const data = options.parseResponse ? await options.parseResponse(res) : res;
        await options.onSuccess(data);
      } catch(err) {
        console.error(err);
        showToast('Submission failed. Please try again.','error');
      } finally { if(submitBtn) submitBtn.disabled=false; }
    });
  }

  // ---------------------- Forms ---------------------- //
  submitFormHandler(UI_ELEMENTS.feedbackForm,{
    type:'feedback',
    payloadFormatter: form=>JSON.stringify({feedback_text: form.querySelector('textarea')?.value.trim()||"", type: form.querySelector('textarea')?.dataset.type||'feedback', ip_hash:"unknown"}),
    fetchOptions: payload=>({method:'POST',headers:{"Content-Type":"application/json"},body:payload}),
    parseResponse: async res=>{const json=await res.json();return json.status==='ok'?json:Promise.reject(json)},
    onSuccess: data=>{showToast(data.status==='ok'?'Feedback submitted!':'Report submitted!','success'); UI_ELEMENTS.feedbackForm.reset(); closeModal('feedback');}
  });

  submitFormHandler(UI_ELEMENTS.entryForm,{
    type:'entry',
    payloadFormatter: form=>JSON.stringify(Object.fromEntries(new FormData(form).entries())),
    fetchOptions: payload=>({method:UI_ELEMENTS.entryForm.method||'POST',headers:{"Content-Type":"application/json"},body:payload}),
    parseResponse: async res=>await res.json(),
    onSuccess: async data=>{
      showToast(data.message||'Entry submitted!','success');
      UI_ELEMENTS.entryForm.reset();
      const spinnerToast=document.createElement('div');
      spinnerToast.className='toast';
      spinnerToast.style.display='inline-flex';
      spinnerToast.style.alignItems='center';
      spinnerToast.style.gap=DIMENSIONS.space1;
      spinnerToast.innerHTML=`<span id="progress-text">Processing... 0%</span><div class="spinner" style="border: 3px solid #ccc; border-top: 3px solid #333; border-radius: 50%; width: ${DIMENSIONS.toggleKnobSize}; height: ${DIMENSIONS.toggleKnobSize}; animation: spin 1s linear infinite;"></div>`;
      UI_ELEMENTS.toastContainer.appendChild(spinnerToast);
      requestAnimationFrame(()=>spinnerToast.classList.add('show'));
      if(!document.getElementById('spinner-style')) {
        const style=document.createElement('style'); style.id='spinner-style';
        style.innerHTML='@keyframes spin {0% {transform: rotate(0deg);} 100% {transform: rotate(360deg);}}';
        document.head.appendChild(style);
      }
      let crisisTriggered=false;
      const wsProtocol=window.location.protocol==='https:'?'wss':'ws';
      const ws=new WebSocket(`${wsProtocol}://${window.location.host}/ws/progress/${data.entry_id}`);
      ws.onopen=()=>console.log("WS connected!");
      ws.onclose=()=>console.log("WS closed");
      ws.onerror=err=>console.error("WS error:",err);
      ws.onmessage=event=>{
        const msg=JSON.parse(event.data);
        if(msg.type==="crisis" && !crisisTriggered){crisisTriggered=true; ws.close(); spinnerToast.classList.remove('show'); spinnerToast.classList.add('hide'); setTimeout(()=>spinnerToast.remove(),400); openModal("crisis"); return;}
        if(crisisTriggered) return;
        const percent=Math.round(Math.min(Math.max(msg.progress||0,0),1)*100);
        const progressText=document.getElementById("progress-text");
        if(progressText) progressText.textContent=`Processing... ${percent}%`;
        if(percent>=100){ws.close(); spinnerToast.classList.remove('show'); spinnerToast.classList.add('hide'); setTimeout(()=>spinnerToast.remove(),400); const real_id=msg.real_id||data.entry_id; setTimeout(()=>window.location.href=`/submit-success?id=${real_id}`,200);}
      };
    }
  });

  submitFormHandler(UI_ELEMENTS.deleteForm,{
    type:'delete',
    payloadFormatter: form=>new URLSearchParams(new FormData(form)),
    fetchOptions: payload=>({method:UI_ELEMENTS.deleteForm.method||'POST', body:payload}),
    parseResponse: async res=>{const htmlText=await res.text(); return new DOMParser().parseFromString(htmlText,"text/html");},
    onSuccess: doc=>{
      const messageEl=doc.querySelector("[data-delete-message]");
      const errorEl=doc.querySelector("[data-delete-error]");
      if(messageEl){ showToast(messageEl.textContent,"success"); UI_ELEMENTS.deleteForm.reset(); setTimeout(()=>window.location.href="/",1500);}
      if(errorEl) showToast(errorEl.textContent,"error");
    }
  });

  // ---------------------- Privacy / Cookie Notice ---------------------- //
  if(UI_ELEMENTS.privacyToast){
    const TOAST_KEY="privacyToastDismissed";
    const dismissed=localStorage.getItem(TOAST_KEY)==="true";
    UI_ELEMENTS.privacyToast.innerHTML=`
      <img src="/static/cookies-icon-by-trinh-ho-from-flaticon-dot-com.png" alt="Cookie icon" class="cookie-icon" title="Cookie icon by Trinh Ho from Flaticon" style="width:85px;height:85px;">
      <span>We use <strong>minimal</strong> local storage to improve your experience. By continuing to use this site, you agree to our <a href="/privacy-policy">Privacy Policy</a> and <a href="/terms-of-service">Terms of Service</a> pages.</span>
      <button id="privacy-toast-dismiss">&times;</button>
    `;
    const dismissBtn=UI_ELEMENTS.privacyToast.querySelector("#privacy-toast-dismiss");
    if(!dismissed){ UI_ELEMENTS.privacyToast.style.display="flex"; requestAnimationFrame(()=>UI_ELEMENTS.privacyToast.classList.add("show")); }
    dismissBtn?.addEventListener("click",()=>{
      UI_ELEMENTS.privacyToast.classList.remove("show");
      UI_ELEMENTS.privacyToast.classList.add("hide");
      setTimeout(()=>UI_ELEMENTS.privacyToast.style.display="none",400);
      localStorage.setItem(TOAST_KEY,"true");
    });
  }

UI_ELEMENTS.menuToggle?.addEventListener('click', () => {
  UI_ELEMENTS.headerMenu?.classList.toggle('show');
});
// ---------------------- Swipeable Cards ---------------------- //

function enableSwipeCards(selector = ".swipe-card") {

  document.querySelectorAll(selector).forEach(card => {

    let startX = 0;
    let currentX = 0;
    let dragging = false;

    card.addEventListener("pointerdown", e => {
      startX = e.clientX;
      dragging = true;
      card.classList.add("swiping");
      card.setPointerCapture(e.pointerId);
    });

    card.addEventListener("pointermove", e => {
      if (!dragging) return;

      currentX = e.clientX - startX;
      const rotate = currentX * 0.05;

      card.style.transform = `translateX(${currentX}px) rotate(${rotate}deg)`;
    });

    card.addEventListener("pointerup", () => {
      dragging = false;
      card.classList.remove("swiping");

      const threshold = 120;

      if (Math.abs(currentX) > threshold) {

        const direction = currentX > 0 ? 1 : -1;

        card.style.transform =
          `translateX(${direction * window.innerWidth}px) rotate(${direction * 20}deg)`;

        card.style.opacity = "0";

        setTimeout(() => card.remove(), 250);

      } else {

        card.style.transform = "";
      }

      currentX = 0;
    });

  });

}

enableSwipeCards();
});