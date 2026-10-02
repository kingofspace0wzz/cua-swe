(function () {
  const GAME_ID = '03_astray';
  const DEFAULT_SEED = 42;

  const capabilities = {
    supports_seed: false,
    supports_level_select: true,
    supports_difficulty: false,
    supports_inplace_reset: true,
    supports_reload_reset: false,
    supports_pause_detection: false,
    supports_menu_detection: false,
    provides_actionable_flag: true
  };

  const session = {
    seed: DEFAULT_SEED,
    configuredLevel: null,
    requestedDifficulty: null,
    episodeStartMs: Date.now(),
    episodeCount: 0
  };

  const runtimeState = {
    lastResetMethod: null,
    terminal: null,
    pathDistanceCache: null
  };

  function safeNumber(value) {
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }

  function intOrNull(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null;
    return Math.trunc(value);
  }

  function normalizeOptions(options) {
    const opts = options || {};
    let level = null;
    if (opts.level !== undefined && opts.level !== null && opts.level !== '') {
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

  function levelFromDimension(dimension) {
    if (typeof dimension !== 'number' || !Number.isFinite(dimension)) return null;
    const level = Math.floor((dimension - 1) / 2 - 4);
    return level >= 1 ? level : null;
  }

  function levelFromUrl() {
    try {
      const raw = new URLSearchParams(window.location.search || '').get('level');
      const level = Number(raw);
      return Number.isFinite(level) && Math.trunc(level) >= 1 ? Math.trunc(level) : null;
    } catch (error) {
      return null;
    }
  }

  function getNativeLevel() {
    const native = typeof window !== 'undefined' ? window.__astrayNative : null;
    const current = safeNumber(native && native.currentLevel);
    if (current !== null) return Math.trunc(current);
    return levelFromDimension(safeNumber(typeof window !== 'undefined' ? window.mazeDimension : null));
  }

  function resetDeterministicRandom() {
    if (typeof window !== 'undefined' && typeof window.__resetRandom === 'function') {
      try {
        window.__resetRandom();
      } catch (error) {
        return false;
      }
    }
    return true;
  }

  function resolveTargetLevel(accepted, notes) {
    if (typeof accepted.level === 'number' && accepted.level >= 1) return accepted.level;
    if (accepted.level !== null) notes.push('invalid_level');
    if (session.configuredLevel !== null) return session.configuredLevel;
    return levelFromUrl() || getNativeLevel() || 1;
  }

  function updateUrlLevel(level) {
    if (!window.history || typeof window.history.replaceState !== 'function') return;
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('level', String(level));
      window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    } catch (error) {
      // URL metadata is auxiliary; native level application is authoritative.
    }
  }

  function waitNextFrame() {
    return new Promise(function (resolve) {
      window.requestAnimationFrame(resolve);
    });
  }

  function nativeEpisodePostcondition(targetLevel, previousBody) {
    const native = typeof window !== 'undefined' ? window.__astrayNative : null;
    const body = typeof window !== 'undefined' ? window.wBall : null;
    const position = body && typeof body.GetPosition === 'function' ? body.GetPosition() : null;
    return !!(
      native &&
      Math.trunc(safeNumber(native.currentLevel)) === targetLevel &&
      native.lastCompletedLevel == null &&
      safeNumber(window.mazeDimension) === (2 * targetLevel) + 9 &&
      window.gameState === 'play' &&
      body &&
      body !== previousBody &&
      position &&
      Math.abs(position.x - 1) < 0.05 &&
      Math.abs(position.y - 1) < 0.05
    );
  }

  async function waitForNativeEpisode(targetLevel, previousBody, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (nativeEpisodePostcondition(targetLevel, previousBody)) return true;
      await waitNextFrame();
    }
    return false;
  }

  async function startEpisode(options) {
    const accepted = normalizeOptions(options);
    const notes = [];
    if (accepted.seed !== null) notes.push('seed_not_supported');
    if (accepted.difficulty !== null) notes.push('difficulty_not_supported');
    const targetLevel = resolveTargetLevel(accepted, notes);

    if (!resetDeterministicRandom() || typeof window.__astrayStartLevel !== 'function') {
      return {
        ok: false,
        accepted: accepted,
        applied: { seed: null, level: null, difficulty: null },
        notes: notes.concat(['native_restart_unavailable'])
      };
    }

    const previousBody = typeof window !== 'undefined' ? window.wBall : null;
    runtimeState.pathDistanceCache = null;
    let started = false;
    try {
      started = window.__astrayStartLevel(targetLevel) === true;
    } catch (error) {
      notes.push('native_restart_threw');
    }
    if (!started) {
      return {
        ok: false,
        accepted: accepted,
        applied: { seed: null, level: null, difficulty: null },
        notes: notes.concat(['native_restart_failed'])
      };
    }
    if (!await waitForNativeEpisode(targetLevel, previousBody, 2500)) {
      return {
        ok: false,
        accepted: accepted,
        applied: { seed: null, level: getNativeLevel(), difficulty: null },
        notes: notes.concat(['native_restart_postcondition_failed'])
      };
    }

    session.configuredLevel = targetLevel;
    session.requestedDifficulty = accepted.difficulty;
    session.episodeStartMs = Date.now();
    session.episodeCount += 1;
    runtimeState.terminal = null;
    updateUrlLevel(targetLevel);

    return {
      ok: true,
      accepted: accepted,
      applied: { seed: null, level: targetLevel, difficulty: null },
      notes: notes
    };
  }

  function getGameState() {
    return typeof window !== 'undefined' ? window.gameState : null;
  }

  function mapStatus(state) {
    if (state === 'play') return 'playing';
    return 'loading';
  }

  function getPlayerSnapshot() {
    const ball = typeof window !== 'undefined' ? window.ballMesh : null;
    if (!ball || !ball.position) return null;
    const body = typeof window !== 'undefined' ? window.wBall : null;
    const velocity = body && typeof body.GetLinearVelocity === 'function'
      ? body.GetLinearVelocity()
      : null;
    return {
      x: safeNumber(ball.position.x),
      y: safeNumber(ball.position.y),
      z: safeNumber(ball.position.z),
      vx: safeNumber(velocity && velocity.x),
      vy: safeNumber(velocity && velocity.y),
      state: getGameState() === 'play' ? 'rolling' : null,
      props: {
        radius: safeNumber(typeof window !== 'undefined' ? window.ballRadius : null)
      }
    };
  }

  function getExitSnapshot(dimension) {
    if (dimension === null) return null;
    return { x: dimension, y: dimension - 2, z: 0 };
  }

  function computeDistanceToGoal(player, exit) {
    if (!player || !exit) return null;
    const dx = exit.x - player.x;
    const dy = exit.y - player.y;
    return safeNumber(Math.sqrt((dx * dx) + (dy * dy)));
  }

  function isOpenMazeCell(maze, dimension, x, y) {
    return !!(
      x >= 0 &&
      x < dimension &&
      y >= 0 &&
      y < dimension &&
      Array.isArray(maze[x]) &&
      maze[x][y] === false
    );
  }

  function buildPathDistanceCache(maze, dimension) {
    const exitX = dimension - 1;
    const exitY = dimension - 2;
    if (!isOpenMazeCell(maze, dimension, exitX, exitY)) return null;

    const distances = Array.from({ length: dimension }, function () {
      return Array(dimension).fill(null);
    });
    const queue = [[exitX, exitY]];
    let queueIndex = 0;

    // The native exit is one cell beyond the opened border cell.
    distances[exitX][exitY] = 1;
    while (queueIndex < queue.length) {
      const cell = queue[queueIndex];
      queueIndex += 1;
      const x = cell[0];
      const y = cell[1];
      const nextDistance = distances[x][y] + 1;
      const neighbors = [
        [x - 1, y],
        [x + 1, y],
        [x, y - 1],
        [x, y + 1]
      ];

      for (let index = 0; index < neighbors.length; index += 1) {
        const neighborX = neighbors[index][0];
        const neighborY = neighbors[index][1];
        if (
          isOpenMazeCell(maze, dimension, neighborX, neighborY) &&
          distances[neighborX][neighborY] === null
        ) {
          distances[neighborX][neighborY] = nextDistance;
          queue.push([neighborX, neighborY]);
        }
      }
    }

    const initialDistance = distances[1] ? safeNumber(distances[1][1]) : null;
    if (initialDistance === null || initialDistance <= 0) return null;
    return {
      maze: maze,
      dimension: dimension,
      distances: distances,
      initialDistance: initialDistance
    };
  }

  function getPathDistanceCache(dimension) {
    const maze = typeof window !== 'undefined' ? window.maze : null;
    const integerDimension = intOrNull(dimension);
    if (
      integerDimension === null ||
      integerDimension < 3 ||
      !Array.isArray(maze) ||
      maze.length < integerDimension
    ) {
      return null;
    }

    const cached = runtimeState.pathDistanceCache;
    if (cached && cached.maze === maze && cached.dimension === integerDimension) {
      return cached;
    }

    const rebuilt = buildPathDistanceCache(maze, integerDimension);
    runtimeState.pathDistanceCache = rebuilt;
    return rebuilt;
  }

  function computePathProgress(player, dimension, terminal) {
    const cache = getPathDistanceCache(dimension);
    if (terminal) {
      return {
        distance: 0,
        progress: 1,
        initialDistance: cache ? cache.initialDistance : null,
        playerCell: null
      };
    }
    if (!player || !cache) {
      return { distance: null, progress: null, initialDistance: null, playerCell: null };
    }

    // Match the native victory check when mapping the continuous ball to a maze cell.
    const cellX = Math.floor(player.x + 0.5);
    const cellY = Math.floor(player.y + 0.5);
    const playerCell = { x: cellX, y: cellY };
    if (cellX === cache.dimension && cellY === cache.dimension - 2) {
      return {
        distance: 0,
        progress: 1,
        initialDistance: cache.initialDistance,
        playerCell: playerCell
      };
    }
    if (!isOpenMazeCell(cache.maze, cache.dimension, cellX, cellY)) {
      return {
        distance: null,
        progress: null,
        initialDistance: cache.initialDistance,
        playerCell: playerCell
      };
    }

    const distance = safeNumber(cache.distances[cellX][cellY]);
    if (distance === null) {
      return {
        distance: null,
        progress: null,
        initialDistance: cache.initialDistance,
        playerCell: playerCell
      };
    }
    const progress = Math.min(
      1,
      Math.max(0, (cache.initialDistance - distance) / cache.initialDistance)
    );
    return {
      distance: distance,
      progress: progress,
      initialDistance: cache.initialDistance,
      playerCell: playerCell
    };
  }

  function observeNativeCompletion() {
    if (runtimeState.terminal) return;
    const native = typeof window !== 'undefined' ? window.__astrayNative : null;
    const completed = safeNumber(native && native.lastCompletedLevel);
    if (completed !== null && Math.trunc(completed) === session.configuredLevel) {
      runtimeState.terminal = {
        outcome: 'success',
        reason: 'native_level_exit'
      };
    }
  }

  window.addEventListener('astray-level-complete', function (event) {
    const level = safeNumber(event && event.detail && event.detail.level);
    if (level !== null && Math.trunc(level) === session.configuredLevel) {
      runtimeState.terminal = {
        outcome: 'success',
        reason: 'native_level_exit'
      };
    }
  });

  function snapshot(now) {
    observeNativeCompletion();
    const nativeState = getGameState();
    const terminal = runtimeState.terminal;
    const nativeStatus = mapStatus(nativeState);
    const dimension = safeNumber(typeof window !== 'undefined' ? window.mazeDimension : null);
    const nativeLevel = getNativeLevel();
    const player = getPlayerSnapshot();
    const exit = getExitSnapshot(dimension);
    const distance = computeDistanceToGoal(player, exit);
    const pathProgress = computePathProgress(player, dimension, terminal);
    const progress = pathProgress.progress === null ? 0 : pathProgress.progress;
    const status = terminal ? 'terminal' : nativeStatus;
    const keyAxis = typeof window !== 'undefined' && Array.isArray(window.keyAxis)
      ? window.keyAxis.map(safeNumber)
      : null;
    const native = typeof window !== 'undefined' ? window.__astrayNative : null;

    return {
      schemaVersion: '1.0',
      gameId: GAME_ID,
      seed: session.seed,
      timestampMs: now,
      gameTimeMs: safeNumber(now - session.episodeStartMs),
      status: status,
      is_actionable: !terminal && status === 'playing' && player !== null,
      terminal: {
        isTerminal: !!terminal,
        outcome: terminal ? terminal.outcome : null,
        reason: terminal ? terminal.reason : null
      },
      game_state: {
        score: progress,
        level: session.configuredLevel,
        player: player,
        environment: {
          maze_dimension: dimension,
          exit: exit
        },
        completion_progress: progress
      },
      metrics: {
        primary_score: progress,
        level_completed: !!terminal,
        distance_to_goal: distance,
        path_distance_to_goal: pathProgress.distance,
        native_level: nativeLevel
      },
      debug: {
        state: nativeState,
        maze_dimension: dimension,
        initial_path_distance: pathProgress.initialDistance,
        player_cell: pathProgress.playerCell,
        key_axis: keyAxis,
        native_restart_count: intOrNull(native && native.restartCount),
        requested_difficulty: session.requestedDifficulty,
        last_reset_method: runtimeState.lastResetMethod,
        episode_count: session.episodeCount
      }
    };
  }

  window.gameAPI = {
    version: '1.0',
    capabilities: capabilities,

    init: async function init(config) {
      const episode = await startEpisode(config || null);
      runtimeState.lastResetMethod = episode.ok ? 'inplace' : 'unsupported';
      return {
        ok: episode.ok,
        accepted: episode.accepted,
        applied: episode.applied,
        notes: episode.notes
      };
    },

    getState: function getState() {
      return snapshot(Date.now());
    },

    reset: async function reset(options) {
      const episode = await startEpisode(options || null);
      runtimeState.lastResetMethod = episode.ok ? 'inplace' : 'unsupported';
      return {
        ok: episode.ok,
        method: episode.ok ? 'inplace' : 'unsupported',
        accepted: episode.accepted,
        applied: episode.applied,
        notes: episode.notes
      };
    }
  };
})();
