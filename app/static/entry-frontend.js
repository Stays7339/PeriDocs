// entry-frontend.js — isolated entry submission + progress orchestration
// save-state 2026-06-05T17:22:35-04:00
// ==========================================

document.addEventListener("DOMContentLoaded", () => {

  // ---------------------- DOM Elements ---------------------- //
  const entryForm = document.querySelector('#entry-form');

  // ---------------------- Entry Submission for /create-entry page ---------------------- //
  if (entryForm) {
    entryForm.addEventListener('submit', async e => {
      e.preventDefault();
      if (!canSubmit('entry')) return;

      const formData = new FormData(entryForm);
      const payload = Object.fromEntries(formData.entries());

      try {
        const res = await authFetch(entryForm.action, {
          method: entryForm.method || 'POST',
          body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error('Network response not ok');

        const data = await res.json();

        if (data.status === 'ok') {

          showToast(data.message || 'Entry submitted!', 'success');
          entryForm.reset();

          // ---------------------- Progress toast using general-toast style ---------------------- //
          const spinnerToast = document.createElement('div');
          spinnerToast.className = 'stacked-toast';
          spinnerToast.style.display = 'inline-flex';
          spinnerToast.classList.add('toast-neutral');
          spinnerToast.style.alignItems = 'center';
          spinnerToast.style.gap = '10px';
          spinnerToast.innerHTML = `
            <span id="progress-text">Processing... 0%</span>
            <div class="spinner" style="border: 3px solid #ccc; border-top: 3px solid #333; border-radius: 50%; width: 18px; height: 18px; animation: spin 1s linear infinite;"></div>
          `;

          const toastContainer = document.querySelector("#general-toast-container");
          toastContainer.appendChild(spinnerToast);

          requestAnimationFrame(() => spinnerToast.classList.add('show'));

          if (!document.getElementById('spinner-style')) {
            const style = document.createElement('style');
            style.id = 'spinner-style';
            style.innerHTML = `
              @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            `;
            document.head.appendChild(style);
          }

          // ---------------------- Connect WebSocket ---------------------- //
          let crisisTriggered = false;

          const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
          const ws = new WebSocket(
            `${wsProtocol}://${window.location.host}/ws/progress/${data.entry_id}`
          );

          ws.onopen = () => console.log("WebSocket connected!");
          ws.onclose = () => console.log("WebSocket closed");
          ws.onerror = (err) => console.error("WebSocket error:", err);

          ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            console.log("WebSocket message received:", msg);

            // ---------------------- Crisis check (Option A) ---------------------- //
            if (msg.type === "crisis" && !crisisTriggered) {
              crisisTriggered = true;

              ws.close();

              spinnerToast.classList.remove('show');
              spinnerToast.classList.add('hide');
              setTimeout(() => spinnerToast.remove(), 400);

              openModal("crisis");
              return;
            }

            // ---------------------- Skip updates if crisis triggered ---------------------- //
            if (crisisTriggered) return;

            const progress = Math.min(Math.max(msg.progress || 0, 0), 1);
            const percent = Math.round(progress * 100);

            const progressText = document.getElementById("progress-text");
            if (progressText) {
              progressText.textContent = `Processing... ${percent}%`;
            }

            // ---------------------- Redirect when done ---------------------- //
            if (progress >= 1) {
              ws.close();

              spinnerToast.classList.remove('show');
              spinnerToast.classList.add('hide');
              setTimeout(() => spinnerToast.remove(), 400);

              const real_id = msg.real_id || data.entry_id;

              setTimeout(() => {
                window.location.href = `/submit-success?id=${real_id}`;
              }, 200);
            }
          };

        } else {
          showToast(data.message || 'Submission failed. Please try again.', 'error');
        }

      } catch (err) {
        console.error(err);
        showToast('Submission failed. Please try again.', 'error');
      }
    });
  }

});