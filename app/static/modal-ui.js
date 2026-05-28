// modal-ui.js
// save-state 2026-05-27T20:21:00-04:00

document.addEventListener("DOMContentLoaded", () => {

  const feedbackModal = document.getElementById("feedback-modal");
  const crisisModal = document.getElementById("crisis-modal");

  const feedbackBtns = document.querySelectorAll(
    "#feedback-btn, .feedback-btn"
  );

  document.addEventListener("click", (e) => {


    const btn = e.target.closest(".report-parse-btn");



    if (!btn) return;



    openModal("report");

  });

  const cancelBtn = document.getElementById("cancel-feedback");
  const crisisCloseBtn = document.getElementById("crisis-close-btn");

  function openModal(type = "feedback") {

    let modal = feedbackModal;

    if (type === "crisis") {
      modal = crisisModal;
    }

    if (!modal) return;

    modal.classList.add("is-open");

    document.body.style.overflow = "hidden";

    if (type !== "crisis") {
      const textarea = modal.querySelector("textarea");

      if (textarea) {
        textarea.focus();
        textarea.dataset.type = type;
      }
    }
  }

  function closeModal(type = "feedback") {

    let modal = feedbackModal;

    if (type === "crisis") {
      modal = crisisModal;
    }

    if (!modal) return;

    modal.classList.remove("is-open");

    document.body.style.overflow = "";
  }


  cancelBtn?.addEventListener("click", () => {
    closeModal("feedback");
  });

  crisisCloseBtn?.addEventListener("click", () => {
    closeModal("crisis");
  });

  window.addEventListener("click", (e) => {
    if (e.target === feedbackModal) {
      closeModal("feedback");
    }

    if (e.target === crisisModal) {
      closeModal("crisis");
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal("feedback");
      closeModal("crisis");
    }
  });

  window.openModal = openModal;
  window.closeModal = closeModal;

  window.openFeedbackModal = () => openModal("feedback");
  window.openReportModal = () => openModal("report");
  window.openCrisisModal = () => openModal("crisis");

});