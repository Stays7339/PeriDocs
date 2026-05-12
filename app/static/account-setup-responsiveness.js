// account-setup-responsiveness.js
// save-state 2026-05-12T110:40:00-04:00
// ==========================================

let pendingTOTPSetup = null;

async function createAccount() {

  if (pendingTOTPSetup !== null) {
    showToast("Bootstrap already started.", "error");
    return;
  }

  const username =
    document.getElementById("username").value.trim();

  const password =
    document.getElementById("password").value;

  const res = await authFetch("/auth/account/setup/start", {
    method: "POST",
    credentials: "same-origin",
    headers: authHeaders(),
    body: JSON.stringify({
      username,
      password
    })
  });

  const data = await res.json();

  if (!res.ok) {
    showToast(data.detail || "Bootstrap failed", "error");
    return;
  }

  pendingTOTPSetup = Object.freeze({
    setup_token: data.setup_token,
    username
  });

  document.getElementById("totp-section").style.display = "block";

  document.getElementById("totp-secret").textContent =
    data.totp_secret;

  const uri =
    `otpauth://totp/PeriDocs:${username}?secret=${data.totp_secret}&issuer=PeriDocs`;

  document.getElementById("totp-uri").textContent = uri;

  const qr = document.getElementById("qr");
  qr.src = "/auth/account/setup/qr?uri=" + encodeURIComponent(uri);
  qr.style.display = "block";
}


async function completeBootstrap() {

  if (!pendingTOTPSetup) {
    showToast("Missing bootstrap session", "error");
    return;
  }

  const submitted_totp_code =
    document.getElementById("bootstrap-totp-code").value;

  const res = await authFetch("/auth/account/setup/complete", {
    method: "POST",
    credentials: "same-origin",
    headers: authHeaders(),
    body: JSON.stringify({
      setup_token: pendingTOTPSetup.setup_token,
      submitted_totp_code
    })
  });

  const data = await res.json();

  if (!res.ok) {
    showToast(
      data.detail || "Verification failed",
      "error"
    );
    return;
  }

  showToast("Account created", "success");

  setTimeout(() => {
    window.location.href = "/auth/login";
  }, 1000);
}


function resetBootstrap() {

  pendingTOTPSetup = null;

  document.getElementById("totp-section").style.display = "none";
  document.getElementById("totp-secret").textContent = "";
  document.getElementById("totp-uri").textContent = "";
  document.getElementById("qr").style.display = "none";

  document.getElementById("username").value = "";
  document.getElementById("password").value = "";
  document.getElementById("bootstrap-totp-code").value = "";
}

document.addEventListener("DOMContentLoaded", () => {

  const createBtn =
    document.getElementById("create-account-btn");

  const completeBtn =
    document.getElementById("complete-bootstrap-btn");

  const usernameInput =
    document.getElementById("username");

  const passwordInput =
    document.getElementById("password");

  const totpInput =
    document.getElementById("bootstrap-totp-code");

  // ---------------- Create Account ---------------- //

  if (createBtn) {
    createBtn.addEventListener("click", async () => {

      createBtn.disabled = true;

      try {
        await createAccount();
      } finally {
        createBtn.disabled = false;
      }
    });
  }

  // Enter key from password field
  if (passwordInput) {
    passwordInput.addEventListener("keydown", async (e) => {

      if (e.key !== "Enter") return;

      e.preventDefault();

      if (createBtn?.disabled) return;

      createBtn.disabled = true;

      try {
        await createAccount();
      } finally {
        createBtn.disabled = false;
      }
    });
  }

  // ---------------- Complete Bootstrap ---------------- //

  if (completeBtn) {
    completeBtn.addEventListener("click", async () => {

      completeBtn.disabled = true;

      try {
        await completeBootstrap();
      } finally {
        completeBtn.disabled = false;
      }
    });
  }

  // Enter key from TOTP field
  if (totpInput) {
    totpInput.addEventListener("keydown", async (e) => {

      if (e.key !== "Enter") return;

      e.preventDefault();

      if (completeBtn?.disabled) return;

      completeBtn.disabled = true;

      try {
        await completeBootstrap();
      } finally {
        completeBtn.disabled = false;
      }
    });
  }

});