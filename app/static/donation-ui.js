// ==========================================
// donation-ui.js
// PeriDocs Stripe Donation Frontend Module
// Works alongside peridocs-misc-ux.js
// save-state 2026-05-03T23:10:40-04:00
// ==========================================

/*
  DEPENDENCIES (must exist globally via peridocs-misc-ux.js):
  - showToast(message, type)
  - general-toast-container DOM element
*/

/* =========================
   CONFIGURATION
========================= */

const DonationAPI = {
  subscriptionEndpoint: "/donation/create-subscription",
  onetimeEndpoint: "/donation/create-onetime"
};

/* =========================
   CORE REQUEST HANDLER
========================= */

async function createDonationSession(endpoint, amount, type = "donation") {
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ amount })
    });

    const data = await res.json();

    // -------------------------
    // Error handling (standardized contract)
    // -------------------------
    if (!res.ok || data.status === "error") {
      showToast(
        data.message || "Donation request failed.",
        "error"
      );
      return null;
    }

    return data;

  } catch (err) {
    console.error("Donation request failed:", err);
    showToast("Network error. Please try again.", "error");
    return null;
  }
}

/* =========================
   SUBSCRIPTION FLOW
========================= */

async function startMonthlyDonation(amount) {
  const data = await createDonationSession(
    DonationAPI.subscriptionEndpoint,
    amount,
    "subscription"
  );

  if (!data) return;

  showToast(
    data.message || "Redirecting to secure monthly checkout...",
    "success"
  );

  // slight UX delay so toast is visible
  setTimeout(() => {
    window.location.href = data.url;
  }, 500);
}

/* =========================
   ONE-TIME FLOW
========================= */

async function startOneTimeDonation(amount) {
  const data = await createDonationSession(
    DonationAPI.onetimeEndpoint,
    amount,
    "onetime"
  );

  if (!data) return;

  showToast(
    data.message || "Redirecting to secure checkout...",
    "success"
  );

  setTimeout(() => {
    window.location.href = data.url;
  }, 500);
}


function valuecheckOneTimeDonation() {
  const val = parseFloat(document.getElementById("onetime-amount").value);

  if (!val || val <= 0) {
    showToast("Please enter a valid amount.", "error");
    return;
  }

  startOneTimeDonation(val);
}

function valuecheckMonthlyDonation() {
  const val = parseFloat(document.getElementById("monthly-amount").value);

  if (!val || val <= 0) {
    showToast("Please enter a valid amount.", "error");
    return;
  }

  startMonthlyDonation(val);
}

/* =========================
   GLOBAL EXPORTS
   (useful for inline buttons)
========================= */

window.PeriDocsDonations = {
  valuecheckOneTimeDonation,
  valuecheckMonthlyDonation,
  startOneTimeDonation,
  startMonthlyDonation
};