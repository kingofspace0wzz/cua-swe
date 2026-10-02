
(function() {
  'use strict';

  const GAME_ID = '06_captaincallisto';
  let episodeCount = 0;
  let terminalEvent = null;

  /**
   * Counts live rendered cargo units.
   * @return {number}
   */
  function remainingCoins() {
    return entities
        .filter((entity) => entity instanceof Coin && entity.health > 0)
        .reduce((total, coin) =>
          total + (/** @type {!Coin} */ (coin)).worldUnits, 0);
  }

  /**
   * Finds the nearest live entity of a requested class.
   * @param {!Function} EntityClass
   * @return {?Object}
   */
  function nearestEntity(EntityClass) {
    let nearest = null;
    entities.forEach((entity) => {
      if (!(entity instanceof EntityClass) || entity.health <= 0) return;
      const distance = vec3.distance(player.pos, entity.pos);
      if (!nearest || distance < nearest.distance) {
        nearest = {
          x: entity.pos[0],
          y: entity.pos[1],
          z: entity.pos[2],
          distance: distance,
        };
      }
    });
    return nearest;
  }

  /**
   * Loads the protected cargo contract and resets a level.
   * @param {number|string|undefined} requestedLevel
   * @return {!Promise<number>}
   */
  async function startLevel(requestedLevel) {
    const nextLevel = Math.max(1, Math.min(10, Number(requestedLevel) || 2));
    await loadCargoContract();
    setLevel(nextLevel);
    gameState = GameState.PLAYING;
    initGame();
    gameTime = 0;
    setMenu(null);
    resetKeys();
    terminalEvent = null;
    episodeCount++;
    return nextLevel;
  }

  window.addEventListener('captaincallisto-level-complete', (event) => {
    terminalEvent = event['detail'] || {};
  });

  window['gameAPI'] = {
    version: '1.0',
    capabilities: {
      supports_seed: true,
      supports_level_select: true,
      supports_inplace_reset: true,
      provides_actionable_flag: true,
    },
    init: async function(config) {
      const appliedLevel = await startLevel(config && config.level);
      return {ok: true, applied: {seed: 45, level: appliedLevel}};
    },
    reset: async function(config) {
      const appliedLevel = await startLevel(config && config.level);
      return {
        ok: true,
        method: 'inplace',
        applied: {seed: 45, level: appliedLevel},
      };
    },
    getState: function() {
      const remaining = remainingCoins();
      const collectedByWorld = availableCoins - remaining;
      const completed = gameState === GameState.AFTER_LEVEL || terminalEvent !== null;
      const reportedCoins = terminalEvent ? terminalEvent['coins'] : coins;
      const reportedTotal = terminalEvent ? terminalEvent['coinsTotal'] : availableCoins;
      return {
        schemaVersion: '1.0',
        gameId: GAME_ID,
        seed: 45,
        status: completed ? 'terminal' : 'playing',
        is_actionable: !completed && player.health > 0,
        terminal: {
          isTerminal: completed,
          outcome: completed ? 'success' : null,
          reason: completed ? 'native_level_exit' : null,
        },
        game_state: {
          score: reportedCoins,
          level: terminalEvent ? terminalEvent['level'] : level,
          completion_progress: completed ? 1 :
              (reportedTotal ? reportedCoins / reportedTotal : 0),
          player: {
            x: player.pos[0],
            y: player.pos[1],
            z: player.pos[2],
            alive: player.health > 0,
            fuel: player.fuel,
          },
          environment: {
            nearest_coin: nearestEntity(Coin),
            nearest_exit: nearestEntity(Flagpole),
          },
        },
        metrics: {
          primary_score: reportedCoins,
          coins: reportedCoins,
          coins_total: reportedTotal,
          remaining_coins: completed ? 0 : remaining,
          world_collected_coins: completed ? reportedCoins : collectedByWorld,
          semantic_mismatch: completed ? false : collectedByWorld !== coins,
          pending_inventory_receipts: inventoryReceipts.length,
          last_inventory_receipt: lastInventoryReceiptKey,
          cargo_contract_ready: cargoContractReady,
          deaths: player.health > 0 ? 0 : 1,
        },
        debug: {
          benchmark_mode: BENCHMARK_MODE,
          episode_count: episodeCount,
          game_state: gameState,
          lift_direction: entities.find((entity) =>
            entity instanceof Platform && entity.waypoints.length > 0)?.velocity[1] || 0,
          cargo_trace: cargoTraceLines.slice(),
        },
      };
    },
  };

  const query = new URLSearchParams(window.location.search);
  if (query.get('benchmark') === '1') {
    startLevel(query.get('level') || 3);
  }
})();
