(function () {
  "use strict";

  function finite(value) {
    return Number.isFinite(value) ? Number(value.toFixed(4)) : null;
  }

  function serializeBounds(bounds) {
    if (!bounds) return null;
    return {
      left: finite(bounds.left),
      right: finite(bounds.right),
      top: finite(bounds.top),
      bottom: finite(bounds.bottom),
      width: finite(bounds.width),
      height: finite(bounds.height),
    };
  }

  function state() {
    const world = window.__flappyGame.getState();
    const bird = world.bird;
    const nextPipe = world.pipes.find((pipe) => !pipe.scored) || null;
    return {
      schemaVersion: "1.0",
      gameId: "13_flappy-bird",
      seed: 42,
      timestampMs: Date.now(),
      gameTimeMs: finite(world.elapsed * 1000),
      status: world.phase === "playing" || world.phase === "drill"
        ? "playing"
        : (world.phase === "dead" ? "terminal" : "menu"),
      is_actionable: world.phase !== "drill",
      terminal: {
        isTerminal: world.phase === "dead",
        outcome: world.phase === "dead" ? "fail" : null,
        reason: world.collision ? world.collision.kind : null,
      },
      game_state: {
        score: world.score,
        level: 1,
        player: {
          x: finite(bird.x),
          y: finite(bird.y),
          vy: finite(bird.velocity_y),
          rotation: finite(bird.rotation),
          flap_age: finite(bird.flap_clock),
          bounds: serializeBounds(bird.bounds),
        },
        environment: {
          phase: world.phase,
          flight_lab: {
            selected: world.drill.slug,
            name: world.drill.name,
            active: world.drill.active,
            outcome: world.drill.outcome,
            pulse_count: world.drill.received,
            score: world.drill.score,
            viewed: Object.keys(world.lab_results).length,
            results: world.lab_results,
            visual_audit: world.drill.audit,
            input_receipt: world.drill_receipt,
            actual_impulse: finite(world.actual_impulse),
            target_impulse: world.drill.index === null
              ? null
              : finite(world.ui.drills[world.drill.index].targetImpulse),
            target: world.drill.index === null
              ? []
              : world.ui.drills[world.drill.index].target.map((point) => ({
                pipe_x: finite(point.pipeX),
                y: finite(point.y),
              })),
            trail: world.trail.map((point) => ({
              x: finite(point.x),
              y: finite(point.y),
              pipe_x: finite(point.pipe_x),
            })),
          },
          next_pipe: nextPipe ? {
            id: nextPipe.id,
            x: finite(nextPipe.x),
            width: nextPipe.width,
            gap_top: nextPipe.gap_top,
            gap_bottom: nextPipe.gap_bottom,
          } : null,
          floor_y: 400,
        },
        completion_progress: finite(Math.min(1, world.score / 3)),
      },
      metrics: {
        primary_score: world.score,
        pipes_passed: world.score,
        attempts: world.attempts,
        pipes_visible: world.pipes.length,
      },
      debug: {
        collision: world.collision,
        recent_events: window.__flappyGame.events.slice(-12),
      },
      control_trace: world.control_trace,
    };
  }

  window.gameAPI = Object.freeze({
    version: "1.0",
    capabilities: Object.freeze({
      supports_seed: true,
      supports_level_select: false,
      supports_inplace_reset: true,
      supports_reload_reset: true,
      provides_actionable_flag: true,
    }),
    init: async function () {
      return {ok: true, applied: {seed: 42, level: 1}};
    },
    reset: async function () {
      window.__flappyGame.reset();
      return {ok: true, method: "inplace", applied: {seed: 42, level: 1}};
    },
    getState: state,
  });
})();
