(function (global) {
  "use strict";

  var WIDTH = 960;
  var HEIGHT = 600;
  var FIXED_STEP = 1 / 120;
  var TILE = { id: "north-relay", x: 390, y: 92, w: 180, h: 28 };

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function VectorRelay(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.contacts = new global.RelayContact.ContactBook();
    this.lane = new global.RelayCommit.RelayLane(0.98);
    this.balance = new global.PulseBalance();
    this.clock = 0;
    this.lastFrame = performance.now();
    this.running = true;
    this.bindInput();
    this.resetChallenge();
    requestAnimationFrame(this.frame.bind(this));
  }

  VectorRelay.prototype.bindInput = function () {
    var self = this;
    global.addEventListener("keydown", function (event) {
      if (["ArrowLeft", "ArrowRight", "Space", "KeyR"].indexOf(event.code) >= 0) {
        event.preventDefault();
      }
      if (event.repeat) return;
      if (event.code === "ArrowLeft") self.shiftReceiver(-1);
      if (event.code === "ArrowRight") self.shiftReceiver(1);
      if (event.code === "Space") self.launch();
      if (event.code === "KeyR") self.redock();
    });
  };

  VectorRelay.prototype.resetChallenge = function () {
    this.contacts.clear();
    this.lane.reset();
    this.score = 0;
    this.lives = 3;
    this.status = "playing";
    this.lastSignal = "READY";
    this.tile = {
      id: TILE.id,
      x: TILE.x,
      y: TILE.y,
      w: TILE.w,
      h: TILE.h,
      phase: "armed",
      contacts: 1,
      lastCommit: "primed",
      commits: 1
    };
    this.paddle = {
      x: 390,
      y: 548,
      w: 180,
      h: 18,
      step: 28
    };
    this.launchCount = 0;
    this.lossCount = 0;
    this.bounceCount = 0;
    this.attachmentCount = 0;
    this.attachBall("challenge-reset");
    this.updatePanel(
      "CHALLENGE PRIMED",
      "Relay is already armed. Press Space to launch a return.",
      true
    );
    this.syncReadout();
  };

  VectorRelay.prototype.attachBall = function (reason) {
    this.contacts.clear();
    this.attachmentCount += 1;
    this.ball = {
      x: this.paddle.x + this.paddle.w / 2,
      y: this.paddle.y - 12,
      r: 10,
      vx: 0,
      vy: 0,
      attached: true,
      body: this.contacts.open("orb"),
      owner: this.lane.open(this.dockPort()),
      attachReason: reason,
      route: null,
      routeTime: 0,
      overlapSlices: 0
    };
  };

  VectorRelay.prototype.dockPort = function () {
    return this.paddle.x < 382 ? "west" : "receiver";
  };

  VectorRelay.prototype.shiftReceiver = function (direction) {
    if (this.status !== "playing") return;
    this.paddle.x = clamp(
      this.paddle.x + direction * this.paddle.step,
      44,
      WIDTH - 44 - this.paddle.w
    );
    if (!this.ball.attached) return;
    this.refreshDockOwner();
    this.ball.x = this.paddle.x + this.paddle.w / 2;
    this.ball.y = this.paddle.y - this.ball.r - 2;
    if (this.lane.pending.length) {
      this.lastSignal = "DOCK " + this.ball.owner.port.toUpperCase();
      this.syncReadout();
    }
  };

  VectorRelay.prototype.refreshDockOwner = function () {
    if (!this.ball.attached) return;
    var port = this.dockPort();
    if (this.ball.owner.port === port) return;
    this.ball.owner = this.lane.open(port);
  };

  VectorRelay.prototype.redock = function () {
    if (this.status !== "playing" || this.ball.attached) return;
    this.attachBall("manual-redock");
    this.lastSignal = "RECALLED";
    this.updatePanel("PASS RECALLED", "Relay stays armed. Press Space to relaunch.", true);
    this.syncReadout();
  };

  VectorRelay.prototype.launch = function () {
    if (this.status !== "playing" || !this.ball.attached) return;
    this.ball.attached = false;
    this.ball.routeTime = 0;
    this.ball.route = this.tile.phase === "idle" ? "arming" : "return";
    this.ball.vx = this.ball.route === "arming" ? 55 : -35;
    this.ball.vy = this.ball.route === "arming" ? -420 : -560;
    this.launchCount += 1;
    this.updatePanel("", "", false);
  };

  VectorRelay.prototype.frame = function (now) {
    if (!this.running) return;
    var elapsed = Math.min(0.05, Math.max(0, (now - this.lastFrame) / 1000));
    this.lastFrame = now;
    this.clock += elapsed;
    while (elapsed >= FIXED_STEP) {
      this.update(FIXED_STEP);
      elapsed -= FIXED_STEP;
    }
    this.update(elapsed);
    this.commitPending();
    this.draw();
    requestAnimationFrame(this.frame.bind(this));
  };

  VectorRelay.prototype.update = function (dt) {
    if (dt <= 0 || this.status !== "playing") return;
    if (this.ball.attached) {
      this.refreshDockOwner();
      this.ball.x = this.paddle.x + this.paddle.w / 2;
      this.ball.y = this.paddle.y - this.ball.r - 2;
      return;
    }
    this.integrateBall(dt, 0);
  };

  VectorRelay.prototype.integrateBall = function (dt, depth) {
    if (depth > 5 || this.ball.attached || this.status !== "playing") return;
    var ball = this.ball;
    ball.routeTime += dt;
    ball.x += ball.vx * dt;
    ball.y += ball.vy * dt;

    var overlaps = ball.x + ball.r >= this.tile.x &&
      ball.x - ball.r <= this.tile.x + this.tile.w &&
      ball.y + ball.r >= this.tile.y &&
      ball.y - ball.r <= this.tile.y + this.tile.h;

    if (overlaps && ball.vy < 0) {
      var claim = this.contacts.claim(ball.body, this.tile);
      if (claim.accepted) this.queueRelay(claim.ticket);
      ball.vy = ball.route === "return" ? 180 : Math.abs(ball.vy);
      if (ball.route === "return") {
        ball.vx = -300;
        this.updatePanel(
          "RETURN REACHED",
          "Press R to recall this pass, or wait for replacement.",
          true
        );
      }
      this.bounceCount += 1;
      ball.overlapSlices += 1;
      if (depth === 0) {
        this.integrateBall(dt * 0.22, depth + 1);
      }
      return;
    }

    if (!overlaps) this.contacts.separate(ball.body, this.tile);

    if (ball.x - ball.r <= 35 || ball.x + ball.r >= WIDTH - 35) {
      ball.vx = -ball.vx;
      ball.x = clamp(ball.x, 35 + ball.r, WIDTH - 35 - ball.r);
    }

    if (ball.vy > 0 && ball.y > 310 && ball.route === "arming") {
      ball.vx = 210;
    }

    if (ball.y - ball.r > HEIGHT) {
      this.loseBall();
      return;
    }

    if (ball.vy > 0 && ball.y + ball.r >= this.paddle.y &&
        ball.y - ball.r <= this.paddle.y + this.paddle.h &&
        ball.x >= this.paddle.x && ball.x <= this.paddle.x + this.paddle.w) {
      ball.y = this.paddle.y - ball.r;
      ball.vy = -Math.abs(ball.vy);
    }
  };

  VectorRelay.prototype.queueRelay = function (ticket) {
    this.lane.defer(ticket, this.tile.phase, this.ball.owner, this.clock);
    this.lastSignal = "REACHED";
    this.syncReadout();
  };

  VectorRelay.prototype.commitPending = function () {
    var transition = this.lane.take(this.clock, this.ball.owner);
    if (!transition || this.tile.lastCommit === transition.id) return;
    this.tile.lastCommit = transition.id;
    this.tile.contacts += 1;
    this.tile.commits += 1;
    if (this.tile.phase === "idle") {
      this.tile.phase = "armed";
      this.updatePanel("RELAY ARMED", "Signal stored. Keep the circuit alive.", true);
      setTimeout(function (self) {
        if (self.status === "playing" && !self.ball.attached) self.updatePanel("", "", false);
      }, 420, this);
    } else if (this.tile.phase === "armed") {
      this.tile.phase = "cleared";
      this.score += 500;
      this.status = "complete";
      this.lastSignal = "SETTLED";
      this.ball.vx = 0;
      this.ball.vy = 0;
      this.updatePanel("CIRCUIT COMPLETE", "+500 relay completion", true);
      this.syncReadout();
    }
  };

  VectorRelay.prototype.loseBall = function () {
    this.lives -= 1;
    this.lossCount += 1;
    this.syncReadout();
    if (this.lives <= 0) {
      this.status = "failed";
      this.updatePanel("CIRCUIT LOST", "Press R to restart the challenge.", true);
      return;
    }
    this.attachBall("life-replacement");
    this.lastSignal = "HANDOFF";
    this.updatePanel("ORB REPLACED", "Relay remains armed. Press Space to relaunch.", true);
    this.syncReadout();
  };

  VectorRelay.prototype.updatePanel = function (title, copy, visible) {
    var panel = document.getElementById("panel");
    document.getElementById("panel-title").textContent = title;
    document.getElementById("panel-copy").textContent = copy;
    panel.classList.toggle("hidden", !visible);
  };

  VectorRelay.prototype.syncReadout = function () {
    document.getElementById("score").textContent = String(this.score).padStart(6, "0");
    document.getElementById("lives").textContent = String(this.lives).padStart(2, "0");
    document.getElementById("relay-state").textContent = this.tile.phase.toUpperCase();
    document.getElementById("return-state").textContent = this.lastSignal;
  };

  VectorRelay.prototype.draw = function () {
    var ctx = this.ctx;
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    ctx.fillStyle = "#061018";
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    ctx.strokeStyle = "rgba(80, 170, 188, 0.13)";
    ctx.lineWidth = 1;
    for (var x = 40; x < WIDTH; x += 40) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, HEIGHT); ctx.stroke();
    }
    for (var y = 40; y < HEIGHT; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(WIDTH, y); ctx.stroke();
    }

    ctx.strokeStyle = "#315d68";
    ctx.lineWidth = 3;
    ctx.strokeRect(34, 24, WIDTH - 68, HEIGHT - 48);
    this.balance.draw(ctx, this.lane.snapshot(), this.tile.commits);

    var armed = this.tile.phase === "armed";
    var cleared = this.tile.phase === "cleared";
    ctx.save();
    if (armed) {
      ctx.shadowColor = "#f0ca4d";
      ctx.shadowBlur = 22;
    }
    ctx.fillStyle = cleared ? "#17343c" : armed ? "#f0ca4d" : "#1c4c59";
    ctx.fillRect(this.tile.x, this.tile.y, this.tile.w, this.tile.h);
    ctx.strokeStyle = cleared ? "#4e7b83" : armed ? "#fff1a3" : "#4ab4c4";
    ctx.strokeRect(this.tile.x, this.tile.y, this.tile.w, this.tile.h);
    ctx.restore();

    ctx.fillStyle = "#caedf4";
    ctx.beginPath();
    ctx.arc(this.ball.x, this.ball.y, this.ball.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#4ab4c4";
    ctx.stroke();

    ctx.fillStyle = "#55c9d9";
    ctx.fillRect(this.paddle.x, this.paddle.y, this.paddle.w, this.paddle.h);
    ctx.fillStyle = "#a4f2fa";
    ctx.fillRect(this.paddle.x + 10, this.paddle.y + 4, this.paddle.w - 20, 3);

    ctx.fillStyle = armed ? "#f0ca4d" : cleared ? "#557b82" : "#7f9ca4";
    ctx.font = "12px Courier New";
    ctx.textAlign = "center";
    ctx.fillText(armed ? "RELAY: ARMED" : cleared ? "RELAY: CLEARED" : "RELAY: IDLE", WIDTH / 2, 75);
  };

  VectorRelay.prototype.snapshot = function () {
    var laneState = this.lane.snapshot();
    return {
      schemaVersion: "1.0",
      gameId: "vector-relay",
      status: this.status,
      score: this.score,
      lives: this.lives,
      isOver: this.status === "complete" || this.status === "failed",
      isActionable: this.status === "playing",
      challenge: { name: "Relay Circuit", seed: 73, level: 3 },
      relay: {
        nextDue: laneState.nextDue,
        phase: this.tile.phase,
        contacts: this.tile.contacts,
        commits: this.tile.commits,
        pending: laneState.pending,
        dropped: laneState.dropped,
        lastCommit: this.tile.lastCommit
      },
      orb: {
        attached: this.ball.attached,
        attachReason: this.ball.attachReason,
        x: Math.round(this.ball.x * 100) / 100,
        y: Math.round(this.ball.y * 100) / 100,
        vx: this.ball.vx,
        vy: this.ball.vy,
        route: this.ball.route,
        contactSlot: this.ball.body.slot,
        contactSeries: this.ball.body.series,
        overlapSlices: this.ball.overlapSlices
      },
      ownership: {
        port: this.ball.owner.port,
        active: this.ball.owner.key,
        attachments: this.attachmentCount
      },
      metrics: {
        launches: this.launchCount,
        losses: this.lossCount,
        bounces: this.bounceCount,
        elapsed: Math.round(this.clock * 1000) / 1000
      },
      terminal: {
        isTerminal: this.status === "complete" || this.status === "failed",
        outcome: this.status === "complete" ? "success" : this.status === "failed" ? "fail" : null,
        reason: this.status === "complete" ? "relay_cleared" : this.status === "failed" ? "no_lives_left" : null
      }
    };
  };

  global.VectorRelay = VectorRelay;
}(window));
