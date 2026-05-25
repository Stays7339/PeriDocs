// account_authentication.js
// save-state 2026-05-25T16:53:05-04:00
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
 * Central signout function
 */
async function signout() {

  const response = await authFetch(
    "/signout",
    {
      method: "POST"
    }
  );

  if (!response.ok) {

    console.error(
      "signout failed:",
      response.status
    );

    return;
  }

  window.location.href = "/signin";
}

document.addEventListener(
  "DOMContentLoaded",
  () => {

    const signoutButton =
      document.getElementById("signout-btn");

    if (!signoutButton) {
      return;
    }

    signoutButton.addEventListener(
      "click",
      async () => {

        try {

          await signout();

        } catch (error) {

          console.error(
            "Signout error:",
            error
          );
        }
      }
    );
  }
);

document.addEventListener(
  "DOMContentLoaded",
  () => {

    const deleteAccountButton =
      document.getElementById("delete-account-btn");

    if (!deleteAccountButton) {
      return;
    }

    deleteAccountButton.addEventListener(
      "click",
      async () => {

        const password = prompt(
          "Just to let you know, account deletion is permanent and irreversible.\n\nIf you'd like to delete your account, please provide your current password below:"
        );

        if (!password) {
          return;
        }

        try {

          const response = await authFetch("/account/delete", {
            method: "POST",
            body: JSON.stringify({ password })
          });

          const data = await response.json().catch(() => ({}));

          if (!response.ok) {

            const message =
              data.detail || "Account deletion failed";

            showToast(message, "error");

            console.error(
              "Account deletion failed:",
              response.status
            );

            return;
          }

          showToast("Account deleted successfully", "success");

          setTimeout(() => {
            requestAnimationFrame(() => {
              window.location.href = "/";
            });
          }, 1500);

        } catch (error) {

          console.error(
            "Delete account error:",
            error
          );

          showToast(
            "Account deletion failed",
            "error"
          );
        }
      }
    );
  }
);