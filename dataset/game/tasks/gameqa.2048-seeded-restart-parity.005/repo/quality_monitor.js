(function () {
  "use strict";

  var badge = document.getElementById("opening-parity-status");
  var detail = document.getElementById("opening-parity-detail");
  var requestSerial = 0;

  function paint(kind, label, message) {
    badge.className = "opening-parity-status " + kind;
    badge.textContent = label;
    detail.textContent = message;
  }

  async function sample() {
    if (!window.gameAPI || typeof window.gameAPI.getState !== "function") {
      paint("checking", "CHECKING", "Waiting for the game state");
      return;
    }

    var state = window.gameAPI.getState();
    if (!state || !state.game_state || !state.game_state.environment) {
      paint("checking", "CHECKING", "Waiting for the opening board");
      return;
    }

    var serial = ++requestSerial;
    try {
      var response = await fetch("/api/runtime-check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seed: state.seed,
          board: state.game_state.environment
        })
      });
      var result = await response.json();
      if (serial !== requestSerial) return;
      if (!result.available) {
        paint("unavailable", "UNAVAILABLE", "Evaluator reference is offline");
      } else if (result.match) {
        paint("match", "MATCH", "Board matches the seeded opening");
      } else {
        paint("mismatch", "MISMATCH", "Board differs from the seeded opening");
      }
    } catch (error) {
      if (serial === requestSerial) {
        paint("unavailable", "UNAVAILABLE", "Evaluator reference is offline");
      }
    }
  }

  window.setInterval(sample, 120);
  sample();
})();
