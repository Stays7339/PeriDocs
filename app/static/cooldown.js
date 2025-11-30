// cooldown.js — persistent across pages

const COOLDOWN_DURATION = 30; // seconds
const COOLDOWN_KEY = 'peridocs_cooldown_timestamps';

// ---------------------- Helpers ---------------------- //
function getCooldownData() {
  try {
    return JSON.parse(localStorage.getItem(COOLDOWN_KEY)) || {};
  } catch (err) {
    return {};
  }
}

function setCooldownData(data) {
  localStorage.setItem(COOLDOWN_KEY, JSON.stringify(data));
}

// Toast helper
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.textContent = message;
  toast.className = `toast toast-${type}`;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// Cooldown check
function canSubmit(formType) {
  const data = getCooldownData();
  const now = Date.now();

  if (data[formType] && now - data[formType] < COOLDOWN_DURATION * 1000) {
    const secondsLeft = Math.ceil((COOLDOWN_DURATION * 1000 - (now - data[formType])) / 1000);
    showToast(`Please wait ${secondsLeft} second(s) before submitting again.`, 'info');
    return false;
  }

  data[formType] = now;
  setCooldownData(data);
  return true;
}

// ---------------------- Attach to forms ---------------------- //
function attachCooldownHandlers() {
  const handleForm = (formSelector, type, successCallback) => {
    const form = document.querySelector(formSelector);
    if (!form) return;

    form.addEventListener('submit', e => {
      e.preventDefault();
      if (!canSubmit(type)) return;

      // Journal form uses native submission after brief toast
      if (type === 'journal') {
        e.preventDefault(); // stop default submission immediately
        showToast('Journal submitted!', 'success');
        setTimeout(() => {
          form.submit(); // native submission after toast is visible
        }, 1500); // 1.5s delay to ensure toast is seen
        return;
      }


      // Feedback/report forms: keep async fetch logic
      const formData = new FormData(form);
      fetch(form.action, {
        method: form.method || 'POST',
        body: formData,
      })
      .then(res => {
        if (!res.ok) throw new Error('Network response was not ok');
        successCallback(form);
      })
      .catch(err => {
        showToast('Submission failed. Please try again.', 'error');
        console.error(err);
      });
    });
  };

  // Journal form: async fetch with toast + optional redirect
  handleForm('#journal-form', 'journal', async (form) => {
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());

    try {
      const res = await fetch(form.action, {
        method: form.method || 'POST',
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) throw new Error('Network response was not ok');

      const data = await res.json();
      if (data.status === "ok") {
        showToast(data.message || 'Journal submitted and analysis started!', 'success');
        form.reset();

        // Redirect with entry_id
        setTimeout(() => {
          window.location.href = `/submit-success?id=${data.entry_id}`;
        }, 1000);
      } else {
        showToast(data.message || 'Submission failed. Please try again.', 'error');
      }
    } catch (err) {
      showToast('Submission failed. Please try again.', 'error');
      console.error(err);
    }
  });

  // Feedback/report form
  handleForm('#report-form', 'report', async (form) => {
    const payload = {
      feedback_text: form.querySelector('textarea')?.value.trim() || "",
      type: "report",
      ip_hash: "unknown"
    };
    try {
      const res = await fetch(form.action, {
        method: form.method || 'POST',
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error('Network response was not ok');
      const data = await res.json();
      if (data.status === "ok") {
        showToast('Report submitted!', 'success');
        form.reset();
      } else {
        showToast(data.message || 'Submission failed. Please try again.', 'error');
      }
    } catch (err) {
      showToast('Submission failed. Please try again.', 'error');
      console.error(err);
    }
  });
}

document.addEventListener('DOMContentLoaded', attachCooldownHandlers);
