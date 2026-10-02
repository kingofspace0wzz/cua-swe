(() => {
  "use strict";

  const FIXTURE_ID = "hextris-cascade-fixture-v1";
  const RED = "#e74c3c";
  const BLUE = "#3498db";
  const GREEN = "#2ecc71";
  const CASCADE_FALL_SPEED_MULTIPLIER = 0.12;
  const DELAYED_STACK_HOLD_MS = 20000;
  const CAUSAL_LEGEND_ID = "cua-swe-hextris-causal-legend";
  const DELAYED_STACK_ROLES = new Set([
    "cascade_mobile_c_v2",
  ]);

  function renderCausalLegend(visible) {
    const existing = document.getElementById(CAUSAL_LEGEND_ID);
    if (!visible) {
      if (existing) existing.remove();
      return;
    }
    const legend = existing || document.createElement("div");
    legend.id = CAUSAL_LEGEND_ID;
    legend.setAttribute("role", "note");
    legend.setAttribute(
      "aria-label",
      "Implementation recipe: queue each block when it re-settles. " +
        "Release its queued consolidation only when no non-deleted, " +
        "unsettled block of the same color remains. Flood-fill settled " +
        "blocks only. Do not check immediately or wait for the whole board."
    );
    Object.assign(legend.style, {
      position: "fixed",
      zIndex: "2147483647",
      top: "18px",
      left: "50%",
      transform: "translateX(-50%)",
      minWidth: "940px",
      boxSizing: "border-box",
      padding: "10px 24px 12px",
      border: "4px solid #3498db",
      borderRadius: "12px",
      background: "rgba(35, 49, 64, 0.97)",
      color: "#ffffff",
      fontFamily: "Arial, Helvetica, sans-serif",
      fontWeight: "700",
      textAlign: "center",
      lineHeight: "1.25",
      letterSpacing: "0.4px",
      pointerEvents: "none",
      boxShadow: "0 5px 18px rgba(0, 0, 0, 0.28)",
    });
    legend.innerHTML =
      '<div style="font-size:17px;color:#ffffff">IMPLEMENTATION RECIPE</div>' +
      '<div style="font-size:21px;color:#66b9ee">' +
      "1. ON RE-SETTLE: queueConsolidation(block)</div>" +
      '<div style="font-size:21px;color:#66b9ee">' +
      "2. RELEASE WHEN hasMovingColor(block.color) == false</div>" +
      '<div style="font-size:21px;color:#58dc93">' +
      "3. floodFill: ONLY settled === 1 NEIGHBORS</div>" +
      '<div style="font-size:17px;color:#ffcf6e">' +
      "NOT checked=1 IMMEDIATELY \u2022 NOT WHOLE-BOARD SETTLING</div>";
    if (!existing) document.body.appendChild(legend);
  }

  function restoreDelayedStackHold() {
    window.__cuaSweDelayedStackHoldActive = false;
    delete window.__cuaSweDelayedStackHoldUntil;
    delete window.__cuaSweDelayedStackHoldDistances;
  }

  function activateDelayedStackHold() {
    const distances = {};
    if (!window.MainHex || !Array.isArray(window.MainHex.blocks)) {
      throw new Error("Hextris attached blocks are unavailable");
    }
    for (const lane of window.MainHex.blocks) {
      for (const block of lane) {
        if (!DELAYED_STACK_ROLES.has(block.__cuaSweFixtureRole)) continue;
        distances[block.__cuaSweFixtureRole] = block.distFromHex;
        block.settled = 0;
        block.iter = 0;
      }
    }
    if (distances.cascade_mobile_c_v2 === undefined) {
      throw new Error("delayed cascade member is unavailable");
    }
    window.__cuaSweDelayedStackHoldDistances = distances;
    window.__cuaSweDelayedStackHoldUntil =
      Date.now() + DELAYED_STACK_HOLD_MS;
    window.__cuaSweDelayedStackHoldActive = true;
  }

  function releaseUnrelatedGreen() {
    if (!window.MainHex || !Array.isArray(window.MainHex.blocks)) {
      throw new Error("Hextris attached blocks are unavailable");
    }
    for (const lane of window.MainHex.blocks) {
      for (const block of lane) {
        if (block.__cuaSweFixtureRole !== "unrelated_green_v3") continue;
        block.settled = 0;
        return;
      }
    }
    throw new Error("unrelated green block is unavailable");
  }

  function wrapDelayedStackHold() {
    if (!window.MainHex.__cuaSweBaseDoesBlockCollide) {
      window.MainHex.__cuaSweBaseDoesBlockCollide =
        window.MainHex.doesBlockCollide;
    }
    const baseDoesBlockCollide =
      window.MainHex.__cuaSweBaseDoesBlockCollide;
    window.MainHex.doesBlockCollide = function heldStackCollision(
      block,
      position,
      attachedBlocks
    ) {
      const role = block && block.__cuaSweFixtureRole;
      if (
        position !== undefined &&
        window.__cuaSweDelayedStackHoldActive &&
        DELAYED_STACK_ROLES.has(role)
      ) {
        if (Date.now() < window.__cuaSweDelayedStackHoldUntil) {
          block.settled = 0;
          block.iter = 0;
          block.distFromHex =
            window.__cuaSweDelayedStackHoldDistances[role];
          window.MainHex.lastCombo = window.MainHex.ct;
          return;
        }
        restoreDelayedStackHold();
      }
      return baseDoesBlockCollide.call(
        window.MainHex,
        block,
        position,
        attachedBlocks
      );
    };
  }

  function restoreCascadePlaybackSpeed() {
    if (window.__cuaSweCascadePlaybackTimer != null) {
      window.clearInterval(window.__cuaSweCascadePlaybackTimer);
      window.__cuaSweCascadePlaybackTimer = null;
    }
    if (
      window.settings &&
      typeof window.__cuaSweCascadeBaseFallSpeed === "number"
    ) {
      window.settings.fallSpeedMultiplier =
        window.__cuaSweCascadeBaseFallSpeed;
    }
    window.__cuaSweCascadePlaybackActive = false;
    delete window.__cuaSweCascadeBaseFallSpeed;
  }

  function activateCascadePlaybackSlowdown() {
    restoreCascadePlaybackSpeed();
    window.__cuaSweCascadeBaseFallSpeed =
      window.settings.fallSpeedMultiplier;
    window.settings.fallSpeedMultiplier =
      CASCADE_FALL_SPEED_MULTIPLIER;
    window.__cuaSweCascadePlaybackActive = true;
    window.__cuaSweCascadePlaybackTimer = window.setInterval(() => {
      const delayed = protectedRoleState().cascade_mobile_c_v2;
      if (delayed && delayed.settled !== true) {
        window.MainHex.lastCombo = window.MainHex.ct;
      } else {
        restoreCascadePlaybackSpeed();
      }
    }, 10);
  }

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
      if (
        window.__cuaSweFixtureMode === "primary" &&
        before.before_score === 0 &&
        before.after_score === 9
      ) {
        activateCascadePlaybackSlowdown();
        activateDelayedStackHold();
        releaseUnrelatedGreen();
      }
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
      0,
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
    block.__cuaSweReleaseIter = 7;
    return block;
  }

  function releaseIncomingOnFirstRotation(block) {
    if (!window.MainHex.__cuaSweBaseRotate) {
      window.MainHex.__cuaSweBaseRotate = window.MainHex.rotate;
    }
    const baseRotate = window.MainHex.__cuaSweBaseRotate;
    window.MainHex.rotate = function releaseThenRotate() {
      block.iter = block.__cuaSweReleaseIter;
      window.MainHex.rotate = baseRotate;
      return baseRotate.apply(window.MainHex, arguments);
    };
  }

  window.__cuaSweInstallHextrisCascadeFixture = function install(options) {
    const config = options || {};
    restoreCascadePlaybackSpeed();
    restoreDelayedStackHold();
    window.__cuaSweFixtureMode = config.pairOnly ? "pair-only" : "primary";
    if (
      !window.MainHex ||
      !window.settings ||
      !window.waveone ||
      typeof window.Block !== "function"
    ) {
      throw new Error("Hextris runtime is not initialized");
    }
    renderCausalLegend(!config.pairOnly);

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
    wrapDelayedStackHold();

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
        3, GREEN, 0, 0.15, "unrelated_green_v3"
      );
      unrelatedGreen.distFromHex += 300;
      window.MainHex.blocks[0].push(
        makeAttached(0, RED, 0, 2, "red_support_a_v1"),
        makeAttached(0, BLUE, 1, 7, "cascade_mobile_a_v1"),
        makeAttached(0, BLUE, 2, 2.5, "cascade_mobile_c_v2")
      );
      window.MainHex.blocks[1].push(
        makeAttached(1, RED, 0, 2, "red_support_b_v1"),
        makeAttached(1, BLUE, 1, 7, "cascade_mobile_b_v1")
      );
      window.MainHex.blocks[5].push(
        makeAttached(5, BLUE, 0, 2, "cascade_anchor_v1")
      );
      window.MainHex.blocks[3].push(unrelatedGreen);
    }

    const incomingRed = makeIncomingRed();
    window.blocks.push(incomingRed);
    releaseIncomingOnFirstRotation(incomingRed);
    window.__cuaSweConsolidationTrace = [];
    wrapConsolidationTrace();
    if (typeof window.__hextrisClearTerminal === "function") {
      window.__hextrisClearTerminal();
    }
    return inspect();
  };

  window.__cuaSweInspectHextrisCascadeFixture = inspect;
})();
