(function() {
  var GAME_ID = "16_hextris";
  var DEFAULT_SEED = 42;

  var capabilities = {
    supports_seed: false,
    supports_level_select: true,
    supports_difficulty: false,
    supports_inplace_reset: true,
    supports_reload_reset: true,
    supports_pause_detection: true,
    supports_menu_detection: false,
    provides_actionable_flag: true,
  };

  var session = {
    episodeStartMs: Date.now(),
    seed: DEFAULT_SEED,
    level: null,
    requestedDifficulty: null,
    episodeCount: 0,
    attemptStartOffset: Date.now(),
    resetCount: 0,
  };
  var runtime = {
    lastResetMethod: null,
    initialized: false,
  };

  function finiteOrNull(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  function intOrNull(value) {
    var num = finiteOrNull(value);
    return num === null ? null : Math.trunc(num);
  }

  function assignIfPresent(target, key, value) {
    if (value !== null && value !== undefined) target[key] = value;
  }

  function normalizeSeed(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    return value >>> 0;
  }

  function normalizeOptions(options) {
    var opts = options || {};
    return {
      seed: normalizeSeed(opts.seed),
      level:
        opts.level === undefined || opts.level === null
          ? null
          : (typeof opts.level === "number" && Number.isFinite(opts.level))
            ? Math.trunc(opts.level)
            : String(opts.level),
      difficulty:
        opts.difficulty === undefined || opts.difficulty === null
          ? null
          : String(opts.difficulty),
    };
  }

  function normalizeLevel(value) {
    if (value === null || value === undefined || value === "") return null;
    var parsed = Number(value);
    if (!Number.isFinite(parsed) || Math.floor(parsed) !== parsed || parsed < 1 || parsed > 35) {
      return null;
    }
    return parsed;
  }

  function readUrlLevel() {
    if (typeof window.getDifficultyFromQuery === "function") {
      return normalizeLevel(window.getDifficultyFromQuery());
    }
    try {
      return normalizeLevel(new URLSearchParams(window.location.search).get("level"));
    } catch (_err) {
      return null;
    }
  }

  function readSelectedLevel() {
    return normalizeLevel(window.initialDifficultyFromQuery) || readUrlLevel() || 1;
  }

  function hasInitialized() {
    return window.MainHex != null && typeof window.MainHex === "object" && typeof window.gameState === "number";
  }

  function ensureTerminalBucket() {
    if (!window.__hextrisTerminal) {
      window.__hextrisTerminal = {
        isTerminal: false,
        outcome: null,
        reason: null,
        ts: 0,
        score: null,
        level: null,
        difficulty: null,
        distance: null,
        environment: null,
      };
    }
  }

  function prepareEpisode(options) {
    var accepted = normalizeOptions(options);
    var notes = [];
    var explicitLevel = normalizeLevel(accepted.level);

    if (accepted.seed !== null) notes.push("seed_not_supported");
    if (accepted.level !== null && explicitLevel === null) notes.push("invalid_level");
    if (accepted.difficulty !== null) notes.push("difficulty_not_supported");

    var targetLevel = explicitLevel || normalizeLevel(session.level) || readUrlLevel() || readSelectedLevel();

    return {
      accepted: accepted,
      applied: {
        seed: null,
        level: targetLevel,
        difficulty: null,
      },
      level: targetLevel,
      explicitLevel: explicitLevel,
      notes: notes,
    };
  }

  function commitEpisode(episode, countAsReset) {
    session.episodeStartMs = Date.now();
    session.seed = DEFAULT_SEED;
    session.level = episode.level;
    session.requestedDifficulty = episode.accepted.difficulty;
    session.episodeCount += 1;
    session.attemptStartOffset = session.episodeStartMs;
    if (countAsReset !== false) session.resetCount += 1;
    runtime.initialized = true;
  }

  function clearTerminal() {
    ensureTerminalBucket();
    if (typeof window.__hextrisClearTerminal === "function") {
      window.__hextrisClearTerminal();
      return;
    }
    window.__hextrisTerminal.isTerminal = false;
    window.__hextrisTerminal.outcome = null;
    window.__hextrisTerminal.reason = null;
    window.__hextrisTerminal.ts = 0;
    window.__hextrisTerminal.score = null;
    window.__hextrisTerminal.level = null;
    window.__hextrisTerminal.difficulty = null;
    window.__hextrisTerminal.distance = null;
    window.__hextrisTerminal.environment = null;
  }

  function getLatchedTerminal() {
    ensureTerminalBucket();

    if (!window.__hextrisTerminal.isTerminal) {
      return {
        isTerminal: false,
        outcome: null,
        reason: null,
      };
    }

    return {
      isTerminal: true,
      outcome: window.__hextrisTerminal.outcome,
      reason: window.__hextrisTerminal.reason,
    };
  }

  function readScore() {
    return intOrNull(window.score);
  }

  function readDifficulty() {
    if (!window.waveone || !Number.isFinite(window.waveone.difficulty)) return null;
    return finiteOrNull(window.waveone.difficulty);
  }

  function buildPlayer() {
    if (!hasInitialized()) {
      return null;
    }

    var player = {};
    assignIfPresent(player, "x", intOrNull(window.MainHex.ct));
    assignIfPresent(player, "y", intOrNull(window.MainHex.y));
    assignIfPresent(player, "angle", intOrNull(window.MainHex.angle));
    assignIfPresent(player, "lane_rotation", intOrNull(window.MainHex.position));
    assignIfPresent(player, "velocity", intOrNull(window.MainHex.dt));
    return Object.keys(player).length ? player : null;
  }

  function buildStatus(gameState, terminal) {
    if (terminal.isTerminal) {
      return "terminal";
    }

    if (gameState === 1) {
      return "playing";
    }

    if (gameState === 0 || gameState === 2 || gameState === -1) {
      return "paused";
    }

    return "loading";
  }

  function environmentInfo() {
    if (!hasInitialized() || !window.MainHex || !Array.isArray(window.MainHex.blocks)) {
      return null;
    }

    var totalSettled = 0;
    var maxHeight = 0;
    for (var i = 0; i < MainHex.blocks.length; i += 1) {
      totalSettled += MainHex.blocks[i].length;
      if (MainHex.blocks[i].length > maxHeight) {
        maxHeight = MainHex.blocks[i].length;
      }
    }

    return {
      settled_blocks: totalSettled,
      highest_column_height: maxHeight,
      active_blocks: intOrNull(window.blocks ? window.blocks.length : 0),
    };
  }

  function buildLoadingState(now) {
    return {
      schemaVersion: "1.0",
      gameId: GAME_ID,
      seed: session.seed,
      timestampMs: now,
      gameTimeMs: finiteOrNull(now - session.episodeStartMs),
      status: "loading",
      is_actionable: false,
      terminal: {
        isTerminal: false,
        outcome: null,
        reason: null,
      },
      game_state: {
        score: readScore(),
        level: readSelectedLevel(),
        player: null,
        environment: null,
        completion_progress: null,
      },
      metrics: {
        primary_score: null,
        attempts: Math.max(1, session.resetCount),
        score: null,
        distance: null,
        best_score: null,
        difficulty: readDifficulty(),
        topped_out: null,
      },
      debug: {
        ready: false,
        game_state: window.gameState == null ? null : intOrNull(window.gameState),
        play_through: window.MainHex ? intOrNull(window.MainHex.playThrough) : null,
        last_reset_method: runtime.lastResetMethod,
      },
    };
  }

  function applyLevelSelection(level) {
    window.initialDifficultyFromQuery = level;
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("level", String(level));
      window.history.replaceState(null, "", url.href);
    } catch (_err) {}
  }

  function performReset(level) {
    applyLevelSelection(level);
    if (typeof clearSaveState === "function") {
      clearSaveState();
    }
    if (typeof init === "function") {
      init(1);
      return "inplace";
    }
    if (window.location && typeof window.location.reload === "function") {
      window.location.reload();
      return "reload";
    }
    return "unsupported";
  }

  function verifyReset(level, method) {
    if (method === "reload") return true;
    return method === "inplace" && hasInitialized() && intOrNull(window.gameState) === 1 &&
      readScore() === 0 && readSelectedLevel() === level &&
      intOrNull(readDifficulty()) === level;
  }

  window.gameAPI = {
    version: "1.0",
    capabilities: capabilities,

    init: async function(config) {
      var episode = prepareEpisode(config || {});
      if (runtime.initialized && normalizeLevel(session.level) === episode.level) {
        return {
          ok: true,
          accepted: episode.accepted,
          applied: episode.applied,
          notes: episode.notes.concat(["already_initialized"]),
        };
      }
      var currentLevel = readSelectedLevel();
      var terminal = getLatchedTerminal();
      var alreadyInitialized = hasInitialized() && intOrNull(window.gameState) === 1 &&
        !terminal.isTerminal && currentLevel === episode.level;
      if (alreadyInitialized) {
        commitEpisode(episode, false);
        return {
          ok: true,
          accepted: episode.accepted,
          applied: episode.applied,
          notes: episode.notes.concat(["already_initialized"]),
        };
      }

      var method = performReset(episode.level);
      var ok = verifyReset(episode.level, method);
      if (ok) {
        clearTerminal();
        commitEpisode(episode, false);
      } else {
        episode.notes.push("level_postcondition_failed");
        episode.applied.level = readSelectedLevel();
      }
      runtime.lastResetMethod = method;
      return {
        ok: ok,
        accepted: episode.accepted,
        applied: episode.applied,
        notes: episode.notes.length ? episode.notes : [],
      };
    },

    reset: async function(options) {
      var episode = prepareEpisode(options || {});
      var method = performReset(episode.level);
      runtime.lastResetMethod = method;
      var resetVerified = verifyReset(episode.level, method);
      if (resetVerified) {
        clearTerminal();
        commitEpisode(episode, true);
      } else {
        episode.notes.push("reset_postcondition_failed");
        episode.applied.level = readSelectedLevel();
      }
      return {
        ok: method !== "unsupported" && resetVerified,
        method: method,
        accepted: episode.accepted,
        applied: episode.applied,
        notes: episode.notes.length ? episode.notes : [],
      };
    },

    start: function() {
      return this.reset();
    },

    restart: function() {
      return this.reset();
    },

    getState: function() {
      var now = Date.now();
      var terminal = getLatchedTerminal();
      if (!hasInitialized()) {
        return buildLoadingState(now);
      }

      var score = terminal.isTerminal && intOrNull(window.__hextrisTerminal.score) !== null
        ? intOrNull(window.__hextrisTerminal.score)
        : readScore();
      var level = terminal.isTerminal && normalizeLevel(window.__hextrisTerminal.level) !== null
        ? normalizeLevel(window.__hextrisTerminal.level)
        : readSelectedLevel();
      var difficulty = terminal.isTerminal && finiteOrNull(window.__hextrisTerminal.difficulty) !== null
        ? finiteOrNull(window.__hextrisTerminal.difficulty)
        : readDifficulty();
      var gameState = intOrNull(window.gameState);
      var status = buildStatus(gameState, terminal);
      var player = buildPlayer();
      var environment = terminal.isTerminal && window.__hextrisTerminal.environment
        ? {
            settled_blocks: intOrNull(window.__hextrisTerminal.environment.settled_blocks),
            highest_column_height: intOrNull(window.__hextrisTerminal.environment.highest_column_height),
            active_blocks: intOrNull(window.__hextrisTerminal.environment.active_blocks),
          }
        : environmentInfo();
      var distance = terminal.isTerminal && intOrNull(window.__hextrisTerminal.distance) !== null
        ? intOrNull(window.__hextrisTerminal.distance)
        : (gameState === 1 ? intOrNull(window.MainHex.ct) : null);
      var runningMs = finiteOrNull(now - session.episodeStartMs);
      var gameStatePayload = {
        score: score,
        level: level,
        player: player,
        environment: environment,
        completion_progress: null,
      };

      return {
        schemaVersion: "1.0",
        gameId: GAME_ID,
        seed: session.seed,
        timestampMs: now,
        gameTimeMs: runningMs,
        status: status,
        is_actionable: status === "playing",
        terminal: terminal,
        game_state: gameStatePayload,
        metrics: {
          primary_score: score,
          attempts: Math.max(1, session.resetCount),
          score: score,
          distance: distance,
          best_score: intOrNull(window.highscores && window.highscores.length ? window.highscores[0] : null),
          difficulty: difficulty,
          topped_out: terminal.isTerminal && terminal.reason === "game_over",
        },
        debug: {
          ready: true,
          game_state: gameState,
          level_width: finiteOrNull(window.settings ? window.settings.hexWidth : null),
          scale: finiteOrNull(window.settings ? window.settings.scale : null),
          paused: gameState === 0 || gameState === -1,
          importing: window.importing == null ? null : intOrNull(window.importing),
          last_reset_method: runtime.lastResetMethod,
        },
      };
    },
  };
})();
