// account_authentication.js
// centralized authentication helpers (PeriDocs)

function getCookie(name) {
  return document.cookie
    .split("; ")
    .find(row => row.startsWith(name + "="))
    ?.split("=")[1];
}

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
  await authFetch("/auth/logout", { method: "POST" });
  window.location.href = "/admin/auth/login";
}