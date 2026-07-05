// admin_review_ux.js
// save-state 2026-07-05T12:27-04:00
// ==========================================

const reviewListContainer = document.getElementById("review-list");
let reviewQueue = [];

// -----------------------------
// REVIEW QUEUE
// -----------------------------
async function fetchQueue() {
  const res = await authFetch("/admin/review-queue");
  reviewQueue = await res.json();
  renderQueue();

  const params = new URLSearchParams(window.location.search);
  const pid = params.get("precentroid");

}

function renderQueue() {
  reviewListContainer.innerHTML = "";

  const template = document.getElementById("review-item-template");

  reviewQueue.forEach(item => {
    const el = template.content.cloneNode(true).firstElementChild;

    el.dataset.id = item.id;

    el.querySelector(".clickable").textContent = item.id;
    el.querySelector(".summary").textContent = item.summary;
    el.querySelector(".entry-count").textContent = item.meta.entry_count;

    const expandBtn = el.querySelector(".expand-btn");
    const approveBtn = el.querySelector(".approve-btn");
    const rejectBtn = el.querySelector(".reject-btn");

    expandBtn.addEventListener("click", () => toggleEntries(item.id));

    approveBtn.addEventListener("click", async () => {
      const description_from_human_moderator =
        prompt("Enter description_from_human_moderator:");
      const title_from_human_moderator =
        prompt("Enter title_from_human_moderator:");

      if (!description_from_human_moderator || !title_from_human_moderator) return;

      await authFetch("/admin/approve-precentroid", {
        method: "POST",
        body: JSON.stringify({
          id: item.id,
          description_from_human_moderator,
          title_from_human_moderator
        })
      });

      await fetchQueue();
      await loadConceptList();
    });

    rejectBtn.addEventListener("click", async () => {
      await authFetch("/admin/reject-precentroid", {
        method: "POST",
        body: JSON.stringify({ id: item.id })
      });

      fetchQueue();
    });

    reviewListContainer.appendChild(el);
  });
}

// -----------------------------
// ENTRY VIEWING
// -----------------------------
async function toggleEntries(precentroidId) {
  const el = [...reviewListContainer.children]
    .find(e => e.dataset.id === precentroidId);

  if (!el) return;

  const entriesContainer = el.querySelector(".entries-container");

  if (entriesContainer.style.display === "block") {
    entriesContainer.style.display = "none";
    return;
  }

  const entryIds =
    reviewQueue.find(p => p.id === precentroidId)?.meta.entry_ids || [];

  const res = await authFetch("/admin/entries-safe-text", {
    method: "POST",
    body: JSON.stringify({ entry_ids: entryIds })
  });

  const data = await res.json();

  entriesContainer.innerHTML = "";

  for (const e of data.entries) {
    const p = document.createElement("p");
    p.className = "matched-snippet";
    p.textContent = e.safe_text;
    entriesContainer.appendChild(p);
  }

  entriesContainer.style.display = "block";
  el.scrollIntoView({ behavior: "smooth" });

  const url = new URL(window.location);
  url.searchParams.set("precentroid", precentroidId);
  history.pushState({ precentroid: precentroidId }, "", url);
}

// -----------------------------
// BACK NAVIGATION
// -----------------------------
window.addEventListener("popstate", event => {
  const pid = event.state?.precentroid;

  if (pid) {
  
  } else {
    reviewQueue.forEach(item => {
      const el = [...reviewListContainer.children]
        .find(e => e.dataset.id === item.id);

      if (el) {
        el.querySelector(".entries-container").style.display = "none";
      }
    });
  }
});

// =====================================================
// HEURISTICS + TYPEAHEAD SYSTEM
// =====================================================

const givensContainer = document.getElementById("givens-container");
const outputsContainer = document.getElementById("outputs-container");

let CONCEPTS = [];
let activeIndex = -1;

const resourceConceptsContainer = document.getElementById("resource-concepts-container");

function addResourceConcept(value = "") {
  const div = document.createElement("div");
  div.style.marginGroup = "6px 0";
  div.innerHTML = `
    <input class="input resource-concept-input" placeholder="Search concept or cluster tag..." value="${value}" style="width:100%; margin-top:4px;">
  `;
  resourceConceptsContainer.appendChild(div);
  
  // Directly bind into your existing Typeahead system
  attachTypeahead(div.querySelector(".resource-concept-input"));
}

async function submitResource() {
  const title = document.getElementById("resource-title").value.trim();
  const url = document.getElementById("resource-url").value.trim();
  const description = document.getElementById("resource-desc").value.trim();
  
  const assigned_concepts = [...resourceConceptsContainer.querySelectorAll("input")]
    .map(i => i.value.trim())
    .filter(Boolean);

  if (!title || !url || assigned_concepts.length === 0) {
    alert("Please populate Title, URL, and at least one linked concept match.");
    return;
  }

  try {
    const res = await authFetch("/admin/create-resource", {
      method: "POST",
      body: JSON.stringify({ title, url, description, assigned_concepts })
    });
    
    const result = await res.json();
    if (res.ok) {
      alert("External resource mapped and synchronized successfully.");
      // Clear inputs safely
      document.getElementById("resource-title").value = "";
      document.getElementById("resource-url").value = "";
      document.getElementById("resource-desc").value = "";
      resourceConceptsContainer.innerHTML = "";
    } else {
      alert(`Provision error: ${result.detail || "Server rejected submission."}`);
    }
  } catch (err) {
    alert(`Network transmission failure: ${err.message}`);
  }
}

// -----------------------------
// INPUT CREATION
// -----------------------------
function addGiven(value = "") {
  const div = document.createElement("div");
  div.innerHTML =
    `<input class="input concept-input" placeholder="Given concept..." value="${value}">`;

  givensContainer.appendChild(div);
  attachTypeahead(div.querySelector("input"));
}

function addOutput(concept = "", likelihood = "") {
  const div = document.createElement("div");
  div.innerHTML = `
    <input class="input concept-input" placeholder="Output concept..." value="${concept}">
    <input class="input" placeholder="Likelihood (0-1 or %)" value="${likelihood}">
  `;

  outputsContainer.appendChild(div);
  attachTypeahead(div.querySelector(".concept-input"));
}

// -----------------------------
// SUBMIT (backend normalization only)
// -----------------------------
async function submitHeuristic() {
  const givens = [...givensContainer.querySelectorAll("input")]
    .map(i => i.value.trim())
    .filter(Boolean);

  const outputs = [...outputsContainer.children]
    .map(div => {
      const inputs = div.querySelectorAll("input");

      return {
        concept: inputs[0].value.trim(),
        likelihood: parseFloat(inputs[1].value)
      };
    })
    .filter(o => o.concept);

  const res = await authFetch("/admin/create-heuristic", {
    method: "POST",
    body: JSON.stringify({ givens, outputs })
  });

  await res.json();
  alert("Heuristic saved");

  givensContainer.innerHTML = "";
  outputsContainer.innerHTML = "";
}

// -----------------------------
// LOAD CONCEPTS (backend source of truth)
// -----------------------------
async function loadConceptList() {
  const res = await authFetch("/admin/concepts");
  const data = await res.json();
  CONCEPTS = data.concepts;
}

loadConceptList();

// =====================================================
// TYPEAHEAD SYSTEM
// =====================================================

function conceptMatches(input, concept) {
  const q = input.toLowerCase().trim();

  const label = concept.label.toLowerCase();
  const id = concept.id.toLowerCase();
  const idLoose = id.replaceAll("_", " ");

  return (
    label.includes(q) ||
    id.includes(q) ||
    idLoose.includes(q)
  );
}

function attachTypeahead(inputEl) {
  const dropdown = document.createElement("div");
  dropdown.className = "typeahead-dropdown";
  inputEl.parentNode.appendChild(dropdown);

  let localIndex = -1;

  inputEl.addEventListener("input", () => {
    const value = inputEl.value;

    const matches = CONCEPTS
      .filter(c => conceptMatches(value, c))
      .slice(0, 10);

    dropdown.innerHTML = matches.map((c, i) => `
      <div class="typeahead-item" data-index="${i}">
        ${c.label} (${c.id})
      </div>
    `).join("");

    localIndex = -1;
  });

  inputEl.addEventListener("keydown", (e) => {
    const items = dropdown.querySelectorAll(".typeahead-item");
    if (!items.length) return;

    if (e.key === "ArrowDown") {
      localIndex = Math.min(localIndex + 1, items.length - 1);
      updateActive(items, localIndex);
      e.preventDefault();
    }

    if (e.key === "ArrowUp") {
      localIndex = Math.max(localIndex - 1, 0);
      updateActive(items, localIndex);
      e.preventDefault();
    }

    if (e.key === "Enter" && localIndex >= 0) {
      inputEl.value = items[localIndex].innerText;
      dropdown.innerHTML = "";
      e.preventDefault();
    }
  });

  dropdown.addEventListener("click", (e) => {
    const item = e.target.closest(".typeahead-item");
    if (!item) return;

    inputEl.value = item.innerText;
    dropdown.innerHTML = "";
  });
}

// correct index scoping
function updateActive(items, index) {
  items.forEach(el => el.classList.remove("active"));

  if (items[index]) {
    items[index].classList.add("active");
  }
}

// =====================================================
// SAFE WIRING LAYER (NEW)
// =====================================================

document.addEventListener("DOMContentLoaded", () => {
  // signout
  const signoutBtn = document.getElementById("signout-btn");
  if (signoutBtn) {
    signoutBtn.addEventListener("click", () => signout());
  }

  // heuristics buttons
  const addGivenBtn = document.getElementById("add-given-btn");
  if (addGivenBtn) {
    addGivenBtn.addEventListener("click", () => addGiven());
  }

  const addOutputBtn = document.getElementById("add-output-btn");
  if (addOutputBtn) {
    addOutputBtn.addEventListener("click", () => addOutput());
  }

  const submitBtn = document.getElementById("submit-heuristic-btn");
  if (submitBtn) {
    submitBtn.addEventListener("click", () => submitHeuristic());
  }

  document.getElementById("add-resource-concept-btn")?.addEventListener("click", () => addResourceConcept());
  document.getElementById("submit-resource-btn")?.addEventListener("click", () => submitResource());

  // initial load
  fetchQueue();
});