(function () {
  "use strict";

  const STEP = 1 / 60;
  const CEILING = 8;
  const FLOOR = 400;
  const PIPE_WIDTH = 58;
  const LAB_BUTTONS = Object.freeze([
    Object.freeze({x: 30, y: 156, width: 180, height: 138}),
    Object.freeze({x: 230, y: 156, width: 180, height: 138}),
    Object.freeze({x: 430, y: 156, width: 180, height: 138}),
  ]);
  const BACK_BUTTON = Object.freeze({x: 454, y: 392, width: 156, height: 48});
  const RUN_BUTTON = Object.freeze({x: 224, y: 344, width: 192, height: 52});
  const targetArc = (values, startX = 215) => Object.freeze(
    values.map((y, index) => Object.freeze({
      pipeX: startX - index * 5,
      y,
    }))
  );
  const DRILLS = Object.freeze([
    Object.freeze({
      id: 1,
      slug: "tap",
      name: "TAP ARC",
      note: "quick release",
      birdY: 270,
      layout: Object.freeze({x: 215, gapTop: 205, gapBottom: 335}),
      finishX: 159,
      targetImpulse: 220,
      target: targetArc([
        270, 270.1722, 266.6778, 263.3556, 260.2056, 257.2278, 254.4222,
        251.7889, 249.3278, 247.0389, 244.9222, 242.9778, 241.2056,
        239.6056, 238.1778, 236.9222, 235.8389, 234.9278, 234.1889,
        233.6222, 233.2278, 233.0056, 232.9556, 233.0778, 233.3722,
        233.8389, 234.4778, 235.2889,
      ]),
      script: Object.freeze([
        Object.freeze({frame: 0, kind: "press"}),
        Object.freeze({frame: 0, kind: "release"}),
      ]),
    }),
    Object.freeze({
      id: 2,
      slug: "held",
      name: "HELD ARC",
      note: "held control",
      birdY: 270,
      layout: Object.freeze({x: 215, gapTop: 190, gapBottom: 325}),
      finishX: 80,
      targetImpulse: 250,
      target: targetArc([
        270, 270.1722, 270.5167, 271.0333, 271.7222, 267.7278, 263.9056,
        260.2556, 256.7778, 253.4722, 250.3389, 247.3778, 244.5889,
        241.9722, 239.5278, 237.2556, 235.1556, 233.2278, 231.4722,
        229.8889, 228.4778, 227.2389, 226.1722, 225.2778, 224.5556,
        224.0056, 223.6278, 223.4222,
      ]),
      script: Object.freeze([
        Object.freeze({frame: 0, kind: "press"}),
        Object.freeze({frame: 3, kind: "release"}),
      ]),
    }),
    Object.freeze({
      id: 3,
      slug: "late",
      name: "LATE CONTACT",
      note: "edge recovery",
      birdY: 306,
      layout: Object.freeze({x: 165, gapTop: 205, gapBottom: 315}),
      finishX: 80,
      targetImpulse: 220,
      target: targetArc([
        306, 304.1722, 302.5167, 301.0333, 299.7222, 298.5833, 297.6167,
        296.8222, 296.2, 295.75, 295.4722, 295.3667, 295.4333, 295.6722,
        296.0833, 296.6667, 297.4222, 298.35,
      ], 165),
      script: Object.freeze([
        Object.freeze({frame: 0, kind: "press"}),
        Object.freeze({frame: 0, kind: "release"}),
      ]),
    }),
  ]);

  const inside = (point, rect) => (
    point
    && point.x >= rect.x
    && point.x <= rect.x + rect.width
    && point.y >= rect.y
    && point.y <= rect.y + rect.height
  );

  class FlappyGame {
    constructor(canvas) {
      this.canvas = canvas;
      this.input = new window.FlightInput(canvas);
      this.bird = new window.Bird();
      this.pipeField = new window.PipeField();
      this.renderer = new window.Renderer(canvas);
      this.phase = "lab";
      this.score = 0;
      this.attempts = 0;
      this.elapsed = 0;
      this.accumulator = 0;
      this.lastTimestamp = null;
      this.lastCollision = null;
      this.labResults = {};
      this.drill = this.drillState(null, false, null, 0, 0, null);
      this.trail = [];
      this.lastBirdFrame = this.bird.snapshot();
      this.lastPipeFrame = this.emptyPipeFrame();
      this.events = [];
      this.controlTrace = [];
      this.drillReceipt = [];
      this.actualImpulse = 0;
      this.world = this.composeWorld();
      this.renderer.draw(this.world);
      requestAnimationFrame((time) => this.frame(time));
    }

    emptyPipeFrame() {
      return Object.freeze({
        scored: 0,
        score_events: Object.freeze([]),
        collision: null,
        pipes: this.pipeField.snapshot(),
      });
    }

    drillState(index, active, outcome, received, score, audit) {
      const spec = index === null ? null : DRILLS[index];
      return Object.freeze({
        index,
        id: spec ? spec.id : null,
        slug: spec ? spec.slug : null,
        name: spec ? spec.name : null,
        active,
        outcome,
        received,
        score,
        audit,
      });
    }

    reset() {
      this.phase = "lab";
      this.score = 0;
      this.elapsed = 0;
      this.accumulator = 0;
      this.lastCollision = null;
      this.labResults = {};
      this.drill = this.drillState(null, false, null, 0, 0, null);
      this.trail = [];
      this.events = [];
      this.controlTrace = [];
      this.drillReceipt = [];
      this.actualImpulse = 0;
      this.bird.reset();
      this.pipeField.reset();
      this.input.clear();
      this.lastBirdFrame = this.bird.snapshot();
      this.lastPipeFrame = this.emptyPipeFrame();
      this.world = this.composeWorld();
      this.renderer.draw(this.world);
      return this.getState();
    }

    showLab() {
      this.phase = "lab";
      this.elapsed = 0;
      this.lastCollision = null;
      this.drill = this.drillState(null, false, null, 0, this.labScore(), null);
      this.trail = [];
      this.drillReceipt = [];
      this.actualImpulse = 0;
      this.bird.reset();
      this.pipeField.reset();
      this.input.clear();
      this.lastBirdFrame = this.bird.snapshot();
      this.lastPipeFrame = this.emptyPipeFrame();
      this.record("lab-ready", {completed: Object.keys(this.labResults).length});
    }

    labScore() {
      return Object.values(this.labResults).filter((value) => value === "clear").length;
    }

    launchDrill(index) {
      const spec = DRILLS[index];
      if (!spec) return;
      this.phase = "drill";
      this.elapsed = 0;
      this.lastCollision = null;
      this.events = [];
      this.bird.reset();
      this.bird.y = spec.birdY;
      this.bird.pose = this.bird.snapshotPose();
      this.pipeField.reset({kind: "drill", id: spec.id, layout: spec.layout});
      this.lastBirdFrame = this.bird.snapshot();
      this.lastPipeFrame = this.emptyPipeFrame();
      this.drillFrame = 0;
      this.drill = this.drillState(index, true, null, 0, this.labScore(), null);
      this.trail = [];
      this.drillReceipt = [];
      this.actualImpulse = 0;
      this.captureTrail();
      this.input.clear();
      this.record("drill-ready", {id: spec.id, name: spec.name});
    }

    applyDrillScript() {
      const spec = DRILLS[this.drill.index];
      for (const event of spec.script) {
        if (event.frame !== this.drillFrame) continue;
        if (event.kind === "press") this.input.press("drill");
        if (event.kind === "release") this.input.release("drill");
      }
    }

    captureTrail() {
      const pipe = this.pipeField.pipes[0];
      this.trail.push(Object.freeze({
        x: this.lastBirdFrame.x,
        y: this.lastBirdFrame.y,
        bounds: this.lastBirdFrame.bounds,
        pipe_x: pipe ? pipe.x : null,
      }));
    }

    captureReceipt(control) {
      if (!control.receipt || control.receipt.length === 0) return;
      for (const edge of control.receipt) {
        const item = Object.freeze({
          kind: edge.kind,
          source: edge.source,
          step: this.phase === "drill" ? this.drillFrame : null,
          held_ms: edge.held_ms,
        });
        this.controlTrace.push(Object.freeze({
          ...item,
          phase: this.phase,
          elapsed: Number(this.elapsed.toFixed(4)),
        }));
        if (this.phase === "drill") this.drillReceipt.push(item);
      }
    }

    contactSegment(spec) {
      if (this.lastCollision && this.lastCollision.motion_segment) {
        return this.lastCollision.motion_segment;
      }
      if (this.trail.length < 2) return null;
      const start = this.trail[0];
      const end = this.trail[1];
      const startBottom = start.bounds.bottom;
      const endBottom = end.bounds.bottom;
      const threshold = spec.layout.gapBottom;
      const startContact = startBottom > threshold;
      const endContact = endBottom > threshold;
      if (!startContact || endContact || startBottom === endBottom) return null;
      const intervalEnd = Math.max(
        0,
        Math.min(1, (startBottom - threshold) / (startBottom - endBottom))
      );
      return Object.freeze({
        start: Object.freeze({
          x: start.x,
          y: start.y,
          pipe_x: start.pipe_x,
          contact: true,
        }),
        end: Object.freeze({
          x: end.x,
          y: end.y,
          pipe_x: end.pipe_x,
          contact: false,
        }),
        interval: Object.freeze({
          start: 0,
          end: intervalEnd,
          marker: intervalEnd / 2,
        }),
        endpoint_safe: true,
      });
    }

    visualAudit() {
      const spec = DRILLS[this.drill.index];
      let closest = null;
      let contact = null;
      for (let index = 0; index < this.trail.length; index += 1) {
        const sample = this.trail[index];
        const pipeLeft = sample.pipe_x;
        const pipeRight = pipeLeft + PIPE_WIDTH;
        const bird = sample.bounds;
        const overlap = bird.right > pipeLeft && bird.left < pipeRight;
        const touches = overlap && (
          bird.top < spec.layout.gapTop || bird.bottom > spec.layout.gapBottom
        );
        const distance = Math.abs((pipeLeft + PIPE_WIDTH / 2) - sample.x);
        if (!closest || distance < closest.distance) {
          closest = {index, distance, sample};
        }
        if (!contact && touches) contact = {index, sample};
      }
      const chosen = contact || closest;
      const segment = spec.slug === "late" ? this.contactSegment(spec) : null;
      return Object.freeze({
        contact_visible: Boolean(contact),
        contact_interval: segment ? segment.interval : null,
        motion_segment: segment,
        endpoint_safe: segment ? segment.endpoint_safe : null,
        sample_index: chosen ? chosen.index : null,
        bird: chosen ? chosen.sample.bounds : null,
        point: chosen ? Object.freeze({
          x: chosen.sample.x,
          y: chosen.sample.y,
        }) : null,
        gap_top: spec.layout.gapTop,
        gap_bottom: spec.layout.gapBottom,
      });
    }

    finishDrill(outcome, collision) {
      const spec = DRILLS[this.drill.index];
      this.phase = "drill_result";
      this.lastCollision = collision || null;
      if (!Object.prototype.hasOwnProperty.call(this.labResults, spec.slug)) {
        this.labResults[spec.slug] = outcome;
      }
      const audit = this.visualAudit();
      const score = this.labScore();
      this.drill = this.drillState(
        this.drill.index,
        false,
        outcome,
        this.drill.received,
        score,
        audit
      );
      this.record("drill-result", {
        id: spec.id,
        outcome,
        score,
        contact_visible: audit.contact_visible,
      });
      this.input.clear();
    }

    start() {
      this.phase = "playing";
      this.score = 0;
      this.elapsed = 0;
      this.lastCollision = null;
      this.drill = this.drillState(null, false, null, 0, this.labScore(), null);
      this.trail = [];
      this.events = [];
      this.controlTrace = [];
      this.drillReceipt = [];
      this.actualImpulse = 0;
      this.bird.reset();
      this.pipeField.reset();
      this.input.clear();
      this.lastBirdFrame = this.bird.snapshot();
      this.lastPipeFrame = this.emptyPipeFrame();
      this.attempts += 1;
      this.record("start", {});
    }

    frame(timestamp) {
      if (this.lastTimestamp === null) this.lastTimestamp = timestamp;
      const delta = Math.min(0.05, (timestamp - this.lastTimestamp) / 1000);
      this.lastTimestamp = timestamp;
      this.accumulator += delta;
      while (this.accumulator >= STEP) {
        this.update(STEP);
        this.accumulator -= STEP;
      }
      this.world = this.composeWorld();
      this.renderer.draw(this.world);
      requestAnimationFrame((time) => this.frame(time));
    }

    update(dt) {
      if (this.phase === "drill") this.applyDrillScript();
      const control = this.input.sample();
      this.captureReceipt(control);

      if (this.phase === "lab") {
        if (control.command !== null) {
          this.launchDrill(control.command);
          return;
        }
        if (control.pressed) {
          const index = LAB_BUTTONS.findIndex((button) => inside(control.pointer, button));
          if (index >= 0) {
            this.launchDrill(index);
          } else if (inside(control.pointer, RUN_BUTTON)) {
            this.start();
          }
        }
        return;
      }
      if (this.phase === "drill_result") {
        if (control.pressed && (
          control.source !== "pointer" || inside(control.pointer, BACK_BUTTON)
        )) {
          this.showLab();
        }
        return;
      }
      if (this.phase === "dead") {
        if (control.pressed) this.start();
        return;
      }

      this.elapsed += dt;
      if (this.phase === "drill" && !this.drill.received) {
        if (!control.pressed) return;
        this.drill = this.drillState(
          this.drill.index,
          true,
          null,
          this.drill.received + 1,
          this.drill.score,
          null
        );
        this.record("pulse-received", {id: this.drill.id});
      }

      this.lastBirdFrame = this.bird.step(dt, control);
      if (this.lastBirdFrame.last_impulse) {
        this.actualImpulse = this.lastBirdFrame.last_impulse;
      }
      this.lastPipeFrame = this.pipeField.step(dt, this.lastBirdFrame);
      if (this.phase === "drill") {
        this.captureTrail();
        this.drillFrame += 1;
        if (this.lastPipeFrame.collision) {
          this.finishDrill("bump", this.lastPipeFrame.collision);
          return;
        }
        const drillPipe = this.lastPipeFrame.pipes[0];
        const spec = DRILLS[this.drill.index];
        if (drillPipe && drillPipe.x <= spec.finishX) {
          this.finishDrill(this.lastPipeFrame.scored ? "clear" : "bump", null);
        }
        return;
      }

      if (this.lastPipeFrame.scored) {
        this.score += this.lastPipeFrame.scored;
        for (const crossing of this.lastPipeFrame.score_events) {
          this.record("score", {
            score: this.score,
            pipe_id: crossing.pipe_id,
            pipe_right: crossing.pipe_right,
            bird_left: crossing.bird_left,
          });
        }
      }

      const bird = this.lastBirdFrame.bounds;
      let collision = this.lastPipeFrame.collision;
      if (!collision && bird.top < CEILING) collision = {kind: "ceiling", bird};
      if (!collision && bird.bottom > FLOOR) collision = {kind: "ground", bird};
      if (collision) this.die(collision);
    }

    die(collision) {
      if (this.phase !== "playing") return;
      this.phase = "dead";
      this.lastCollision = collision;
      this.record("collision", collision);
      this.input.clear();
    }

    record(type, details) {
      this.events.push(Object.freeze({
        index: this.events.length,
        type,
        elapsed: Number(this.elapsed.toFixed(4)),
        details,
      }));
    }

    composeWorld() {
      return Object.freeze({
        phase: this.phase,
        score: this.score,
        attempts: this.attempts,
        elapsed: this.elapsed,
        bird: this.lastBirdFrame,
        pipes: this.lastPipeFrame.pipes,
        collision: this.lastCollision,
        drill: this.drill,
        lab_results: Object.freeze({...this.labResults}),
        trail: Object.freeze(this.trail.slice()),
        drill_receipt: Object.freeze(this.drillReceipt.slice()),
        actual_impulse: this.actualImpulse,
        control_trace: Object.freeze(this.controlTrace.slice()),
        ui: Object.freeze({
          drill_buttons: LAB_BUTTONS,
          back_button: BACK_BUTTON,
          run_button: RUN_BUTTON,
          drills: DRILLS,
        }),
      });
    }

    getState() {
      this.world = this.composeWorld();
      return this.world;
    }
  }

  window.__flappyGame = new FlappyGame(document.getElementById("game"));
})();
