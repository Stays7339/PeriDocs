// persistence-opt-in.js 
// save-state: 2026-07-14T15:52-04:00
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  const optInToggle = document.getElementById("opt-in-toggle");
  const optInInput = document.getElementById("opt-in-input");
  
  // Define a distinct storage key mirroring the consent state pattern
  const OPT_IN_SESSION_KEY = "PeriDocs_PermanentPostOptIn";

  if (optInToggle && optInInput) {
    const updateOptInState = (isOn) => {
      // 1. Update visual and DOM properties
      optInToggle.setAttribute("aria-checked", isOn ? "true" : "false");
      optInToggle.setAttribute("data-state", isOn ? "on" : "off");
      optInInput.value = isOn ? "true" : "false";
      
      // 2. Commit state to active session storage memory
      sessionStorage.setItem(OPT_IN_SESSION_KEY, isOn ? "true" : "false");
      
      // 3. Update text container inside the toggle element safely
      const label = optInToggle.querySelector(".toggle-label");
      if (label) {
        label.textContent = isOn ? "Current Setting: Yes" : "Current Setting: No";
      }
    };

    // 4. Resolve the starting preference: check session memory first, 
    // falling back to the page's HTML template attribute if empty.
    const sessionStoredState = sessionStorage.getItem(OPT_IN_SESSION_KEY);
    let isInitiallyOn;
    
    if (sessionStoredState !== null) {
      isInitiallyOn = sessionStoredState === "true";
    } else {
      isInitiallyOn = optInToggle.getAttribute("data-state") === "on";
    }
    
    // 5. Initialize layout using the resolved state
    updateOptInState(isInitiallyOn);
    
    // 6. Bind interactive toggle listeners
    optInToggle.addEventListener("click", () => {
      const isCurrentlyChecked = optInToggle.getAttribute("aria-checked") === "true";
      updateOptInState(!isCurrentlyChecked);
    });
  } else {
    console.error("Persistence Script Error: 'opt-in-toggle' or 'opt-in-input' missing from template.");
  }
});