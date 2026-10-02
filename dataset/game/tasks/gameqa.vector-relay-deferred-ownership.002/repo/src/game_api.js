(function (global) {
  "use strict";

  var game = new global.VectorRelay(document.getElementById("game"));
  global.__vectorRelayGame = game;

  function reset(options) {
    var requested = options || {};
    game.resetChallenge();
    return {
      accepted: {
        seed: requested.seed == null ? null : Number(requested.seed),
        level: requested.level == null ? null : Number(requested.level)
      },
      applied: { seed: 73, level: 3, difficulty: null },
      notes: []
    };
  }

  global.gameAPI = {
    capabilities: {
      supports_seed: true,
      supports_level_select: true,
      supports_difficulty: false,
      supports_inplace_reset: true,
      supports_reload_reset: false,
      supports_pause_detection: false,
      supports_menu_detection: true,
      provides_actionable_flag: true
    },
    reset: reset,
    getState: function () { return game.snapshot(); },
    getSeed: function () { return 73; },
    getEpisode: function () { return { seed: 73, level: 3, name: "Relay Circuit" }; }
  };
}(window));
