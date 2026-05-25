// account-signup-responsiveness.js
// save-state 2026-05-20T19:30:20:00-04:00
// ==========================================

let pendingTOTPSetup = null;

async function createAccount() {

  console.log("createAccount ENTERED");

  if (pendingTOTPSetup !== null) {
    showToast("AccountSetup already started.", "error");
    return;
  }

  const username =
    document.getElementById("username").value.trim();

  const password =
    document.getElementById("password").value;

  console.log("ABOUT TO FETCH");

  const res = await authFetch("/account/setup/start", {
    method: "POST",
    credentials: "same-origin",
    headers: authHeaders(),
    body: JSON.stringify({
      username,
      password
    })
  });

  console.log("FETCH RESOLVED:", res);

  const data = await res.json();

  if (!res.ok) {
    showToast(data.detail || "AccountSetup failed", "error");
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
  qr.src = "/account/setup/qr?uri=" + encodeURIComponent(uri);
  qr.style.display = "block";
}


async function completeAccountSetup() {

  if (!pendingTOTPSetup) {
    showToast("Missing AccountSetup session", "error");
    return;
  }

  const totp_code =
    document.getElementById("setup-totp-code").value;

  const res = await authFetch("/account/setup/complete", {
    method: "POST",
    credentials: "same-origin",
    headers: authHeaders(),
    body: JSON.stringify({
      setup_token: pendingTOTPSetup.setup_token,
      totp_code
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
    window.location.href = "/signin";
  }, 1000);
}


function resetAccountSetup() {

  pendingTOTPSetup = null;

  document.getElementById("totp-section").style.display = "none";
  document.getElementById("totp-secret").textContent = "";
  document.getElementById("totp-uri").textContent = "";
  document.getElementById("qr").style.display = "none";

  document.getElementById("username").value = "";
  document.getElementById("password").value = "";
  document.getElementById("setup-totp-code").value = "";
}

document.addEventListener("DOMContentLoaded", () => {

  const createBtn = document.getElementById("create-account-btn");

  console.log("DOM ready");
  console.log("createBtn found:", createBtn);

  const completeBtn =
    document.getElementById("complete-account-creation-btn");

  const usernameInput =
    document.getElementById("username");

  const passwordInput =
    document.getElementById("password");

  const totpInput =
    document.getElementById("setup-totp-code");

  // ---------------- Create Account ---------------- //

  if (createBtn) {
    createBtn.addEventListener("click", async () => {
      
      console.log("CREATE BUTTON CLICKED");
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

  // ---------------- Complete AccountSetup ---------------- //

  if (completeBtn) {
    completeBtn.addEventListener("click", async () => {

      completeBtn.disabled = true;

      try {
        await completeAccountSetup();
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
        await completeAccountSetup();
      } finally {
        completeBtn.disabled = false;
      }
    });
  }

});