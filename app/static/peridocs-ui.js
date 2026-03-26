// peridocs-ui.js — unified UI state: theme, cooldowns, modals, toasts, feedback/entry, privacy toast 
// save-state 2026-03-24T22:39:45-04:00
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
  const entryForm = document.querySelector('#entry-form');

  /* ================================
     Consent Lock Feature
  ================================ */
  const entryWrapper = document.getElementById("entry-wrapper");
  const consentToggle = document.getElementById("consent-toggle");
  const textarea = entryForm?.querySelector("textarea");
  const submitBtn = entryForm?.querySelector('button[type="submit"]');

  const CONSENT_SESSION_KEY = "PeriDocs_ConsentGranted";
  const OVERLAY_SHOWN_KEY = "PeriDocs_ConsentOverlayShown";

  // Initial consent state
  let consentGranted = sessionStorage.getItem(CONSENT_SESSION_KEY) === "true";

  // Streaks element
  const streaks = entryWrapper?.querySelector(".entry-overlay-streaks");

  // ---------------------- Apply Consent State ---------------------- //
  function applyConsentState(granted) {
    consentGranted = granted;
    const overlayAlreadyShown = sessionStorage.getItem(OVERLAY_SHOWN_KEY) === "true";
    const overlay = entryWrapper?.querySelector(".entry-overlay");

    if (entryWrapper) {
      if (granted) {
        if (!overlayAlreadyShown) {
          // First-time opt-in: show overlay for 2s
          entryWrapper.setAttribute("data-locked", "true"); // overlay fully visible
          sessionStorage.setItem(OVERLAY_SHOWN_KEY, "true");

          setTimeout(() => {
            entryWrapper.setAttribute("data-locked", "false"); // fade overlay (and streaks together)
          }, 2000);
        } else {
          // Already opted-in previously: hide overlay immediately
          entryWrapper.setAttribute("data-locked", "false");
        }
      } else {
        // Opt-out: overlay stays visible (locked)
        entryWrapper.setAttribute("data-locked", "true");
      }
    }

    // Enable/disable textarea & submit
    if (textarea) textarea.disabled = !granted;
    if (submitBtn) submitBtn.disabled = !granted;

    // Update toggle pill
    if (consentToggle) {
      consentToggle.setAttribute("data-state", granted ? "on" : "off");
      consentToggle.setAttribute("aria-checked", granted ? "true" : "false");
      const label = consentToggle.querySelector(".toggle-label");
      if (label) label.textContent = granted ? " Consent Given" : "Consent Requested";
    }

    // Persist consent
    sessionStorage.setItem(CONSENT_SESSION_KEY, granted ? "true" : "false");
  }
  /* --- Initialize --- */
  applyConsentState(consentGranted);

  /* --- Listening For Click on the Consent Toggle (un-comment to re-enable consent toggle) --- */
  if (consentToggle) {
    consentToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      // Disable toggle for 3 seconds to prevent accidental double-click
      consentToggle.disabled = true;
      setTimeout(() => {
        consentToggle.disabled = false;
      }, 3000);
      applyConsentState(!consentGranted);
    });
  }
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

  // ---------------------- entry Form Submission ---------------------- //
  if (entryForm) {
    entryForm.addEventListener('submit', async e => {
      e.preventDefault();
      if (!canSubmit('entry')) return;

      const formData = new FormData(entryForm);
      const payload = Object.fromEntries(formData.entries());
      try {
        const res = await fetch(entryForm.action, { method:entryForm.method||'POST', headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
        if (!res.ok) throw new Error('Network response not ok');
        const data = await res.json();
        if (data.status==='ok') { 
          showToast(data.message||'Entry submitted!', 'success'); 
          entryForm.reset();

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

          const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
          const ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws/progress/${data.entry_id}`);
          ws.onopen = () => console.log("WS connected!");
          ws.onclose = () => console.log("WS closed");
          ws.onerror = (err) => console.error("WS error:", err);
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

  // ---------------------- Copy Text to Clipboard ---------------------- //
function copySafeTextToClipboard(safeText) {
  if (!safeText) return;
  navigator.clipboard.writeText(safeText).then(() => {
    showToast("Copy to clipboard successful!", "success");
  }).catch(err => {
    console.error("Clipboard copy failed:", err);
    showToast("Copy to clipboard failed. Please contact support.", "error");
  });
}

// ---------------------- Copy Entry Button Binding ---------------------- //
const copyEntryBtn = document.getElementById("copy-entry-btn");
if (copyEntryBtn) {  // FIXED: check the correct variable
  const safeText = copyEntryBtn.dataset.safeText; // read from data attribute
  copyEntryBtn.addEventListener("click", () => copySafeTextToClipboard(safeText));
}

// ---------------------- Copy Delete Token Button Binding ---------------------- //
const copyDeleteTokenBtn = document.getElementById("copy-delete-token-btn");
if (copyDeleteTokenBtn) {  // FIXED: check the correct variable
  const safeText = copyDeleteTokenBtn.dataset.safeText; // read from data attribute
  copyDeleteTokenBtn.addEventListener("click", () => copySafeTextToClipboard(safeText));
}

// Expose globally
window.copySafeTextToClipboard = copySafeTextToClipboard;

  // ---------------------- Delete Entry Form Submission ---------------------- //
  const deleteForm = document.getElementById("delete-form");
  const deleteSubmit = document.getElementById("delete-submit");

  if (deleteForm && deleteSubmit) {
    deleteForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      if (typeof canSubmit !== "function") {
        console.error("canSubmit is not defined!");
        return;
      }

      if (!canSubmit("delete")) return; // optional cooldown like entry/feedback

      const formData = new FormData(deleteForm);
      const payload = new URLSearchParams(formData); // x-www-form-urlencoded

      deleteSubmit.disabled = true;

      try {
        const res = await fetch(deleteForm.action, {
          method: deleteForm.method || "POST",
          body: payload,
        });

        const htmlText = await res.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(htmlText, "text/html");

        const messageEl = doc.querySelector("[data-delete-message]");
        const errorEl = doc.querySelector("[data-delete-error]");

        if (messageEl) {
          showToast(messageEl.textContent, "success");
          deleteForm.reset();
          setTimeout(() => {
            window.location.href = "/";
          }, 1500);
        }
        if (errorEl) showToast(errorEl.textContent, "error");

      } catch (err) {
        console.error(err);
        showToast("Network error. Please try again.", "error");
      } finally {
        deleteSubmit.disabled = false;
      }
  }); // end deleteForm submit listener
    }

// =========================
// Header & Mobile Menu
// =========================

function initHeaderMenu() {
  try {
    const headerMenu = document.querySelector('.header-menu');
    const menuToggle = document.getElementById('menu-toggle-btn');
    const themeBtn = document.getElementById('theme-toggle-btn');
    const feedbackBtn = document.getElementById('feedback-btn');

    // Mobile menu toggle
    menuToggle?.addEventListener('click', () => {
      headerMenu?.classList.toggle('show');
    });

    // Move theme/feedback buttons into sidebar on mobile
    function updateSidebarButtons() {
      if (!headerMenu || !themeBtn || !feedbackBtn) return;
      if (window.innerWidth <= 835) {
        if (!headerMenu.contains(themeBtn)) headerMenu.appendChild(themeBtn);
        if (!headerMenu.contains(feedbackBtn)) headerMenu.appendChild(feedbackBtn);
      } else {
        if (themeBtn.parentNode === headerMenu) document.body.appendChild(themeBtn);
        if (feedbackBtn.parentNode === headerMenu) document.body.appendChild(feedbackBtn);
      }
    }
    updateSidebarButtons();
    window.addEventListener('resize', updateSidebarButtons);

    // Header link/button hover and active
    function styleHeaderButtons() {
      headerMenu?.querySelectorAll('a, button').forEach(el => {
        el.style.width = '100%';
        el.style.marginBottom = '1.5rem';
        el.style.display = 'inline-flex';
        el.style.alignItems = 'center';
        el.style.justifyContent = 'center';
        el.style.fontFamily = "'CabinetGrotesk-Variable', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial";
        el.style.fontWeight = '600';
        el.style.height = '48px';
        el.style.textDecoration = 'none';
        el.style.color = '#FFFFFF';
        el.style.borderRadius = '10px';
        el.style.transition = 'background 0.2s ease, transform 0.1s ease';
        el.addEventListener('mouseenter', () => { el.style.transform='translateY(-1px)'; });
        el.addEventListener('mouseleave', () => { el.style.transform='translateY(0)'; });
        el.addEventListener('mousedown', () => el.style.transform='translateY(0)');
      });
    }
    styleHeaderButtons();

  } catch (err) {
    console.error('Header/menu init failed:', err);
  }
}

// Run immediately or on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHeaderMenu);
} else {
  initHeaderMenu();
}

}); // end DOMContentLoaded

