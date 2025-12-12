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

function showToast(message, type = 'info', duration = 3000) {
  return new Promise(resolve => {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.className = `toast toast-${type}`;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.remove();
      resolve();
    }, duration);
  });
}

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
  const handleForm = (formSelector, type, submitCallback) => {
    const form = document.querySelector(formSelector);
    if (!form) return;

    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (!canSubmit(type)) return;

      if (type === 'journal') {
        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());
        const resultsDiv = document.getElementById('nlp-results');

        // Only update resultsDiv if it exists
        if (resultsDiv) resultsDiv.innerHTML = `<p>Analyzing...</p>`;

        try {
          const res = await fetch(form.action, {
            method: form.method || 'POST',
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });

          if (!res.ok) throw new Error('Network response was not ok');

          const data = await res.json();
          const nlp = data.nlp_result;

          if (resultsDiv) {
            const emotions = nlp.emotions || {};
            const dominant = Object.keys(emotions).reduce((a, b) => emotions[a] > emotions[b] ? a : b, 'neutral');
            const emotionHtml = Object.entries(emotions)
              .map(([k, v]) => `<li>${k}: ${(v*100).toFixed(1)}%</li>`)
              .join('');

            resultsDiv.innerHTML = `
              <h3>Analysis Results</h3>
              <p><strong>Dominant Emotion:</strong> ${dominant}</p>
              <ul>${emotionHtml}</ul>
              <p><strong>Repetition Multiplier:</strong> ${nlp.repetition_multiplier.toFixed(2)}</p>
            `;
          }

          await showToast(data.message || 'Analysis complete!', 'success', 1500);
          form.reset();
        } catch (err) {
          console.error(err);
          if (resultsDiv) resultsDiv.innerHTML = `<p style="color:red;">Error analyzing text.</p>`;
          await showToast('Submission failed. Please try again.', 'error', 3000);
        }
        return;
      }

      if (submitCallback) submitCallback(form);
    });
  };

  const reportSubmitCallback = async form => {
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
        form.reset();
        await showToast('Report submitted!', 'success', 1500);
      } else {
        await showToast(data.message || 'Submission failed. Please try again.', 'error', 3000);
      }
    } catch (err) {
      await showToast('Submission failed. Please try again.', 'error', 3000);
      console.error(err);
    }
  };

  handleForm('#journal-form', 'journal');
  handleForm('#report-form', 'report', reportSubmitCallback);
}

document.addEventListener('DOMContentLoaded', attachCooldownHandlers);
