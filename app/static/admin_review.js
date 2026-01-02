// ==========================================
// PeriDocs-code/app/static/admin_review.js 
// save-state 202601012210 (YYYYMMDDhhmm)
// ==========================================
let currentIndex = 0;
let reviewQueue = [];

// ---------------- Fetch wrapper ----------------
async function checkedFetch(url, opts={}) {
  const resp = await fetch(url, opts);
  if (!resp.ok) {
    let text = "<no response body>";
    try { text = await resp.text(); } catch (_) {}
    throw new Error(`${resp.status} ${resp.statusText}: ${text}`);
  }
  return resp;
}

// ---------------- Load queue ----------------
async function fetchReviewQueue() {
  const loadingToastId = showToast("Loading review queue...", "info", 0);
  try {
    const resp = await checkedFetch("/admin/review-queue-json");
    reviewQueue = await resp.json();
    currentIndex = 0;
    renderCard();
    dismissToast(loadingToastId);
  } catch(err) {
    dismissToast(loadingToastId);
    console.error("Failed to fetch review queue:", err);
    showToast(`Failed to load review queue: ${err.message}`, "error", 5000);
  }
}

// ---------------- Render card ----------------
function renderCard() {
  const card = reviewQueue[currentIndex];
  const titleEl = document.getElementById("card-title");
  const summaryEl = document.getElementById("card-summary");
  const metaEl = document.getElementById("card-meta");
  const detailsEl = document.getElementById("card-details");

  if (!card) {
    titleEl.innerText = "No more items";
    summaryEl.innerText = "";
    metaEl.innerHTML = "";
    detailsEl.style.display = "none";
    return;
  }

  titleEl.innerText = card.id;
  summaryEl.innerText = card.summary || "No summary available.";
  metaEl.innerHTML = "";
  for (const [k,v] of Object.entries(card.meta || {})) {
    const li = document.createElement("li");
    li.innerText = `${k}: ${JSON.stringify(v)}`;
    metaEl.appendChild(li);
  }
  detailsEl.style.display = "none";
}

// ---------------- Toggle details ----------------
document.getElementById("read-more-btn").addEventListener("click", () => {
  const details = document.getElementById("card-details");
  details.style.display = (details.style.display === "none") ? "block" : "none";
});

// ---------------- Swipe action ----------------
async function swipeAction(action) {
  const card = reviewQueue[currentIndex];
  if (!card) return;

  let endpoint;
  if (card.type === "precentroid") {
    endpoint = `/admin/precentroid/${card.id}/${action}`;
  } else if (card.type === "split_suggestion") {
    endpoint = `/admin/centroid/${card.id}/execute-split`;
  } else {
    console.warn("Unknown card type:", card.type);
    return;
  }

  const toastId = showToast(`${action}ing ${card.id}...`, "info", 0);
  try {
    await checkedFetch(endpoint, { method: "POST" });
    dismissToast(toastId);
    showToast(`${action.charAt(0).toUpperCase() + action.slice(1)}ed ${card.id}`, "success");
    currentIndex++;
    renderCard();
  } catch(err) {
    dismissToast(toastId);
    console.error(`Failed to ${action} ${card.id}:`, err);
    showToast(`Failed to ${action} ${card.id}: ${err.message}`, "error", 5000);
  }
}

// ---------------- Button bindings ----------------
document.getElementById("approve-btn").addEventListener("click", () => swipeAction("approve"));
document.getElementById("reject-btn").addEventListener("click", () => swipeAction("reject"));

// ---------------- Keyboard shortcuts ----------------
document.addEventListener("keydown", e => {
  if (e.key === "ArrowLeft") swipeAction("reject");
  if (e.key === "ArrowRight") swipeAction("approve");
});

// ---------------- Toast helpers ----------------
function showToast(message, type="info", duration=2500) {
  if (!window.showToast) { alert(message); return null; }
  return window.showToast(message, type, duration);
}
function dismissToast(toastId) {
  if (window.dismissToast) window.dismissToast(toastId);
}


// ---------------- Queue stats display ----------------
async function updateQueueStats() {
  const statsEl = document.getElementById("queue-stats");
  if (!statsEl) return;

  try {
    const resp = await fetch("/admin/review-queue-json");
    if (!resp.ok) throw new Error("Failed to fetch queue JSON");
    const data = await resp.json();
    statsEl.textContent = `Pending review items: ${data.length}`;
  } catch (err) {
    console.error("Failed to update queue stats:", err);
    statsEl.textContent = "Unable to load review queue stats.";
  }
}

// Call it after loading queue
document.addEventListener("DOMContentLoaded", () => {
  updateQueueStats();
});


// ---------------- Init ----------------
document.addEventListener("DOMContentLoaded", () => {
  fetchReviewQueue().catch(err => {
    console.error("Failed to initialize review queue:", err);
    showToast(`Failed to initialize: ${err.message}`, "error", 5000);
  });
});
