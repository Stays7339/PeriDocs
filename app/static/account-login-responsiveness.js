// account-login-responsiveness.js
// save-state 2026-05-11T15:36:40-04:00
// ==========================================



async function login() {
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;
  const totp_code = document.getElementById("totp").value;

  const res = await authFetch("/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: authHeaders(),
    body: JSON.stringify({
      username,
      password,
      totp_code
    })
  });

  const data = await res.json();

  if (data.status === "ok") {
    window.location.href = "/";
  } else {
    showToast("Login failed", "error");
  }
}