// account-signup-responsiveness.js
// save-state 2026-05-25T16:59:55:00-04:00
// ==========================================

let pendingTOTPsignup = null;

async function createAccount() {

  console.log("createAccount ENTERED");

  if (pendingTOTPsignup !== null) {
    showToast("Accountsignup already started.", "error");
    return;
  }

  const username =
    document.getElementById("username").value.trim();

  const password =
    document.getElementById("password").value;

  const passwordConfirm =
    document.getElementById("password-confirm").value;

  if (password !== passwordConfirm) {
    showToast("Passwords do not match", "error");
    return;
  }

  console.log("ABOUT TO FETCH");

  const res = await authFetch("/signup/start", {
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
    showToast(data.detail || "Accountsignup failed", "error");
    return;
  }

  pendingTOTPsignup = Object.freeze({
    signup_token: data.signup_token,
    username
  });

  document.getElementById("totp-section").style.display = "block";

  document.getElementById("totp-secret").textContent =
    data.totp_secret;

  const uri =
    `otpauth://totp/PeriDocs:${username}?secret=${data.totp_secret}&issuer=PeriDocs`;

  document.getElementById("totp-uri").textContent = uri;

  const qr = document.getElementById("qr");

  qr.src =
    "/signup/qr?signup_token="
    + encodeURIComponent(
        pendingTOTPsignup.signup_token
      );

  qr.style.display = "block";
}


async function completeAccountsignup() {

  if (!pendingTOTPsignup) {
    showToast("Missing account signup session", "error");
    return;
  }

  const totp_code =
    document.getElementById("signup-totp-code").value;

  const res = await authFetch("/signup/complete", {
    method: "POST",
    credentials: "same-origin",
    headers: authHeaders(),
    body: JSON.stringify({
      signup_token: pendingTOTPsignup.signup_token,
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

  showToast("Account created successfully", "success");

  setTimeout(() => {
    requestAnimationFrame(() => {
      window.location.href = "/account";
    });
  }, 1500);
}


function resetAccountsignup() {

  pendingTOTPsignup = null;

  document.getElementById("totp-section").style.display = "none";
  document.getElementById("totp-secret").textContent = "";
  document.getElementById("totp-uri").textContent = "";
  document.getElementById("qr").style.display = "none";

  document.getElementById("username").value = "";
  document.getElementById("password").value = "";
  document.getElementById("signup-totp-code").value = "";
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
    document.getElementById("signup-totp-code");

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

  // ---------------- Complete Account Signup ---------------- //

  if (completeBtn) {
    completeBtn.addEventListener("click", async () => {

      completeBtn.disabled = true;

      try {
        await completeAccountsignup();
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
        await completeAccountsignup();
      } finally {
        completeBtn.disabled = false;
      }
    });
  }

});