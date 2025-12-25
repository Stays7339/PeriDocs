// peridocs-ui.js — unified UI state: theme, cooldowns, modals, toasts, feedback/journal, privacy toast 
// save-state 202512242015 (YYYYMMDDhhmm)
// ==========================================

/* Notes:
  - Cooldowns are client-side and privacy-first.
  - Theme state persists on refresh.
  - Privacy toast only shows once per user unless localStorage is cleared.
*/

document.addEventListener("DOMContentLoaded", () => {
  // ---------------------- DOM Elements ---------------------- //
  const feedbackModal = document.querySelector(".feedback-modal");
  const feedbackBtns = document.querySelectorAll("#feedback-btn, .feedback-btn");
  const reportBtns = document.querySelectorAll(".report-parse-btn");
  const cancelBtn = document.getElementById("cancel-feedback");
  const feedbackForm = document.querySelector("#feedback-form");
  const journalForm = document.querySelector('#journal-form');
  const toastContainer = document.querySelector("#general-toast-container");
  const privacyToast = document.querySelector("#privacy-toast");
  const themeBtn = document.getElementById('theme-toggle-btn');
  const root = document.documentElement;

  // ---------------------- Crisis Modal ---------------------- //
  const crisisModal = document.getElementById("crisis-modal");
  const crisisCloseBtn = document.getElementById("crisis-close-btn");

  // ---------------------- Unified Modal ---------------------- //
  function openModal(type="feedback") {
    let modal;
    if(type === "crisis") {
      modal = crisisModal;
    } else {
      modal = feedbackModal;
    }
    if(!modal) return;

    modal.style.display = "flex";
    document.body.style.overflow = "hidden";

    // Only focus textarea for feedback/report
    if(type !== "crisis") {
      const ta = modal.querySelector("textarea");
      if(ta) { 
        ta.value = ""; 
        ta.dataset.type = type; 
        ta.focus(); 
      }
    }
  }

  function closeModal(type="feedback") {
    let modal;
    if(type === "crisis") {
      modal = crisisModal;
    } else {
      modal = feedbackModal;
    }
    if(!modal) return;

    modal.style.display = "none";
    document.body.style.overflow = "";
  }

  // ---------------------- Hook up modal buttons ---------------------- //
  feedbackBtns.forEach(btn => btn.addEventListener("click", () => openModal("feedback")));
  reportBtns.forEach(btn => btn.addEventListener("click", () => openModal("report")));
  cancelBtn?.addEventListener("click", () => closeModal("feedback"));
  crisisCloseBtn?.addEventListener("click", () => closeModal("crisis"));

  // Close modal when clicking outside
  window.addEventListener("click", e => {
    if (e.target === feedbackModal) closeModal("feedback");
    if (e.target === crisisModal) closeModal("crisis");
  });

  // Close modal on Escape key
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      closeModal("feedback");
      closeModal("crisis");
    }
  });

  // Expose globally
  window.openFeedbackModal = () => openModal("feedback");
  window.openReportModal = () => openModal("report");
  window.openCrisisModal = () => openModal("crisis");

  // ---------------------- Persistent State Helper ---------------------- //
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

  // ---------------------- Theme Toggle ---------------------- //
  const currentTheme = State.getTheme();
  root.setAttribute('data-theme', currentTheme);
  if (themeBtn) themeBtn.textContent = currentTheme === 'dark' ? 'Light Mode' : 'Dark Mode';
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      const newTheme = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', newTheme);
      State.setTheme(newTheme);
      themeBtn.textContent = newTheme === 'dark' ? 'Light Mode' : 'Dark Mode';
    });
  }

  // ---------------------- Cooldown Helper ---------------------- //
  const COOLDOWN_MS = 30_000;
  function canSubmit(type) {
    const now = Date.now();
    const state = State.loadCooldowns();
    if (state[type] && now - state[type] < COOLDOWN_MS) {
      const remaining = Math.ceil((COOLDOWN_MS - (now - state[type])) / 1000);
      showToast(`Please wait ${remaining}s before submitting again`, 'error');
      return false;
    }
    state[type] = now;
    State.saveCooldowns(state);
    return true;
  }

  // ---------------------- Toast ---------------------- //
  const activeToasts = [];


  function showToast(message, type='info', duration=2500) {
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = 'stacked-toast';
    toast.style.backgroundColor = type === 'success' ? '#A3F5B2' :
                              type === 'error' ? '#F5A3A3' : '#F5E8A3';
    toast.textContent = message;

    toastContainer.appendChild(toast);
    activeToasts.push(toast);

    // Trigger slide-in/fade-in
    requestAnimationFrame(() => {
      toast.classList.add('show');
    });

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

  // ---------------------- Feedback/Report Form Submission ---------------------- //
  if (feedbackForm) {
    feedbackForm.addEventListener("submit", async e => {
      const textarea = feedbackForm.querySelector('textarea'); // <-- Trying to prevent crisis entries from passing through
      const type = textarea?.dataset.type || 'feedback';
      if (!canSubmit(type)) return;

      const payload = { feedback_text: textarea?.value.trim() || "", type, ip_hash:"unknown" };
      try {
        const res = await fetch(feedbackForm.action, { method:'POST', headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
        if (!res.ok) throw new Error('Network response not ok');
        const data = await res.json();
        if (data.status==="ok") { showToast(type==='feedback'?'Feedback submitted!':'Report submitted!', 'success'); feedbackForm.reset(); closeModal(type); }
        else { showToast(data.message || 'Submission failed. Please try again.', 'error'); }
      } catch (err) { console.error(err); showToast('Submission failed. Please try again.', 'error'); }
    });
  }

  // ---------------------- Journal Form Submission ---------------------- //
  if (journalForm) {
    journalForm.addEventListener('submit', async e => {
      e.preventDefault();
      if (!canSubmit('journal')) return;

      const formData = new FormData(journalForm);
      const payload = Object.fromEntries(formData.entries());
      try {
        const res = await fetch(journalForm.action, { method:journalForm.method||'POST', headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
        if (!res.ok) throw new Error('Network response not ok');
        const data = await res.json();
        if (data.status==='ok') { 
          showToast(data.message||'Journal submitted!', 'success'); 
          journalForm.reset();

          // ---------------------- Progress toast using general-toast style ---------------------- //
          const spinnerToast = document.createElement('div');
          spinnerToast.className = 'stacked-toast';
          spinnerToast.style.display = 'inline-flex';
          spinnerToast.style.alignItems = 'center';
          spinnerToast.style.gap = '10px';
          spinnerToast.innerHTML = `
            <span id="progress-text">Processing... 0%</span>
            <div class="spinner" style="border: 3px solid #ccc; border-top: 3px solid #333; border-radius: 50%; width: 18px; height: 18px; animation: spin 1s linear infinite;"></div>
          `;
          toastContainer.appendChild(spinnerToast);
          requestAnimationFrame(() => spinnerToast.classList.add('show'));

          if (!document.getElementById('spinner-style')) {
            const style = document.createElement('style');
            style.id = 'spinner-style';
            style.innerHTML = `
              @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            `;
            document.head.appendChild(style);
          }

          // ---------------------- Connect WebSocket ---------------------- //
          let crisisTriggered = false; // <-- ADDED FLAG

          const ws = new WebSocket(`ws://${window.location.host}/ws/progress/${data.entry_id}`);
          ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            console.log("WS message received:", msg);

            // ---------------------- Crisis check (Option A) ---------------------- //
            if (msg.type === "crisis" && !crisisTriggered) {
              crisisTriggered = true; // <-- SET FLAG
              ws.close();
              spinnerToast.classList.remove('show');
              spinnerToast.classList.add('hide');
              setTimeout(() => spinnerToast.remove(), 400);
              openModal("crisis");
              return; // stop further processing
            }

            // ---------------------- Skip updates if crisis triggered ---------------------- //
            if (crisisTriggered) return;

            const progress = Math.min(Math.max(msg.progress || 0, 0), 1); 
            const percent = Math.round(progress * 100);
            const progressText = document.getElementById("progress-text");
            if (progressText) progressText.textContent = `Processing... ${percent}%`;

            // ---------------------- Redirect when done ---------------------- //
            if (progress >= 1) {
              ws.close();
              spinnerToast.classList.remove('show');
              spinnerToast.classList.add('hide');
              setTimeout(() => spinnerToast.remove(), 400);
              const real_id = msg.real_id || data.entry_id;
              setTimeout(() => { window.location.href = `/submit-success?id=${real_id}`; }, 200);
            }
          };
        } else { showToast(data.message||'Submission failed. Please try again.', 'error'); }
      } catch (err) { console.error(err); showToast('Submission failed. Please try again.', 'error'); }
    });
  }

  // ---------------------- Privacy / Cookie Notice ---------------------- //
  if (privacyToast) {
    const TOAST_KEY = "privacyToastDismissed";
    const dismissed = localStorage.getItem(TOAST_KEY) === "true";

    privacyToast.innerHTML = `
      <img src="/static/cookies-icon-by-trinh-ho-from-flaticon-dot-com.png"
        alt="Cookie icon"
        class="cookie-icon"
        title="Cookie icon by Trinh Ho from Flaticon"
        style="width:85px; height:85px;">
      <span>
        We use <strong>minimal</strong> local storage to improve your experience.
        By continuing to use this site, you agree to our <a href="/privacy-policy">Privacy Policy</a> and <a href="/terms-of-service">Terms of Service</a> pages.
      </span>
      <button id="privacy-toast-dismiss">&times;</button>
    `;

    const dismissBtn = privacyToast.querySelector("#privacy-toast-dismiss");

    if (!dismissed) {
      privacyToast.style.display = "flex";
      requestAnimationFrame(() => privacyToast.classList.add("show"));
    }

    dismissBtn?.addEventListener("click", () => {
      privacyToast.classList.remove("show");
      privacyToast.classList.add("hide");
      setTimeout(() => { privacyToast.style.display = "none"; }, 400);
      localStorage.setItem(TOAST_KEY, "true");
    });
  }

  // ---------------------- Copy Safe Text to Clipboard ---------------------- //
  function copySafeTextToClipboard(safeText) {
    if (!safeText) return;
    navigator.clipboard.writeText(safeText).then(() => {
      showToast("Safe text copied to clipboard!", "success");
    }).catch(err => {
      console.error("Clipboard copy failed:", err);
      showToast("Failed to copy safe text.", "error");
    });
  }

  // ---------------------- Copy Safe Text Button Binding ---------------------- //
  const copyBtn = document.getElementById("copy-entry-btn");
  if (copyBtn) {
    const safeText = copyBtn.dataset.safeText; // read from data attribute
    copyBtn.addEventListener("click", () => copySafeTextToClipboard(safeText));
  }

  // Expose globally
  window.copySafeTextToClipboard = copySafeTextToClipboard;

  // Show Santa hat on Dec 25
  (function() {
    const today = new Date();
    const month = today.getMonth(); // 0-11
    const date = today.getDate();   // 1-31
    if (month === 11 && (date === 25)) { // Dec 24 or 25
      const hat = document.getElementById('santa-hat');
      if (hat) hat.style.display = 'block';
    }
  })();

  //show snowfall
  (function() {
    const hat = document.getElementById('santa-hat');
    const canvas = document.getElementById('snow-canvas');
    if (!canvas || !hat) return;

    const today = new Date();
    const isXmas = today.getMonth() === 11 && today.getDate() === 25;
    if (!isXmas) return; // only on Dec 25

    let active = false;
    let fadeOut = false;
    let animationId;
    const ctx = canvas.getContext('2d');

    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    const flakes = [];
    const flakeCount = 120;

    for (let i = 0; i < flakeCount; i++) {
      flakes.push({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() * 3 + 1,
        d: Math.random() * flakeCount,
        alpha: 1
      });
    }

    let angle = 0;

    function drawFlakes() {
      ctx.clearRect(0, 0, width, height);
      ctx.beginPath();
      for (let i = 0; i < flakeCount; i++) {
        const f = flakes[i];
        ctx.fillStyle = `rgba(255,255,255,${f.alpha})`;
        ctx.moveTo(f.x, f.y);
        ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);
      }
      ctx.fill();
      updateFlakes();
    }

    function updateFlakes() {
      angle += 0.01;
      for (let i = 0; i < flakeCount; i++) {
        const f = flakes[i];
        f.y += Math.cos(angle + f.d) + 1 + f.r / 2;
        f.x += Math.sin(angle) * 0.5;

        // Only respawn if NOT fading out
        if (!fadeOut) {
          if (f.x > width + 5 || f.x < -5 || f.y > height) {
            f.x = Math.random() * width;
            f.y = -10;
            f.alpha = 1;
          }
        }

        // Fade out gradually
        if (fadeOut) {
          f.alpha -= 0.02; // fade speed
          if (f.alpha < 0) f.alpha = 0;
        }
      }
    }


    function animate() {
      drawFlakes();
      if (fadeOut && flakes.every(f => f.alpha <= 0)) {
        // completely done
        canvas.style.display = 'none';
        active = false;
        fadeOut = false;
        cancelAnimationFrame(animationId);
        return;
      }
      animationId = requestAnimationFrame(animate);
    }

    function startSnow() {
      if (active) return;
      active = true;
      fadeOut = false;
      canvas.style.display = 'block';
      animate();
    }

    function stopSnow() {
      if (!active) return;
      fadeOut = true; // start graceful fade
    }

    hat.addEventListener('mouseenter', startSnow);
    hat.addEventListener('mouseleave', stopSnow);

    window.addEventListener('resize', () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    });

  })();
});
