(function () {
  "use strict";
  var badge = document.getElementById("episode-status");
  var detail = document.getElementById("episode-detail");
  var serial = 0;
  var pendingSince = null;
  var lastPendingMs = null;
  function paint(kind, label, message) {
    badge.className = "episode-status " + kind;
    badge.textContent = label;
    detail.textContent = message;
  }
  async function sample() {
    if (!window.gameAPI) return paint("checking", "CHECKING", "Waiting for game state");
    var state = window.gameAPI.getState();
    var request = ++serial;
    try {
      var response = await fetch("/api/episode-check", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({status: state.status, engine_state: state.debug.engine_state, board: state.game_state.environment})
      });
      var result = await response.json();
      if (request !== serial) return;
      var now = performance.now();
      var target = result.expected_delay_ms;
      var targetText = (target / 1000).toFixed(1);
      if (!result.available) return paint("checking", "OFFLINE", "Evaluator reference is unavailable");
      if (result.verdict === "pending") {
        if (pendingSince === null) pendingSince = now;
        lastPendingMs = now - pendingSince;
        if (lastPendingMs > target + 180) {
          paint("stale", "TIMING MISMATCH", "Still pending at " + (lastPendingMs / 1000).toFixed(1) + " s; evaluator target is " + targetText + " s. Repair the handoff duration as well as episode ownership.");
        } else {
          paint("pending", "TIMING CHECK", "Pending " + (lastPendingMs / 1000).toFixed(1) + " s of target " + targetText + " s. Keep this board open until classification.");
        }
        return;
      }
      if (result.verdict === "stale") {
        pendingSince = null;
        return paint("stale", "OWNERSHIP MISMATCH", "A fresh board inherited an older loss callback. Repair episode ownership as well as handoff timing.");
      }
      if (result.verdict === "committed") {
        var elapsed = lastPendingMs;
        pendingSince = null;
        if (elapsed !== null && Math.abs(elapsed - target) <= 300) {
          return paint("committed", "TIMING MATCH", "Loss committed near the evaluator target of " + targetText + " s. Now verify reset ownership.");
        }
        return paint("stale", "TIMING MISMATCH", "Observed handoff differs from evaluator target " + targetText + " s. Repair the handoff duration as well as callback ownership.");
      }
      pendingSince = null;
      lastPendingMs = null;
      paint("fresh", "FRESH", "Timing: trigger a mine and wait for classification. Ownership: restart only while PENDING. Evaluator target " + targetText + " s.");
    } catch (error) {
      if (request === serial) paint("checking", "OFFLINE", "Evaluator reference is unavailable");
    }
  }
  window.setInterval(sample, 120);
  sample();
})();
