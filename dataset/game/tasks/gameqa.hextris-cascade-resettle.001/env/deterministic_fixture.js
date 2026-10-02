(() => {
  "use strict";

  const FIXTURE_ID = "hextris-cascade-fixture-v1";
  const RED = "#e74c3c";
  const BLUE = "#3498db";
  const GREEN = "#2ecc71";

  function protectedRoleState() {
    const roles = {};
    if (!window.MainHex || !Array.isArray(window.MainHex.blocks)) {
      return roles;
    }
    for (const lane of window.MainHex.blocks) {
      for (const block of lane) {
        if (!block.__cuaSweFixtureRole) continue;
        roles[block.__cuaSweFixtureRole] = {
          settled: block.settled === 1,
          deleted: block.deleted,
          attachedLane: block.attachedLane,
          distFromHex: block.distFromHex,
        };
      }
    }
    return roles;
  }

  function inspect() {
    return {
      fixtureId: FIXTURE_ID,
      score: window.score,
      position: window.MainHex ? window.MainHex.position : null,
      activeBlocks: Array.isArray(window.blocks) ? window.blocks.length : null,
      roles: protectedRoleState(),
      consolidationTrace: window.__cuaSweConsolidationTrace || [],
      api: window.gameAPI ? window.gameAPI.getState() : null,
    };
  }

  function wrapConsolidationTrace() {
    if (window.__cuaSweConsolidationWrapped) return;
    const original = window.consolidateBlocks;
    if (typeof original !== "function") {
      throw new Error("consolidateBlocks is unavailable");
    }
    window.consolidateBlocks = function tracedConsolidation(hex, side, index) {
      const before = {
        side,
        index,
        before_score: window.score,
        roles: protectedRoleState(),
        ct: window.MainHex ? window.MainHex.ct : null,
      };
      const result = original.apply(this, arguments);
      before.after_score = window.score;
      window.__cuaSweConsolidationTrace.push(before);
      return result;
    };
    window.__cuaSweConsolidationWrapped = true;
  }

  function makeAttached(lane, color, index, iter, role) {
    const fallingLane = (window.MainHex.sides - lane) % window.MainHex.sides;
    const base =
      (window.MainHex.sideLength / 2) * Math.sqrt(3) +
      window.settings.blockHeight * index;
    const block = new window.Block(fallingLane, color, iter, base, true);
    block.initializing = 0;
    block.settled = 1;
    block.removed = 1;
    block.checked = 0;
    block.deleted = 0;
    block.opacity = 1;
    block.tint = 0;
    block.attachedLane = lane;
    block.angle = 60 + lane * 60;
    block.targetAngle = block.angle;
    if (role) block.__cuaSweFixtureRole = role;
    return block;
  }

  function makeIncomingRed() {
    const block = new window.Block(
      5,
      RED,
      7,
      window.settings.startDist * window.settings.scale
    );
    block.initializing = 0;
    block.settled = 0;
    block.removed = 0;
    block.checked = 0;
    block.deleted = 0;
    block.opacity = 1;
    block.tint = 0;
    block.__cuaSweFixtureRole = "incoming_red_v1";
    return block;
  }

  window.__cuaSweInstallHextrisCascadeFixture = function install(options) {
    const config = options || {};
    if (
      !window.MainHex ||
      !window.settings ||
      !window.waveone ||
      typeof window.Block !== "function"
    ) {
      throw new Error("Hextris runtime is not initialized");
    }

    window.score = 0;
    window.prevScore = 0;
    window.scoreAdditionCoeff = 1;
    window.blocks = [];
    for (const key of Object.keys(window.history)) {
      if (/^\d+$/.test(key)) {
        delete window.history[key];
      }
    }
    window.rush = 1;
    window.gameState = 1;
    window.MainHex.ct = 100;
    window.MainHex.position = 0;
    window.MainHex.angle = 30;
    window.MainHex.targetAngle = 30;
    window.MainHex.angularVelocity = 0;
    window.MainHex.lastRotate = Date.now() - 1000;
    window.MainHex.lastCombo =
      window.MainHex.ct - window.settings.comboTime - 1;
    window.MainHex.blocks = Array.from(
      { length: window.MainHex.sides },
      () => []
    );

    window.waveone.currentFunction = function noProtectedWaveGeneration() {};
    window.waveone.firstDropDone = true;
    window.waveone.lastGen = window.waveone.dt;
    window.waveone.nextGen = 1000000000;

    if (config.pairOnly) {
      window.MainHex.blocks[1].push(
        makeAttached(1, RED, 0, 2, "pair_red_v1")
      );
    } else {
      const unrelatedGreen = makeAttached(
        0, GREEN, 3, 0.15, "unrelated_green_v3"
      );
      unrelatedGreen.distFromHex += 600;
      window.MainHex.blocks[0].push(
        makeAttached(0, RED, 0, 2, "red_support_a_v1"),
        makeAttached(0, BLUE, 1, 7, "cascade_mobile_a_v1"),
        makeAttached(0, BLUE, 2, 1.5, "cascade_mobile_c_v2"),
        unrelatedGreen
      );
      window.MainHex.blocks[1].push(
        makeAttached(1, RED, 0, 2, "red_support_b_v1"),
        makeAttached(1, BLUE, 1, 7, "cascade_mobile_b_v1")
      );
      window.MainHex.blocks[5].push(
        makeAttached(5, BLUE, 0, 2, "cascade_anchor_v1")
      );
    }

    window.blocks.push(makeIncomingRed());
    window.__cuaSweConsolidationTrace = [];
    wrapConsolidationTrace();
    if (typeof window.__hextrisClearTerminal === "function") {
      window.__hextrisClearTerminal();
    }
    return inspect();
  };

  window.__cuaSweInspectHextrisCascadeFixture = inspect;
})();
