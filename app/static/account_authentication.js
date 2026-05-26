// account_authentication.js
// save-state 2026-05-26T15:14:55-04:00
// centralized authentication helpers (PeriDocs)

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return null;
}

/**
 * Returns headers that are safe for authenticated requests.
 * Includes CSRF protection when cookie exists.
 */
async function authFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});

  const csrf = getCookie("csrf_token");
  if (csrf) {
    headers.set("X-CSRF-Token", csrf);
  }

  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(url, {
    ...options,
    credentials: "include",
    headers
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