(function () {
  const GAME_ID = "04_boxel-rebound";

  const capabilities = {
    supports_seed: false,
    supports_level_select: true,
    supports_difficulty: false,
    supports_inplace_reset: true,
    supports_reload_reset: false,
    supports_pause_detection: true,
    supports_menu_detection: true,
    provides_actionable_flag: true
  };

  const session = {
    seed: null,
    configuredLevel: null,
    requestedDifficulty: null,
    episodeStartMs: Date.now(),
    episodeCount: 0
  };

  const runtimeState = {
    furthestDistance: 0,
    progressLevel: null,
    lastResetMethod: null,
    nativeRestartCount: 0,
    terminal: null
  };

  function getGame() {
    return typeof window !== "undefined" ? window.Game || null : null;
  }

  function finiteOrNull(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  function intOrNull(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    return Math.trunc(value);
  }

  function clamp01(value) {
    if (!Number.isFinite(value)) return null;
    if (value <= 0) return 0;
    if (value >= 1) return 1;
    return value;
  }

  function normalizeOptions(options) {
    const opts = options || {};
    let level = null;
    if (opts.level !== undefined && opts.level !== null && opts.level !== "") {
      const numeric = Number(opts.level);
      level = Number.isFinite(numeric) ? Math.trunc(numeric) : String(opts.level);
    }
    return {
      seed: intOrNull(opts.seed),
      level: level,
      difficulty:
        opts.difficulty === undefined || opts.difficulty === null
          ? null
          : String(opts.difficulty)
    };
  }

  function levelFromUrl() {
    try {
      const level = Number(new URLSearchParams(window.location.search || "").get("level"));
      return Number.isFinite(level) && Math.trunc(level) >= 1 ? Math.trunc(level) : null;
    } catch (error) {
      return null;
    }
  }

  function resolveTargetLevel(accepted, game, notes) {
    if (typeof accepted.level === "number" && accepted.level >= 1) return accepted.level;
    if (accepted.level !== null) notes.push("invalid_level");
    if (session.configuredLevel !== null) return session.configuredLevel;
    const urlLevel = levelFromUrl();
    if (urlLevel !== null) return urlLevel;
    const selected = finiteOrNull(game && game.home ? game.home.selectedLevel : null);
    return selected !== null && Math.trunc(selected) >= 1 ? Math.trunc(selected) : 1;
  }

  function waitForGame(timeoutMs) {
    return new Promise(function (resolve) {
      const deadline = Date.now() + timeoutMs;
      function check() {
        const game = getGame();
        if (game && game.ready === true && typeof game.startLevel === "function") {
          resolve(game);
          return;
        }
        if (Date.now() >= deadline) {
          resolve(null);
          return;
        }
        window.requestAnimationFrame(check);
      }
      check();
    });
  }

  function updateUrlLevel(level) {
    if (!window.history || typeof window.history.replaceState !== "function") return;
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("level", String(level));
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    } catch (error) {
      // Native level state remains authoritative when history is unavailable.
    }
  }

  function resetPostcondition(game, targetLevel, previousMap) {
    const selectedLevel = finiteOrNull(game && game.home ? game.home.selectedLevel : null);
    const dialogOpen = !!(
      game && game.dialog &&
      ((typeof game.dialog.isOpen === "function" && game.dialog.isOpen()) || game.dialog.dialog)
    );
    return !!(
      game &&
      game.levelMap &&
      Array.isArray(game.levelMap.map) &&
      game.levelMap.map.length > 0 &&
      game.levelMap.map !== previousMap &&
      selectedLevel !== null &&
      Math.trunc(selectedLevel) === targetLevel &&
      game.view === 2 &&
      game.gamePaused !== true &&
      !dialogOpen &&
      game.player &&
      game.player.playerState === 0 &&
      finiteOrNull(game.player.xPos) === 0 &&
      finiteOrNull(game.player.y) === 0
    );
  }

  async function startEpisode(options) {
    const accepted = normalizeOptions(options);
    const notes = [];
    if (accepted.seed !== null) notes.push("seed_not_supported");
    if (accepted.difficulty !== null) notes.push("difficulty_not_supported");
    const game = await waitForGame(5000);
    if (!game) {
      return {
        ok: false,
        accepted: accepted,
        applied: { seed: null, level: null, difficulty: null },
        notes: notes.concat(["native_game_unavailable"])
      };
    }
    const targetLevel = resolveTargetLevel(accepted, game, notes);
    const previousMap = game.levelMap ? game.levelMap.map : null;
    let started = false;
    try {
      started = game.startLevel(targetLevel) === true;
    } catch (error) {
      notes.push("native_level_start_threw");
    }
    if (!started) {
      return {
        ok: false,
        accepted: accepted,
        applied: { seed: null, level: null, difficulty: null },
        notes: notes.concat(["native_level_unavailable"])
      };
    }
    if (!resetPostcondition(game, targetLevel, previousMap)) {
      return {
        ok: false,
        accepted: accepted,
        applied: {
          seed: null,
          level: finiteOrNull(game.home ? game.home.selectedLevel : null),
          difficulty: null
        },
        notes: notes.concat(["native_reset_postcondition_failed"])
      };
    }

    session.configuredLevel = targetLevel;
    session.requestedDifficulty = accepted.difficulty;
    session.episodeStartMs = Date.now();
    session.episodeCount += 1;
    runtimeState.furthestDistance = 0;
    runtimeState.progressLevel = targetLevel;
    runtimeState.terminal = null;
    updateUrlLevel(targetLevel);

    return {
      ok: true,
      accepted: accepted,
      applied: { seed: null, level: targetLevel, difficulty: null },
      notes: notes
    };
  }

  function latchTerminal(outcome, reason) {
    if (runtimeState.terminal) return;
    const now = Date.now();
    const game = getGame();
    const level = game && game.home
      ? finiteOrNull(game.home.selectedLevel) : session.configuredLevel;
    const player = getPlayerSnapshot(game);
    const distance = updateDistance(level, player ? player.x : null);
    const finishDistance = getFinishDistance(game && game.levelMap);
    let progress = finishDistance === null || distance === null
      ? null : clamp01(distance / finishDistance);
    if (outcome === "success") {
      progress = 1;
    } else if (progress === 1) {
      progress = 0.999999;
    }
    const playTime = getPlayTimeMs(now);
    runtimeState.terminal = {
      outcome: outcome,
      reason: reason,
      display: {
        gameTimeMs: playTime,
        level: level,
        player: player,
        environment: getEnvironment(game, finishDistance),
        progress: progress,
        distance: distance,
        finishDistance: finishDistance
      }
    };
  }

  window.addEventListener("boxel-level-complete", function (event) {
    const level = finiteOrNull(event && event.detail && event.detail.level);
    if (level !== null && Math.trunc(level) === session.configuredLevel) {
      latchTerminal("success", "native_level_complete");
    }
  });

  window.addEventListener("boxel-run-aborted", function (event) {
    const level = finiteOrNull(event && event.detail && event.detail.level);
    if (level === null || Math.trunc(level) === session.configuredLevel) {
      latchTerminal("aborted", "native_quit");
    }
  });

  window.addEventListener("boxel-restart", function () {
    runtimeState.nativeRestartCount += 1;
    runtimeState.lastResetMethod = "keyboard";
  });

  function mapPlayerState(value) {
    if (value === 0) return "alive";
    if (value === 1) return "dead";
    if (value === 2) return "ready";
    return null;
  }

  function getPlayerSnapshot(game) {
    if (!game || !game.player) return null;
    const player = game.player;
    return {
      x: finiteOrNull(player.xPos),
      y: finiteOrNull(player.y),
      vx: finiteOrNull(player.xV),
      state: mapPlayerState(player.playerState),
      jump_ready: !!player.jumpReady,
      props: {
        on_finish_tile: !!player.onFinishTile,
        checkpoint_active: !!player.newSpawn,
        support_id: player.supportId == null ? null : String(player.supportId),
        checkpoint_support_id:
          player.spawnSupportId == null ? null : String(player.spawnSupportId)
      }
    };
  }

  function getFinishDistance(levelMap) {
    if (!levelMap || !Array.isArray(levelMap.map)) return null;
    const box = finiteOrNull(levelMap.box);
    if (box === null || box <= 0) return null;
    let finishColumn = null;
    for (let row = 0; row < levelMap.map.length; row += 1) {
      const columns = levelMap.map[row];
      if (!Array.isArray(columns)) continue;
      for (let column = 0; column < columns.length; column += 1) {
        if (columns[column] && columns[column].type === 11) {
          finishColumn = finishColumn === null ? column : Math.min(finishColumn, column);
        }
      }
    }
    return finishColumn === null ? null : finiteOrNull((finishColumn + 0.5) * box);
  }

  function getEnvironment(game, finishDistance) {
    const levelMap = game && game.levelMap;
    if (!levelMap) return null;
    const rows = Array.isArray(levelMap.map) ? levelMap.map.length : null;
    const columns = rows && Array.isArray(levelMap.map[0]) ? levelMap.map[0].length : null;
    const supports = Array.isArray(levelMap.movingSupports)
      ? levelMap.movingSupports.map(function (support) {
          return {
            id: String(support.id),
            left: finiteOrNull(support.left),
            right: finiteOrNull(support.right),
            top: finiteOrNull(support.top),
            offset_y: finiteOrNull(support.offsetY),
            has_checkpoint: support.checkpointCol >= 0
          };
        })
      : [];
    return {
      level_width: finiteOrNull(typeof levelMap.getWidth === "function" ? levelMap.getWidth() : null),
      finish_distance: finishDistance,
      map_rows: intOrNull(rows),
      map_cols: intOrNull(columns),
      camera_offset_x: finiteOrNull(levelMap.x),
      camera_progress: finiteOrNull(levelMap.cameraProgress),
      motion_time_ms: finiteOrNull(levelMap.motionTime),
      moving_supports: supports,
      speed_multiplier: finiteOrNull(game.speedMultiplier),
      gravity_multiplier: finiteOrNull(game.gravityMultiplier)
    };
  }

  function updateDistance(level, playerX) {
    if (level !== runtimeState.progressLevel) {
      runtimeState.progressLevel = level;
      runtimeState.furthestDistance = 0;
    }
    if (playerX !== null && playerX > runtimeState.furthestDistance) {
      runtimeState.furthestDistance = playerX;
    }
    return finiteOrNull(runtimeState.furthestDistance);
  }

  function getPlayTimeMs(now) {
    const native = window.timer && typeof window.timer.getPlayTime === "function"
      ? finiteOrNull(window.timer.getPlayTime())
      : null;
    return native !== null ? native : finiteOrNull(now - session.episodeStartMs);
  }

  function buildLoadingState(now) {
    return {
      schemaVersion: "1.0",
      gameId: GAME_ID,
      seed: null,
      timestampMs: now,
      gameTimeMs: finiteOrNull(now - session.episodeStartMs),
      status: "loading",
      is_actionable: false,
      terminal: { isTerminal: false, outcome: null, reason: null },
      game_state: {
        score: null,
        level: session.configuredLevel,
        player: null,
        environment: null,
        completion_progress: null
      },
      metrics: { primary_score: null, distance: null },
      debug: {
        ready: false,
        last_reset_method: runtimeState.lastResetMethod,
        episode_count: session.episodeCount
      }
    };
  }

  window.gameAPI = {
    version: "1.0",
    capabilities: capabilities,

    init: async function init(config) {
      const episode = await startEpisode(config || null);
      runtimeState.lastResetMethod = episode.ok ? "inplace" : "unsupported";
      return {
        ok: episode.ok,
        accepted: episode.accepted,
        applied: episode.applied,
        notes: episode.notes
      };
    },

    getState: function getState() {
      const now = Date.now();
      const game = getGame();
      if (!game || game.ready !== true || typeof game.view !== "number") {
        return buildLoadingState(now);
      }

      const view = finiteOrNull(game.view);
      const dialogState = game.dialog && typeof game.dialog.state === "string"
        ? game.dialog.state
        : null;
      if (!runtimeState.terminal && view === 2 && dialogState === "complete") {
        latchTerminal("success", "native_level_complete");
      } else if (!runtimeState.terminal && view === 2 && dialogState === "gameover") {
        latchTerminal("success", "native_campaign_complete");
      }

      const terminal = runtimeState.terminal;
      const display = terminal && terminal.display ? terminal.display : null;
      const level = display
        ? display.level
        : game.home ? finiteOrNull(game.home.selectedLevel) : session.configuredLevel;
      const paused = !!game.gamePaused || dialogState === "pause" || dialogState === "tip";
      const player = display ? display.player : getPlayerSnapshot(game);
      const playerX = player ? player.x : null;
      const distance = display ? display.distance : updateDistance(level, playerX);
      const finishDistance = display
        ? display.finishDistance : getFinishDistance(game.levelMap);
      let progress = display ? display.progress : (
        finishDistance === null || distance === null
          ? null
          : clamp01(distance / finishDistance)
      );
      if (!display) {
        if (terminal && terminal.outcome === "success") {
          progress = 1;
        } else if (progress === 1) {
          // Reserve exact completion for Player.completeLevel(); passing the finish
          // column and dying is not a completed stage.
          progress = 0.999999;
        }
      }
      const playTime = display ? display.gameTimeMs : getPlayTimeMs(now);

      let status = "loading";
      if (terminal) status = "terminal";
      else if (view === 2) status = paused ? "paused" : "playing";
      else if (view === 0 || view === 1 || view === 3) status = "menu";

      return {
        schemaVersion: "1.0",
        gameId: GAME_ID,
        seed: null,
        timestampMs: now,
        gameTimeMs: playTime,
        status: status,
        is_actionable: !terminal && status === "playing" && player !== null && player.state === "alive",
        terminal: {
          isTerminal: !!terminal,
          outcome: terminal ? terminal.outcome : null,
          reason: terminal ? terminal.reason : null
        },
        game_state: {
          score: playTime,
          level: level,
          player: player,
          environment: display ? display.environment : getEnvironment(game, finishDistance),
          completion_progress: progress
        },
        metrics: {
          primary_score: progress,
          distance: distance,
          finish_distance: finishDistance
        },
        debug: {
          view: view,
          dialog_state: dialogState,
          paused: paused,
          last_reset_method: runtimeState.lastResetMethod,
          requested_difficulty: session.requestedDifficulty,
          episode_count: session.episodeCount,
          native_restart_count: runtimeState.nativeRestartCount,
          input: {
            jump_held: !!game.jumpHeld
          }
        }
      };
    },

    reset: async function reset(options) {
      const episode = await startEpisode(options || null);
      runtimeState.lastResetMethod = episode.ok ? "inplace" : "unsupported";
      return {
        ok: episode.ok,
        method: episode.ok ? "inplace" : "unsupported",
        accepted: episode.accepted,
        applied: episode.applied,
        notes: episode.notes
      };
    }
  };
})();
