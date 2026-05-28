// peridocs-misc-ux.js — unified UI state: theme, cooldowns, toasts, feedback/entry, privacy toast 
// save-state 2026-05-26T16:40:40-04:00
// ==========================================


document.addEventListener("DOMContentLoaded", () => {
  // ---------------------- DOM Elements ---------------------- //
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


  const productionMode = document.body.dataset.productionMode === "true";

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

  /* --- Listening For Click on the Consent Toggle (production mode sensitive) --- */
  if (consentToggle) {

    // ------------------------------------------------
    // PRODUCTION MODE:
    // hard-disable consent interaction
    // ------------------------------------------------
    if (productionMode) {

      consentToggle.disabled = true;

      consentToggle.setAttribute("aria-disabled", "true");

      // optional visual cue
      consentToggle.classList.add("disabled");

    }

    // ------------------------------------------------
    // DEVELOPMENT MODE:
    // allow normal interaction
    // ------------------------------------------------
    else {

      consentToggle.addEventListener("click", (e) => {

        e.stopPropagation();

        consentToggle.disabled = true;

        setTimeout(() => {
          consentToggle.disabled = false;
        }, 3000);

        applyConsentState(!consentGranted);

      });

    }
  }

  const toastContainer = document.querySelector("#general-toast-container");
  const privacyToast = document.querySelector("#privacy-toast");
  const themeBtn = document.getElementById('theme-toggle-btn');
  const root = document.documentElement;

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
  if (copyEntryBtn) {  
    const safeText = copyEntryBtn.dataset.safeText; // read from data attribute
    copyEntryBtn.addEventListener("click", () => copySafeTextToClipboard(safeText));
  }

  // ---------------------- Copy Delete Token Button Binding ---------------------- //
  const copyDeleteTokenBtn = document.getElementById("copy-delete-token-btn");
  if (copyDeleteTokenBtn) {  
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

    window.canSubmit = canSubmit;

}); // end DOMContentLoaded

