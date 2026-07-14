// base-html-responsiveness.js
// save-state 2026-05-11T15:27:50-04:00
// ==========================================

function updateNavPill() {
  const left = document.querySelector(".menu-group-left");
  const right = document.querySelector(".menu-group-right");
  const header = document.querySelector(".header-center");

  if (!left || !right || !header) return;

  const headerRect = header.getBoundingClientRect();
  const leftRect = left.getBoundingClientRect();
  const rightRect = right.getBoundingClientRect();

  // left edge of left group relative to header
  const leftEdge = leftRect.left - headerRect.left;

  // right edge of right group relative to header
  const rightEdge = rightRect.right - headerRect.left;

  const width = rightEdge - leftEdge;

  // write to CSS variables
  header.style.setProperty("--nav-pill-left", `${leftEdge}px`);
  header.style.setProperty("--nav-pill-width", `${width}px`);
}

window.addEventListener("load", updateNavPill);
window.addEventListener("resize", updateNavPill);


// clone existing menu (no duplication of HTML in templates)

const hamburger = document.querySelector(".header-hamburger-button");
const overlay = document.getElementById("mobileMenuOverlay");
const navSource = document.querySelector(".header-center");

function openMobileMenu() {
  if (!overlay || !navSource) return;
  // prevent duplicate rebuilds
  if (overlay.classList.contains("is-open")) return;

  const panel = overlay.querySelector(".mobile-menu-panel");

  
  panel.innerHTML = navSource.innerHTML;

  overlay.classList.add("is-open");
}

function closeMobileMenu() {
  overlay.classList.remove("is-open");
}


function toggleMobileMenu() {
  if (overlay?.classList.contains("is-open")) {
    closeMobileMenu();
  } else {
    openMobileMenu();
  }
}

hamburger?.addEventListener("click", toggleMobileMenu);

overlay?.addEventListener("click", (e) => {
  if (e.target === overlay) closeMobileMenu();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeMobileMenu();
  }
});

function forceDesktopCleanup() {
  // close mobile menu
  overlay?.classList.remove("is-open");

  // clear cloned DOM
  const panel = overlay?.querySelector(".mobile-menu-panel");
  if (panel) panel.innerHTML = "";

  // repair nav pill layout
  updateNavPill();
}

const mq = window.matchMedia("(max-aspect-ratio: 175/100)");

let isMobileMode = mq.matches;



mq.addEventListener("change", (e) => {
  const nowMobile = e.matches;

  // ENTERING DESKTOP MODE
  if (!nowMobile && isMobileMode) {
    forceDesktopCleanup();
  }

  // ENTERING MOBILE MODE
  if (nowMobile && !isMobileMode) {
    // optional: ensure header state is clean
    updateNavPill();
  }

  isMobileMode = nowMobile;
});

window.addEventListener("resize", () => {
  updateNavPill();

  // optional safety: if we're in desktop mode, ensure no mobile state leaks
  if (!mq.matches) forceDesktopCleanup();
});