// ---------------------- localStorage.js ---------------------- //
(function () {
  // ---------------------- Cooldown Management ----------------------
  const DEFAULT_COOLDOWN_MS = 30000; // default: 30 seconds for any action
  const STORAGE_KEY = "PeriDocsCooldowns"; // key for storing cooldown timestamps

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function getCooldownTimestamp(type = "global") {
    const state = loadState();
    return state[type] || 0;
  }

  function setCooldownTimestamp(type = "global") {
    const state = loadState();
    state[type] = Date.now();
    saveState(state);
  }

  function getTimeRemaining(type = "global", customMs = DEFAULT_COOLDOWN_MS) {
    const now = Date.now();
    const last = getCooldownTimestamp(type);
    const remaining = customMs - (now - last);
    return remaining > 0 ? remaining : 0;
  }

  function isUnderCooldown(type = "global", customMs = DEFAULT_COOLDOWN_MS) {
    return getTimeRemaining(type, customMs) > 0;
  }

  // Expose cooldown API globally
  window.PeriDocsCooldown = {
    DEFAULT_COOLDOWN_MS,
    getCooldownTimestamp,
    setCooldownTimestamp,
    getTimeRemaining,
    isUnderCooldown
  };

  // ---------------------- Privacy / Cookie Notice Management ----------------------
  document.addEventListener("DOMContentLoaded", () => {
    const TOAST_KEY = "privacyToastDismissed";
    const toast = document.querySelector("#privacy-toast");

    if (!toast) return;

    // Inject cookie icon + links
    toast.innerHTML = `
      <img src="/static/cookies-icon-by-trinh-ho-from-flaticon-dot-come.png"
           alt="Cookie icon"
           class="cookie-icon"
           title="Cookie icon by Trinh Ho from Flaticon"
           style="width:85px; height:85px;">
      <span>
        We use <strong>minimal</minimal> local storage to improve your experience.
        By continuing to use this site, you agree to our <a href="/privacy-policy">Privacy Policy</a> and <a href="/terms-of-service">Terms of Service</a> pages.
      <button id="privacy-toast-dismiss">&times;</button>
    `;

    const dismissBtn = toast.querySelector("#privacy-toast-dismiss");
    if (!dismissBtn) return;

    const dismissed = localStorage.getItem(TOAST_KEY) === "true";

    // Always trigger the toast if not dismissed
    if (!dismissed) {
      toast.style.display = "flex"; // Ensure it appears immediately
      requestAnimationFrame(() => toast.classList.add("show")); // Trigger transition
    }

    dismissBtn.addEventListener("click", () => {
      toast.classList.remove("show");
      toast.classList.add("hide");
      setTimeout(() => {
        toast.style.display = "none";
      }, 400);
      localStorage.setItem(TOAST_KEY, "true");
    });
  });
})();
