// account-login-responsiveness.js
// save-state 2026-05-20T20:25:15-04:00
// ==========================================

async function login() {
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;
  const totp_code = document.getElementById("totp").value;

  const res = await authFetch("/signin", {
    method: "POST",
    body: JSON.stringify({
      username,
      password,
      totp_code
    })
  });

  const text = await res.text();

  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    console.error("Non-JSON response from server:", text);
    showToast("Server error during login", "error");
    return;
  }

  if (data.status === "ok") {
    window.location.href = "/";
  } else {
    showToast(data.detail || "Login failed", "error");
  }
}

document.addEventListener("DOMContentLoaded", () => {

  const loginButton =
    document.getElementById("login-button");

  if (loginButton) {

    loginButton.addEventListener("click", async () => {

      loginButton.disabled = true;

      try {
        await login();
      } finally {
        loginButton.disabled = false;
      }

    });

  }

});