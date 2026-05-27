// feedback-ui.js — isolated feedback/report submission
// save-state 2026-05-27T13:57:45-04:00

document.addEventListener("DOMContentLoaded", () => {

  const feedbackForm = document.getElementById("feedback-form");

  if (!feedbackForm) return;

  feedbackForm.setAttribute("novalidate", "true");

  feedbackForm.addEventListener("submit", async (e) => {

    e.preventDefault();

    const textarea = feedbackForm.querySelector("textarea");

    if (!textarea) return;

    const type = textarea.dataset.type || "feedback";

    if (typeof canSubmit === "function") {
      if (!canSubmit(type)) return;
    }

    const feedbackText = textarea.value.trim();

    if (!feedbackText) return;

    const payload = {
      feedback_text: feedbackText,
      type,
      ip_hash: "unknown"
    };

    try {

      const res = await authFetch(
        feedbackForm.action,
        {
          method: "POST",
          body: JSON.stringify(payload)
        }
      );

      if (!res.ok) {
        throw new Error("Network response not ok");
      }

      const data = await res.json();

      if (data.status === "ok") {

        feedbackForm.reset();

        if (typeof showToast === "function") {

          showToast(
            type === "feedback"
              ? "Feedback submitted!"
              : "Report submitted!",
            "success"
          );
        }

        if (typeof closeModal === "function") {
          closeModal(type);
        }

      } else {

        if (typeof showToast === "function") {
          showToast(
            data.message || "Submission failed. Please try again.",
            "error"
          );
        }
      }

    } catch (err) {

      console.error("Feedback submission error:", err);

      if (typeof showToast === "function") {
        showToast(
          "Submission failed. Please try again.",
          "error"
        );
      }
    }

  });

});