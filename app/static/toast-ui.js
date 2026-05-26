// toast-ui.js — extracted from peridocs-misc-ux.js
// save-state 2026-05-26
// ==========================================

document.addEventListener("DOMContentLoaded", () => {

  // ---------------------- Toast DOM Dependency ---------------------- //
  const toastContainer = document.querySelector("#general-toast-container");

  // ---------------------- Toast State ---------------------- //
  const activeToasts = [];

  /**
   * Global toast function (UNCHANGED API)
   * - message: string
   * - type: 'info' | 'success' | 'error' | 'warning' (existing usage preserved)
   * - duration: ms
   */
  window.showToast = function(message, type='info', duration=2500) {
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = 'stacked-toast';

    /* adds a CSS class to the toast element, choosing the class name based on the type, 
    but if the type is "info", it swaps it to "neutral" instead. */
    toast.classList.add(`toast-${type === 'info' ? 'neutral' : type}`);
    
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
  };

});