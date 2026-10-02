
(function() {
  'use strict';

  const GAME_ID = '06_captaincallisto';
  let episodeCount = 0;
  let terminalEvent = null;

  function remainingCoins() {
    return entities.filter((entity) => entity instanceof Coin && entity.health > 0).length;
  }

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

  function startLevel(requestedLevel) {
    const nextLevel = Math.max(1, Math.min(10, Number(requestedLevel) || 3));
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
      const appliedLevel = startLevel(config && config.level);
      return {ok: true, applied: {seed: 44, level: appliedLevel}};
    },
    reset: async function(config) {
      const appliedLevel = startLevel(config && config.level);
      return {
        ok: true,
        method: 'inplace',
        applied: {seed: 44, level: appliedLevel},
      };
    },
    getState: function() {
      const remaining = remainingCoins();
      const collectedByWorld = availableCoins - remaining;
      const firstLift = entities.find(
          (entity) => entity.debugLabel === 'first-lift');
      const secondLift = entities.find(
          (entity) => entity.debugLabel === 'second-lift');
      const completed = gameState === GameState.AFTER_LEVEL || terminalEvent !== null;
      const reportedCoins = terminalEvent ? terminalEvent['coins'] : coins;
      const reportedTotal = terminalEvent ? terminalEvent['coinsTotal'] : availableCoins;
      return {
        schemaVersion: '1.0',
        gameId: GAME_ID,
        seed: 44,
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
            velocity_x: player.velocity[0],
            velocity_y: player.velocity[1],
            velocity_z: player.velocity[2],
            jetpack_visible: player.jetpack,
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
          deaths: player.health > 0 ? 0 : 1,
        },
        debug: {
          benchmark_mode: BENCHMARK_MODE,
          episode_count: episodeCount,
          game_state: gameState,
          grounded: player.isGrounded(),
          jetpack_sound_active: Boolean(jetpackSound),
          jetpack_player_cycle: player.jetpackCycle,
          jetpack_thrusting: player.jetpackThrusting,
          support: player.groundedPlatform ?
              player.groundedPlatform.debugLabel || 'platform' : null,
          motion_phase: player.motionPhase,
          motion_local_x: player.motionLocal[0],
          motion_reference_x: player.motionReference[0],
          interaction_start: {
            x: player.interactionStart[0],
            y: player.interactionStart[1],
            z: player.interactionStart[2],
          },
          interaction_end: {
            x: player.interactionEnd[0],
            y: player.interactionEnd[1],
            z: player.interactionEnd[2],
          },
          first_lift_x: firstLift ? firstLift.pos[0] : null,
          second_lift_x: secondLift ? secondLift.pos[0] : null,
        },
      };
    },
  };

  const query = new URLSearchParams(window.location.search);
  if (query.get('benchmark') === '1') {
    startLevel(query.get('level') || 3);
  }
})();
