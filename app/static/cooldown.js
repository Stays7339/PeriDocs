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

  // Journal form: show brief toast before redirect
  handleForm('#journal-form', 'journal', (form) => {
    showToast('Journal submitted!', 'success');
    setTimeout(() => {
      window.location.href = '/submit-success';
    }, 800); // 0.8s delay for UX
  });

  //specifiies data types for feedback submissions
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
