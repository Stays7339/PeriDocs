// persistence-opt-in.js 
// save-state: 2026-07-13T22:29-04:00
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  const optInToggle = document.getElementById("opt-in-toggle");
  const optInInput = document.getElementById("opt-in-input");
  
  if (optInToggle && optInInput) {
    const updateOptInState = (isOn) => {
      optInToggle.setAttribute("aria-checked", isOn ? "true" : "false");
      optInToggle.setAttribute("data-state", isOn ? "on" : "off");
      optInInput.value = isOn ? "true" : "false";
      
      // Target the text container inside the toggle button
      const label = optInToggle.querySelector(".toggle-label");
      if (label) {
        label.textContent = isOn ? "Current Setting: Yes" : "Current Setting: No";
      }
    };

    // Initialize the text and state correctly on initial page load
    const isInitiallyOn = optInToggle.getAttribute("data-state") === "on";
    updateOptInState(isInitiallyOn);
    
    // Toggle state on click interactions
    optInToggle.addEventListener("click", () => {
      const isCurrentlyChecked = optInToggle.getAttribute("aria-checked") === "true";
      updateOptInState(!isCurrentlyChecked);
    });
  } else {
    // This will log an error in your browser console if the JS can't find your HTML
    console.error("Persistence Script Error: 'opt-in-toggle' or 'opt-in-input' elements were not found on this page.");
  }
});