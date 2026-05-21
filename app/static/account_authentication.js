// account_authentication.js
// save-state 2026-05-20T22:29:50-04:00
// centralized authentication helpers (PeriDocs)

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return null;
}

console.log("cookie raw:", document.cookie);
console.log("csrf parsed:", getCookie("csrf_token"));

/**
 * Returns headers that are safe for authenticated requests.
 * Includes CSRF protection when cookie exists.
 */
function authHeaders(extra = {}) {
  const csrf = getCookie("csrf_token");

  return {
    "Content-Type": "application/json",
    ...(csrf ? { "X-CSRF-Token": csrf } : {}),
    ...extra
  };
}

/**
 * Fetch wrapper that enforces:
 * - same-origin cookies
 * - CSRF header injection
 */
async function authFetch(url, options = {}) {
  return fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: authHeaders(options.headers || {})
  });
}

/**
 * Central logout function
 */
async function logout() {
  await authFetch("/signout", { method: "POST" });
  window.location.href = "/signout";
}