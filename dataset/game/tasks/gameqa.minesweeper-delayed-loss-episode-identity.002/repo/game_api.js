(function () {
  const GAME_ID = '19_minesweeper';
  const DEFAULT_SEED = 42;
  const PENDING_SEED_KEY = 'gameworld:19_minesweeper:pending-seed';
  const CELL_TOKENS = {
    unknown: '\u2B1C',
    mine: '\u{1F4A3}',
    explodedMine: '\u{1F4A5}',
    incorrectFlag: '\u274C',
    marked: '\u{1F6A9}',
    question: '\u2753'
  };
  const DIGIT_TOKEN_REGEX = /^[0-8]\uFE0F?\u20E3$/;
  const NATIVE_EPISODE_ID_KEY = '__gameApiNativeEpisodeId';

  const capabilities = {
    supports_seed: true,
    supports_level_select: false,
    supports_difficulty: false,
    supports_inplace_reset: true,
    supports_reload_reset: true,
    supports_pause_detection: false,
    supports_menu_detection: false,
    provides_actionable_flag: true
  };

  const session = {
    seed: getCurrentSeed(),
    difficulty: null,
    episodeStartMs: Date.now(),
    episodeCount: 0
  };

  const runtime = {
    gameplayStartMs: null,
    lastResetMethod: null
  };

  const terminalLatch = {
    isTerminal: false,
    outcome: null,
    reason: null,
    ts: 0
  };

  function finiteNumber(value) {
    return (typeof value === 'number' && Number.isFinite(value)) ? value : null;
  }

  function intOrNull(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null;
    return Math.trunc(value);
  }

  function normalizeSeed(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    return (numeric >>> 0);
  }

  function clearTerminal() {
    terminalLatch.isTerminal = false;
    terminalLatch.outcome = null;
    terminalLatch.reason = null;
    terminalLatch.ts = 0;
  }

  function latchTerminal(outcome, reason) {
    if (terminalLatch.isTerminal) return;
    terminalLatch.isTerminal = true;
    terminalLatch.outcome = outcome;
    terminalLatch.reason = reason;
    terminalLatch.ts = Date.now();
  }

  function getLatchedTerminal() {
    if (!terminalLatch.isTerminal) return null;
    return {
      isTerminal: true,
      outcome: terminalLatch.outcome,
      reason: terminalLatch.reason
    };
  }

  function normalizeOptions(options) {
    const opts = options || {};
    return {
      seed: normalizeSeed(opts.seed),
      level:
        opts.level === undefined || opts.level === null
          ? null
          : (typeof opts.level === 'number' && Number.isFinite(opts.level))
            ? Math.trunc(opts.level)
            : String(opts.level),
      difficulty:
        opts.difficulty === undefined || opts.difficulty === null
          ? null
          : String(opts.difficulty)
    };
  }

  function getCurrentSeed() {
    if (typeof window !== 'undefined' && typeof window.__getDeterministicSeed === 'function') {
      const seed = intOrNull(window.__getDeterministicSeed());
      if (seed !== null) return (seed >>> 0);
    }
    return DEFAULT_SEED;
  }

  function applySeed(seed) {
    if (typeof window === 'undefined') return null;
    try {
      if (typeof window.__setDeterministicSeed === 'function') {
        const applied = intOrNull(window.__setDeterministicSeed(seed));
        return applied === null ? null : (applied >>> 0);
      }
      if (typeof window.__resetRandom === 'function') {
        const applied = intOrNull(window.__resetRandom(seed));
        return applied === null ? null : (applied >>> 0);
      }
    } catch (error) {}
    return null;
  }

  function captureRandomState() {
    if (
      typeof window === 'undefined' ||
      typeof window.__getDeterministicRandomState !== 'function'
    ) {
      return null;
    }
    try {
      const snapshot = window.__getDeterministicRandomState();
      if (!snapshot || typeof snapshot !== 'object') return null;
      const seed = intOrNull(snapshot.seed);
      const random = intOrNull(snapshot.random);
      const crypto = intOrNull(snapshot.crypto);
      if (seed === null || random === null || crypto === null) return null;
      return {
        seed: seed >>> 0,
        random: random >>> 0,
        crypto: crypto >>> 0
      };
    } catch (error) {
      return null;
    }
  }

  function restoreRandomState(snapshot) {
    if (
      !snapshot ||
      typeof window === 'undefined' ||
      typeof window.__restoreDeterministicRandomState !== 'function'
    ) {
      return false;
    }
    try {
      return window.__restoreDeterministicRandomState(snapshot) === true;
    } catch (error) {
      return false;
    }
  }

  function persistSeedForReload(seed) {
    if (typeof window === 'undefined') return { ok: false };
    try {
      const storage = window.sessionStorage;
      if (!storage) return { ok: false };
      const previousValue = storage.getItem(PENDING_SEED_KEY);
      const encoded = String(seed >>> 0);
      storage.setItem(PENDING_SEED_KEY, encoded);
      if (storage.getItem(PENDING_SEED_KEY) !== encoded) {
        if (previousValue === null) storage.removeItem(PENDING_SEED_KEY);
        else storage.setItem(PENDING_SEED_KEY, previousValue);
        return { ok: false };
      }
      return { ok: true, storage, previousValue };
    } catch (error) {
      return { ok: false };
    }
  }

  function restorePendingSeed(persistence) {
    if (!persistence || !persistence.ok || !persistence.storage) return;
    try {
      if (persistence.previousValue === null) {
        persistence.storage.removeItem(PENDING_SEED_KEY);
      } else {
        persistence.storage.setItem(PENDING_SEED_KEY, persistence.previousValue);
      }
    } catch (error) {}
  }

  function planEpisode(options) {
    const accepted = normalizeOptions(options);
    const notes = [];

    if (accepted.level !== null) notes.push('level_not_supported');
    if (accepted.difficulty !== null) notes.push('difficulty_not_supported');

    return {
      accepted: accepted,
      applied: {
        seed: accepted.seed === null ? getCurrentSeed() : accepted.seed,
        level: null,
        difficulty: null
      },
      notes: notes
    };
  }

  function commitEpisode(episode) {
    session.seed = episode.applied.seed;
    session.difficulty = null;
    session.episodeStartMs = Date.now();
    session.episodeCount += 1;
    runtime.gameplayStartMs = null;
  }

  function captureLifecycle() {
    return {
      seed: session.seed,
      difficulty: session.difficulty,
      episodeStartMs: session.episodeStartMs,
      episodeCount: session.episodeCount,
      gameplayStartMs: runtime.gameplayStartMs,
      lastResetMethod: runtime.lastResetMethod,
      terminalIsTerminal: terminalLatch.isTerminal,
      terminalOutcome: terminalLatch.outcome,
      terminalReason: terminalLatch.reason,
      terminalTs: terminalLatch.ts,
      randomState: captureRandomState()
    };
  }

  function failedResetResult(episode, previous, reason) {
    return {
      ok: false,
      method: 'unsupported',
      accepted: episode.accepted,
      applied: {
        seed: previous.seed,
        level: null,
        difficulty: previous.difficulty
      },
      notes: episode.notes.concat([reason])
    };
  }

  function failedNativeResetResult(episode, previous, reason) {
    const result = failedResetResult(episode, previous, reason);
    if (!restoreRandomState(previous.randomState)) {
      result.notes.push('rng_restore_failed');
    }
    return result;
  }

  function navigateReload() {
    if (typeof window.__gameworldSeedNavigationHook === 'function') {
      window.__gameworldSeedNavigationHook('reload', null);
    }
    return window.location.reload();
  }

  function getGame() {
    if (typeof window === 'undefined') return null;
    const direct = window.minesweeperGames;
    if (direct) {
      if (Array.isArray(direct) && direct.length) return direct[0];
      if (typeof direct === 'object') {
        const keys = Object.keys(direct);
        if (keys.length) return direct[keys[0]];
      }
    }
    if (Array.isArray(window.games) && window.games.length) return window.games[0];
    return null;
  }

  function parseBoard(boardString) {
    if (!boardString || typeof boardString !== 'string') return null;
    const rows = boardString
      .split('\n')
      .map(function (row) {
        return row.trim();
      })
      .filter(function (row) {
        return row.length > 0;
      })
      .map(function (row) {
        return row.split(' ');
      });
    return rows.length ? rows : null;
  }

  function getPreset() {
    if (typeof document === 'undefined') return null;
    const el = document.querySelector('.minesweeper-game');
    return el ? el.getAttribute('data-preset') : null;
  }

  function isPairOfNumbers(value) {
    return (
      Array.isArray(value) &&
      value.length >= 2 &&
      typeof value[0] === 'number' &&
      typeof value[1] === 'number'
    );
  }

  function installShuffleHook(game) {
    if (typeof window === 'undefined') return;
    if (game) {
      window.__minesweeperMineTarget = game;
    }
    const target = window.__minesweeperMineTarget;
    if (target && target.__minePositions) return;
    if (window.__minesweeperShuffleHookInstalled) return;

    const lodash = window._;
    if (!lodash || typeof lodash.shuffle !== 'function') return;

    const originalShuffle = lodash.shuffle;
    window.__minesweeperOriginalShuffle = originalShuffle;
    window.__minesweeperShuffleHookInstalled = true;

    lodash.shuffle = function (list) {
      const shuffled = originalShuffle.apply(this, arguments);
      try {
        const target = window.__minesweeperMineTarget;
        if (
          target &&
          !target.__minePositions &&
          Array.isArray(list) &&
          Array.isArray(shuffled)
        ) {
          const dims = Array.isArray(target.dimensions) ? target.dimensions : null;
          const totalCells =
            dims && typeof dims[0] === 'number' && typeof dims[1] === 'number'
              ? dims[0] * dims[1]
              : null;
          const mineCount =
            typeof target.mine_count === 'number'
              ? target.mine_count
              : typeof target.mineCount === 'number'
                ? target.mineCount
                : null;

          if (totalCells && mineCount && list.length === totalCells - 1) {
            const candidate = shuffled.slice(0, mineCount);
            if (candidate.every(isPairOfNumbers)) {
              target.__minePositions = candidate.map(function (entry) {
                return [entry[0], entry[1]];
              });
            }
          }
        }
      } catch (e) {
        // Ignore hook errors; do not break game logic.
      }
      return shuffled;
    };
  }

  function installPlaceMinesHook(game) {
    if (!game || game.__placeMinesHookInstalled) return;
    if (typeof game.placeMines !== 'function') return;

    game.__placeMinesHookInstalled = true;
    const originalPlaceMines = game.placeMines;
    game.placeMines = function (mines) {
      if (Array.isArray(mines)) {
        const parsed = mines
          .map(function (entry) {
            if (isPairOfNumbers(entry)) return [entry[0], entry[1]];
            if (entry && typeof entry === 'object') {
              if (typeof entry.row === 'number' && typeof entry.col === 'number') {
                return [entry.row, entry.col];
              }
              if (typeof entry.r === 'number' && typeof entry.c === 'number') {
                return [entry.r, entry.c];
              }
            }
            return null;
          })
          .filter(function (entry) {
            return entry !== null;
          });
        game.__minePositions = parsed.length ? parsed : null;
      } else {
        game.__minePositions = null;
      }
      return originalPlaceMines.apply(game, arguments);
    };
  }

  function ensureMineTracking(game) {
    if (!game || game.__mineTrackingInstalled) return;
    game.__mineTrackingInstalled = true;

    if (Array.isArray(game.mines) && !game.__minePositions) {
      const parsed = game.mines
        .map(function (entry) {
          return isPairOfNumbers(entry) ? [entry[0], entry[1]] : null;
        })
        .filter(function (entry) {
          return entry !== null;
        });
      if (parsed.length) {
        game.__minePositions = parsed;
      }
    }

    installPlaceMinesHook(game);
    installShuffleHook(game);

    if (intOrNull(game[NATIVE_EPISODE_ID_KEY]) === null) {
      game[NATIVE_EPISODE_ID_KEY] = 0;
    }
    if (
      !game.__gameApiNativeEpisodeHookInstalled &&
      typeof game.onGameStateChange === 'function'
    ) {
      game.__gameApiNativeEpisodeHookInstalled = true;
      game.onGameStateChange(function (nextState) {
        if (nextState === 'not_started') {
          game[NATIVE_EPISODE_ID_KEY] = game[NATIVE_EPISODE_ID_KEY] + 1;
        }
      });
    }

    if (typeof game.reset === 'function') {
      const originalReset = game.reset;
      game.reset = function () {
        const result = originalReset.apply(game, arguments);
        game.__minePositions = null;
        return result;
      };
    }
  }

  function bootstrapMineTracking() {
    if (typeof window === 'undefined') return;
    let attempts = 0;
    const maxAttempts = 200;
    const intervalMs = 50;
    let timerId = null;

    function tick() {
      attempts += 1;
      const game = getGame();
      if (game && !window.__minesweeperMineTarget) {
        window.__minesweeperMineTarget = game;
      }
      if (game) {
        ensureMineTracking(game);
      }
      installShuffleHook(window.__minesweeperMineTarget);

      if (
        (window.__minesweeperShuffleHookInstalled && window.__minesweeperMineTarget) ||
        attempts >= maxAttempts
      ) {
        if (timerId !== null && typeof window.clearInterval === 'function') {
          window.clearInterval(timerId);
        }
      }
    }

    timerId = typeof window.setInterval === 'function'
      ? window.setInterval(tick, intervalMs)
      : null;
    if (timerId === null) {
      tick();
    }
  }

  function isDigitToken(token) {
    return typeof token === 'string' && DIGIT_TOKEN_REGEX.test(token);
  }

  function countCellsRevealed(board) {
    if (!Array.isArray(board)) return null;
    let count = 0;
    for (let r = 0; r < board.length; r += 1) {
      const row = board[r];
      if (!Array.isArray(row)) continue;
      for (let c = 0; c < row.length; c += 1) {
        if (isDigitToken(row[c])) count += 1;
      }
    }
    return count;
  }

  function countCorrectFlaggedMines(board, minePositions, status) {
    if (!Array.isArray(board)) return null;
    if (Array.isArray(minePositions) && minePositions.length > 0) {
      let count = 0;
      for (let i = 0; i < minePositions.length; i += 1) {
        const entry = minePositions[i];
        if (!Array.isArray(entry) || entry.length < 2) continue;
        const row = entry[0];
        const col = entry[1];
        const rowData = board[row];
        if (!Array.isArray(rowData)) continue;
        if (rowData[col] === CELL_TOKENS.marked) count += 1;
      }
      return count;
    }

    if (status === 'lost') {
      let count = 0;
      for (let r = 0; r < board.length; r += 1) {
        const row = board[r];
        if (!Array.isArray(row)) continue;
        for (let c = 0; c < row.length; c += 1) {
          if (row[c] === CELL_TOKENS.marked) count += 1;
        }
      }
      return count;
    }

    return 0;
  }

  function clamp01(value) {
    const num = finiteNumber(value);
    if (num === null) return null;
    if (num < 0) return 0;
    if (num > 1) return 1;
    return num;
  }

  function getMineCount(game) {
    if (!game) return null;
    if (typeof game.mine_count === 'number') return Math.trunc(game.mine_count);
    if (typeof game.mineCount === 'number') return Math.trunc(game.mineCount);
    return null;
  }

  function getBoardDimensions(game, board) {
    if (game && Array.isArray(game.dimensions) && game.dimensions.length >= 2) {
      const rows = finiteNumber(game.dimensions[0]);
      const cols = finiteNumber(game.dimensions[1]);
      if (rows !== null && cols !== null) {
        return { rows: Math.trunc(rows), cols: Math.trunc(cols) };
      }
    }
    if (Array.isArray(board) && board.length) {
      return {
        rows: board.length,
        cols: Array.isArray(board[0]) ? board[0].length : null
      };
    }
    return { rows: null, cols: null };
  }

  function readNativeResetState(game) {
    let engineState = null;
    let boardString = null;
    let remainingMines = null;
    let startedAt = null;

    try {
      engineState = typeof game.state === 'function' ? game.state() : null;
      boardString = typeof game.renderAsString === 'function' ? game.renderAsString() : null;
      remainingMines =
        typeof game.remainingMineCount === 'function'
          ? intOrNull(game.remainingMineCount())
          : null;
      startedAt = typeof game.started === 'function' ? game.started() : null;
    } catch (e) {
      return null;
    }

    return {
      episodeId: intOrNull(game[NATIVE_EPISODE_ID_KEY]),
      engineState: engineState,
      board: parseBoard(boardString),
      remainingMines: remainingMines,
      startedAt: startedAt
    };
  }

  function isFreshNativeBoard(game, nativeState) {
    if (!nativeState || !Array.isArray(nativeState.board)) return false;
    const dimensions = getBoardDimensions(game, nativeState.board);
    if (dimensions.rows === null || dimensions.cols === null) return false;

    let cellCount = 0;
    for (let rowIndex = 0; rowIndex < nativeState.board.length; rowIndex += 1) {
      const row = nativeState.board[rowIndex];
      if (!Array.isArray(row)) return false;
      for (let colIndex = 0; colIndex < row.length; colIndex += 1) {
        if (row[colIndex] !== CELL_TOKENS.unknown) return false;
        cellCount += 1;
      }
    }

    return cellCount === dimensions.rows * dimensions.cols;
  }

  function nativeResetPostconditionHolds(game, before, after) {
    const mineCount = getMineCount(game);
    return !!(
      before &&
      after &&
      before.episodeId !== null &&
      after.episodeId !== null &&
      after.episodeId !== before.episodeId &&
      after.engineState === 'not_started' &&
      !after.startedAt &&
      mineCount !== null &&
      after.remainingMines === mineCount &&
      isFreshNativeBoard(game, after)
    );
  }

  function getCompletionProgress(numCellsRevealed, totalSafeCells, terminal) {
    if (terminal && terminal.isTerminal && terminal.outcome === 'success') return 1;
    if (numCellsRevealed === null || totalSafeCells === null || totalSafeCells <= 0) return null;
    return clamp01(numCellsRevealed / totalSafeCells);
  }

  function buildLoadingState(nowMs) {
    return {
      schemaVersion: '1.0',
      gameId: GAME_ID,
      seed: session.seed,
      timestampMs: nowMs,
      gameTimeMs: null,
      status: 'loading',
      is_actionable: false,
      terminal: { isTerminal: false, outcome: null, reason: null },
      game_state: {
        score: null,
        level: null,
        player: null,
        environment: null,
        completion_progress: null
      },
      metrics: {
        primary_score: null,
        attempts: session.episodeCount,
        revealed_safe_cells: null,
        total_safe_cells: null,
        correct_flags: null,
        total_mines: null,
        remaining_mines: null
      },
      debug: {
        game_ready: false,
        engine_state: null,
        preset: null,
        board_rows: null,
        board_cols: null,
        mine_positions_known: false,
        last_reset_method: runtime.lastResetMethod
      },
      raw: null
    };
  }

  bootstrapMineTracking();

  window.gameAPI = {
    version: '1.0',
    capabilities: capabilities,

    init: async function init(config) {
      const normalized = normalizeOptions(config || {});
      if (normalized.seed === null || normalized.seed === getCurrentSeed()) {
        const notes = ['already_initialized'];
        if (normalized.level !== null) notes.unshift('level_not_supported');
        if (normalized.difficulty !== null) notes.unshift('difficulty_not_supported');
        return {
          ok: true,
          accepted: normalized,
          applied: { seed: getCurrentSeed(), level: null, difficulty: null },
          notes: notes
        };
      }
      return window.gameAPI.reset(config || {});
    },

    getState: function getState() {
      const nowMs = Date.now();
      const game = getGame();
      ensureMineTracking(game);
      if (!game) {
        return buildLoadingState(nowMs);
      }

      const state = typeof game.state === 'function' ? game.state() : null;
      let baseStatus = 'loading';
      if (state === 'started') baseStatus = 'playing';
      else if (state === 'won' || state === 'lost') baseStatus = 'terminal';
      else if (state === 'not_started') baseStatus = 'ready';
      else if (typeof state === 'string' && state.length > 0) baseStatus = 'menu';

      const remainingMines =
        typeof game.remainingMineCount === 'function'
          ? game.remainingMineCount()
          : null;
      const startedAt = typeof game.started === 'function' ? game.started() : null;
      const timeMs =
        startedAt && typeof startedAt === 'number'
          ? Math.max(0, Date.now() - startedAt)
          : null;
      const boardString =
        typeof game.renderAsString === 'function' ? game.renderAsString() : null;
      const board = parseBoard(boardString);
      const preset = getPreset();
      const revealedSafeCells = countCellsRevealed(board);
      const mineCount = getMineCount(game);
      const dims = getBoardDimensions(game, board);
      const totalCells =
        (dims.rows !== null && dims.cols !== null) ? (dims.rows * dims.cols) : null;
      const totalSafeCells =
        (totalCells !== null && mineCount !== null) ? Math.max(0, totalCells - mineCount) : null;
      const correctFlags = countCorrectFlaggedMines(
        board,
        game.__minePositions,
        state
      );

      const terminalFromState =
        state === 'won'
          ? { isTerminal: true, outcome: 'success', reason: 'board_cleared' }
          : state === 'lost'
            ? { isTerminal: true, outcome: 'fail', reason: 'mine_triggered' }
            : null;
      if (terminalFromState) {
        latchTerminal(terminalFromState.outcome, terminalFromState.reason);
      }

      const terminal = getLatchedTerminal() || {
        isTerminal: false,
        outcome: null,
        reason: null
      };
      const status = terminal.isTerminal ? 'terminal' : baseStatus;
      if (status === 'playing' && runtime.gameplayStartMs === null) {
        runtime.gameplayStartMs = nowMs;
      }
      const effectiveNowMs = terminal.isTerminal && terminalLatch.ts > 0
        ? terminalLatch.ts
        : nowMs;
      const gameTimeMs = runtime.gameplayStartMs === null
        ? startedAt && typeof startedAt === 'number'
          ? Math.max(0, effectiveNowMs - startedAt)
          : timeMs
        : Math.max(0, effectiveNowMs - runtime.gameplayStartMs);

      return {
        schemaVersion: '1.0',
        gameId: GAME_ID,
        seed: session.seed,
        timestampMs: nowMs,
        gameTimeMs: gameTimeMs,
        status: status,
        is_actionable: status === 'ready' || status === 'playing',
        terminal: terminal,
        game_state: {
          score: revealedSafeCells,
          level: preset,
          player: null,
          environment: board,
          completion_progress: getCompletionProgress(revealedSafeCells, totalSafeCells, terminal)
        },
        metrics: {
          primary_score: revealedSafeCells,
          attempts: session.episodeCount,
          revealed_safe_cells: revealedSafeCells,
          total_safe_cells: totalSafeCells,
          correct_flags: correctFlags,
          total_mines: mineCount,
          remaining_mines: remainingMines
        },
        debug: {
          game_ready: true,
          engine_state: state,
          preset: preset,
          board_rows: dims.rows,
          board_cols: dims.cols,
          mine_positions_known: Array.isArray(game.__minePositions) && game.__minePositions.length > 0,
          last_reset_method: runtime.lastResetMethod
        },
        raw: null
      };
    },

    reset: async function reset(options) {
      const previous = captureLifecycle();
      const episode = planEpisode(options || {});
      const game = getGame();

      // The preferred reset path is the game's native reset() implementation.
      if (game && typeof game.reset === 'function') {
        if (!previous.randomState) {
          return failedResetResult(episode, previous, 'seed_transaction_unavailable');
        }
        const appliedSeed = applySeed(episode.applied.seed);
        if (appliedSeed === null || appliedSeed !== episode.applied.seed) {
          return failedNativeResetResult(episode, previous, 'seed_apply_failed');
        }
        ensureMineTracking(game);
        const before = readNativeResetState(game);
        let nativeResetError = null;
        try {
          await Promise.resolve(game.reset());
        } catch (e) {
          nativeResetError = e;
        }
        const after = readNativeResetState(game);
        if (!nativeResetPostconditionHolds(game, before, after)) {
          if (nativeResetError) {
            return failedNativeResetResult(episode, previous, 'native_reset_failed');
          }
          return failedNativeResetResult(
            episode,
            previous,
            'native_reset_postcondition_failed'
          );
        }
        commitEpisode(episode);
        clearTerminal();
        runtime.lastResetMethod = 'inplace';
        return {
          ok: true,
          method: 'inplace',
          accepted: episode.accepted,
          applied: episode.applied,
          notes: nativeResetError
            ? episode.notes.concat(['native_reset_threw_after_commit'])
            : episode.notes
        };
      }

      if (typeof window !== 'undefined' && window.location && typeof window.location.reload === 'function') {
        const persistence = persistSeedForReload(episode.applied.seed);
        if (!persistence.ok) {
          return failedResetResult(episode, previous, 'seed_persistence_failed');
        }
        try {
          navigateReload();
          runtime.lastResetMethod = 'reload';
          return {
            ok: true,
            method: 'reload',
            accepted: episode.accepted,
            applied: episode.applied,
            notes: episode.notes
          };
        } catch (e) {
          restorePendingSeed(persistence);
          return failedResetResult(episode, previous, 'reload_reset_failed');
        }
      }

      return failedResetResult(episode, previous, 'no_reset_method_available');
    }
  };
})();
