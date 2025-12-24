// peridocs-ui.js — unified UI state: theme, cooldowns, modals, toasts, feedback/journal, privacy toast 
// (save-state 202512232129 (YYYYMMDDhhmm)

/* Notes:
  - Cooldowns are client-side and privacy-first.
  - Theme state persists on refresh.
  - Privacy toast only shows once per user unless localStorage is cleared.
*/

document.addEventListener("DOMContentLoaded", () => {
  // ---------------------- DOM Elements ---------------------- //
  const feedbackModal = document.querySelector(".feedback-modal");
  const textarea = feedbackModal?.querySelector("textarea");
  const feedbackBtns = document.querySelectorAll("#feedback-btn, .feedback-btn");
  const reportBtns = document.querySelectorAll(".report-parse-btn");
  const cancelBtn = document.getElementById("cancel-feedback");
  const feedbackForm = document.querySelector("#feedback-form");
  const journalForm = document.querySelector('#journal-form');
  const toastContainer = document.querySelector("#general-toast-notification");
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

  // ---------------------- Toast ---------------------- //
  function showToast(message, type='info') {
    if (!toastContainer) return;
    toastContainer.textContent = message;
    toastContainer.style.backgroundColor = type === 'success' ? '#A3F5B2' :
                                       type === 'error' ? '#F5A3A3' : '#F5E8A3';
    toastContainer.style.color = '#000';
    toastContainer.style.display = 'block';
    toastContainer.style.opacity = 1;
    setTimeout(() => {
      toastContainer.style.transition = 'opacity 0.5s';
      toastContainer.style.opacity = 0;
      setTimeout(() => toastContainer.style.display = 'none', 500);
    }, 2500);
  }

  // ---------------------- Modal ---------------------- //
  function openModal(type="feedback") {
    if (!feedbackModal) return;
    feedbackModal.style.display = "flex";
    document.body.style.overflow = "hidden";
    if (textarea) { textarea.value = ""; textarea.dataset.type = type; textarea.focus(); }
  }
  function closeModal() {
    if (!feedbackModal) return;
    feedbackModal.style.display = "none";
    document.body.style.overflow = "";
  }
  feedbackBtns.forEach(btn => btn.addEventListener("click", () => openModal("feedback")));
  reportBtns.forEach(btn => btn.addEventListener("click", () => openModal("report")));
  cancelBtn?.addEventListener("click", closeModal);
  window.addEventListener("click", e => { if (e.target === feedbackModal) closeModal(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
  window.openFeedbackModal = () => openModal("feedback");
  window.openReportModal = () => openModal("report");

  // ---------------------- Feedback/Report Form Submission ---------------------- //
  if (feedbackForm) {
    feedbackForm.addEventListener("submit", async e => {
      e.preventDefault();
      const type = textarea?.dataset.type || 'feedback';
      if (!canSubmit(type)) return;

      const payload = { feedback_text: textarea?.value.trim() || "", type, ip_hash:"unknown" };
      try {
        const res = await fetch(feedbackForm.action, { method:'POST', headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
        if (!res.ok) throw new Error('Network response not ok');
        const data = await res.json();
        if (data.status==="ok") { showToast(type==='feedback'?'Feedback submitted!':'Report submitted!', 'success'); feedbackForm.reset(); closeModal(); }
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
        if (data.status==='ok') { showToast(data.message||'Journal submitted!', 'success'); journalForm.reset();
          setTimeout(()=>{ window.location.href = `/submit-success?id=${data.entry_id}`; }, 1000);
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
});
