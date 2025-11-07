// feedback.js — handles feedback modal with JSON submission + toast notifications

document.addEventListener("DOMContentLoaded", () => {
  const feedbackModal = document.querySelector(".feedback-modal");
  const textarea = feedbackModal?.querySelector("textarea");
  const feedbackBtns = document.querySelectorAll("#feedback-btn, .feedback-btn");
  const reportBtns = document.querySelectorAll(".report-parse-btn");
  const cancelBtn = document.getElementById("cancel-feedback");
  const feedbackForm = document.querySelector("#feedback-form");
  const toastContainer = document.querySelector("#feedback-notification");

  // ---------------------- Toast helper ---------------------- //
  function showToast(message, type = 'info') {
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

  // ---------------------- Modal open/close ---------------------- //
  function openModal(type = "feedback") {
    if (!feedbackModal) return;
    feedbackModal.style.display = "flex";
    document.body.style.overflow = "hidden";
    if (textarea) {
      textarea.value = "";
      textarea.dataset.type = type;
      textarea.focus();
    }
  }

  function closeModal() {
    if (!feedbackModal) return;
    feedbackModal.style.display = "none";
    document.body.style.overflow = "";
  }

  // ---------------------- Modal triggers ---------------------- //
  feedbackBtns.forEach(btn => btn.addEventListener("click", () => openModal("feedback")));
  reportBtns.forEach(btn => btn.addEventListener("click", () => openModal("report")));
  cancelBtn?.addEventListener("click", closeModal);
  window.addEventListener("click", e => { if (e.target === feedbackModal) closeModal(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

  // ---------------------- Cooldown check helper ---------------------- //
  function canSubmit(type) {
    return !(window.PeriDocsCooldown?.isUnderCooldown(type));
  }

  // ---------------------- Form submission ---------------------- //
  if (feedbackForm) {
    feedbackForm.addEventListener("submit", async e => {
      e.preventDefault();
      const type = textarea?.dataset.type || 'feedback';

      if (!canSubmit(type)) {
        showToast("Please wait before submitting again.", "error");
        return;
      }

      const payload = {
        feedback_text: textarea?.value.trim() || "",
        type: type,
        ip_hash: "unknown"
      };

      try {
        const res = await fetch(feedbackForm.action, {
          method: 'POST',
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error('Network response not ok');
        const data = await res.json();

        if (data.status === "ok") {
          showToast(type === 'feedback' ? 'Feedback submitted!' : 'Report submitted!', 'success');
          feedbackForm.reset();
          closeModal();
        } else {
          showToast(data.message || 'Submission failed. Please try again.', 'error');
        }
      } catch (err) {
        console.error(err);
        showToast('Submission failed. Please try again.', 'error');
      }
    });
  }

  // ---------------------- Expose modal globally ---------------------- //
  window.openFeedbackModal = () => openModal("feedback");
  window.openReportModal = () => openModal("report");
});
