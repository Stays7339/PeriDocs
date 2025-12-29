// ==========================================
// PeriDocs-code/app/static/admin_review.js 
// save-state 202512291254 (YYYYMMDDhhmm)
// ==========================================

let currentIndex = 0;
let precentroids = [];

/* --------------------------------------------------
   Loud fetch wrapper
   -------------------------------------------------- */
async function checkedFetch(url, opts = {}) {
  const resp = await fetch(url, opts);

  if (!resp.ok) {
    let text = "";
    try {
      text = await resp.text();
    } catch (_) {
      text = "<no response body>";
    }
    throw new Error(`${resp.status} ${resp.statusText}: ${text}`);
  }

  return resp;
}

/* --------------------------------------------------
   Data loading
   -------------------------------------------------- */
async function fetchPrecentroids() {
  // Show loading toast while fetching
  const loadingToastId = showToast("Loading precentroids...", "info", 0); // 0 duration = manual removal

  try {
    const resp = await checkedFetch("/admin/review-queue-json");
    precentroids = await resp.json();
    currentIndex = 0;
    renderCard();
    dismissToast(loadingToastId);
  } catch (err) {
    dismissToast(loadingToastId);
    console.error("Failed to fetch precentroids:", err);
    showToast(`Failed to load precentroids: ${err.message}`, "error", 5000);
  }
}

/* --------------------------------------------------
   Rendering
   -------------------------------------------------- */
function renderCard() {
  const card = precentroids[currentIndex];

  if (!card) {
    document.getElementById("card-title").innerText = "No more precentroids";
    document.getElementById("card-summary").innerText = "";
    document.getElementById("card-meta").innerHTML = "";
    document.getElementById("card-details").style.display = "none";
    return;
  }

  document.getElementById("card-title").innerText = card.id;
  document.getElementById("card-summary").innerText =
    card.summary || "No summary available.";

  const metaList = document.getElementById("card-meta");
  metaList.innerHTML = "";
  for (const [key, val] of Object.entries(card.meta || {})) {
    const li = document.createElement("li");
    li.innerText = `${key}: ${val}`;
    metaList.appendChild(li);
  }

  document.getElementById("card-details").style.display = "none";
}

/* --------------------------------------------------
   UI controls
   -------------------------------------------------- */
document
  .getElementById("read-more-btn")
  .addEventListener("click", () => {
    const details = document.getElementById("card-details");
    details.style.display =
      details.style.display === "none" ? "block" : "none";
  });

/* --------------------------------------------------
   Actions
   -------------------------------------------------- */
async function swipeAction(action) {
  const card = precentroids[currentIndex];
  if (!card) return;

  const endpoint =
    action === "approve"
      ? `/admin/precentroid/${card.id}/approve`
      : `/admin/precentroid/${card.id}/reject`;

  const actionToastId = showToast(
    `${action === "approve" ? "Approving" : "Rejecting"} ${card.id}...`,
    "info",
    0
  ); // Manual removal toast

  try {
    await checkedFetch(endpoint, { method: "POST" });
    dismissToast(actionToastId);
    showToast(
      `${action === "approve" ? "Approved" : "Rejected"} ${card.id}`,
      "success"
    );
    currentIndex++;
    renderCard();
  } catch (err) {
    dismissToast(actionToastId);
    console.error(`Failed to ${action} ${card.id}:`, err);
    showToast(
      `Failed to ${action} ${card.id}: ${err.message}`,
      "error",
      5000
    );
  }
}

/* --------------------------------------------------
   Button bindings
   -------------------------------------------------- */
document
  .getElementById("approve-btn")
  .addEventListener("click", () => swipeAction("approve"));

document
  .getElementById("reject-btn")
  .addEventListener("click", () => swipeAction("reject"));

/* --------------------------------------------------
   Keyboard shortcuts
   -------------------------------------------------- */
document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") swipeAction("reject");
  if (e.key === "ArrowRight") swipeAction("approve");
});

/* --------------------------------------------------
   Toast helpers (integrated with peridocs-ui.js)
   -------------------------------------------------- */
function showToast(message, type = "info", duration = 2500) {
  if (!window.showToast) {
    console.warn(
      "peridocs-ui.js toast system not loaded. Falling back to alert."
    );
    alert(message);
    return null;
  }
  // window.showToast from peridocs-ui.js
  return window.showToast(message, type, duration);
}

function dismissToast(toastId) {
  // This assumes peridocs-ui.js returns an ID you can dismiss; if not, no-op
  if (window.dismissToast) window.dismissToast(toastId);
}

/* --------------------------------------------------
   Init
   -------------------------------------------------- */
document.addEventListener("DOMContentLoaded", () => {
  if (typeof fetchPrecentroids === "function") {
    fetchPrecentroids().catch((err) => {
      console.error("Admin review failed to initialize:", err);
      showToast(`Admin review failed to initialize: ${err.message}`, "error", 5000);
    });
  }
});
