(function () {
  "use strict";

  const COLORS = Object.freeze({
    ink: "#102f3a",
    cream: "#fff4c7",
    cyan: "#35d9df",
    green: "#75d35c",
    red: "#ff625f",
    gold: "#ffd45a",
    ghost: "rgba(255,244,199,.38)",
    panel: "#173e4a",
    panel2: "#245665",
  });

  class Renderer {
    constructor(canvas) {
      this.canvas = canvas;
      this.context = canvas.getContext("2d");
    }

    draw(world) {
      if (world.phase === "lab") {
        this.drawLab(world);
      } else if (world.phase === "drill" || world.phase === "drill_result") {
        this.drawDrill(world);
      } else {
        this.drawRun(world);
      }
    }

    background() {
      const ctx = this.context;
      const gradient = ctx.createLinearGradient(0, 0, 0, this.canvas.height);
      gradient.addColorStop(0, "#66ccd5");
      gradient.addColorStop(0.72, "#bce9d5");
      gradient.addColorStop(0.73, "#d9c471");
      gradient.addColorStop(1, "#a9934a");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    panel(x, y, width, height, fill = COLORS.panel) {
      const ctx = this.context;
      ctx.fillStyle = fill;
      ctx.strokeStyle = COLORS.cream;
      ctx.lineWidth = 3;
      ctx.fillRect(x, y, width, height);
      ctx.strokeRect(x, y, width, height);
    }

    text(value, x, y, size, options = {}) {
      const ctx = this.context;
      ctx.fillStyle = options.color || COLORS.cream;
      ctx.font = `${options.bold === false ? "" : "bold "}${size}px monospace`;
      ctx.textAlign = options.align || "center";
      ctx.textBaseline = options.baseline || "alphabetic";
      ctx.fillText(value, x, y);
    }

    drawLab(world) {
      const ctx = this.context;
      ctx.fillStyle = COLORS.ink;
      ctx.fillRect(0, 0, 640, 480);
      this.text("FLIGHT LAB", 320, 58, 35);
      this.text("SELECT A FROZEN DRILL", 320, 88, 15, {color: "#a9edf0"});

      for (let index = 0; index < world.ui.drill_buttons.length; index += 1) {
        const button = world.ui.drill_buttons[index];
        const drill = world.ui.drills[index];
        this.panel(button.x, button.y, button.width, button.height, COLORS.panel2);
        this.text(String(index + 1), button.x + 25, button.y + 32, 18, {color: COLORS.gold});
        this.text(drill.name, button.x + button.width / 2, button.y + 62, 20);
        this.text(drill.note.toUpperCase(), button.x + button.width / 2, button.y + 88, 12, {
          color: "#a9edf0",
        });
        const previous = world.lab_results[drill.slug];
        this.text(
          previous ? `LAST: ${previous.toUpperCase()}` : "CLICK TO LAUNCH",
          button.x + button.width / 2,
          button.y + 119,
          13,
          {color: previous === "bump" ? COLORS.red : (previous ? COLORS.green : COLORS.cream)}
        );
      }

      this.panel(
        world.ui.run_button.x,
        world.ui.run_button.y,
        world.ui.run_button.width,
        world.ui.run_button.height,
        "#315f3d"
      );
      this.text("START NORMAL RUN", 320, 377, 18);
      this.text(
        `LAB LEDGER  ${Object.keys(world.lab_results).length}/3 VIEWED  ·  ${world.drill.score} CLEAR`,
        320,
        438,
        14,
        {color: "#a9edf0"}
      );
    }

    drawDrill(world) {
      const ctx = this.context;
      ctx.fillStyle = COLORS.ink;
      ctx.fillRect(0, 0, 640, 480);
      this.text("FLIGHT LAB · VISUAL AUDIT", 24, 31, 17, {align: "left", color: "#a9edf0"});
      this.text(world.drill.name || "", 24, 60, 27, {align: "left"});

      this.panel(24, 82, 406, 326, "#0d3440");
      this.text("ACTUAL TRACE + TARGET + GATE", 42, 109, 13, {
        align: "left",
        color: "#a9edf0",
      });

      const plot = {left: 48, right: 406, top: 126, bottom: 374};
      const spec = world.ui.drills[world.drill.index];
      const gateX = 326;
      const mapX = (sample) => Math.max(
        plot.left,
        Math.min(plot.right, gateX + sample.x - sample.pipe_x)
      );
      const mapY = (value) => plot.top + (value - 155) * (plot.bottom - plot.top) / 205;
      const gapTop = mapY(spec.layout.gapTop);
      const gapBottom = mapY(spec.layout.gapBottom);

      ctx.strokeStyle = "#234f5d";
      ctx.lineWidth = 1;
      for (let y = plot.top; y <= plot.bottom; y += 31) {
        ctx.beginPath();
        ctx.moveTo(plot.left, y);
        ctx.lineTo(plot.right, y);
        ctx.stroke();
      }

      ctx.fillStyle = "#3f7e42";
      ctx.strokeStyle = COLORS.green;
      ctx.lineWidth = 5;
      ctx.fillRect(gateX, plot.top, 56, Math.max(0, gapTop - plot.top));
      ctx.strokeRect(gateX, plot.top, 56, Math.max(0, gapTop - plot.top));
      ctx.fillRect(gateX, gapBottom, 56, Math.max(0, plot.bottom - gapBottom));
      ctx.strokeRect(gateX, gapBottom, 56, Math.max(0, plot.bottom - gapBottom));
      ctx.strokeStyle = COLORS.gold;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(gateX - 10, gapTop);
      ctx.lineTo(gateX + 66, gapTop);
      ctx.moveTo(gateX - 10, gapBottom);
      ctx.lineTo(gateX + 66, gapBottom);
      ctx.stroke();

      if (spec.target.length > 1) {
        ctx.strokeStyle = COLORS.ghost;
        ctx.lineWidth = spec.slug === "late" ? 18 : 14;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        spec.target.forEach((sample, index) => {
          const x = mapX({x: 154, pipe_x: sample.pipeX});
          const y = mapY(sample.y);
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.strokeStyle = "rgba(255,244,199,.72)";
        ctx.lineWidth = 2;
        ctx.setLineDash([7, 7]);
        ctx.stroke();
        ctx.setLineDash([]);
        this.text(
          spec.slug === "late" ? "TARGET CONTACT CORRIDOR" : "TARGET ARC",
          56,
          139,
          11,
          {align: "left", color: "rgba(255,244,199,.78)"}
        );
      }

      if (world.trail.length > 1) {
        ctx.strokeStyle = COLORS.cyan;
        ctx.lineWidth = 8;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        world.trail.forEach((sample, index) => {
          const x = mapX(sample);
          const y = mapY(sample.y);
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
        this.text("ACTUAL", 56, 158, 11, {align: "left", color: COLORS.cyan});
      }

      const audit = world.drill.audit;
      if (audit && audit.point) {
        const index = audit.sample_index;
        const x = mapX(world.trail[index]);
        const y = mapY(audit.point.y);
        this.drawAuditBird(x, y, audit.contact_visible);
        if (audit.contact_visible) {
          ctx.strokeStyle = COLORS.red;
          ctx.lineWidth = 6;
          ctx.beginPath();
          ctx.moveTo(x - 13, y - 13);
          ctx.lineTo(x + 13, y + 13);
          ctx.moveTo(x + 13, y - 13);
          ctx.lineTo(x - 13, y + 13);
          ctx.stroke();
          this.text("VISIBLE CONTACT", x, Math.max(plot.top + 18, y - 24), 12, {color: COLORS.red});
        } else {
          this.text("VISIBLE CLEARANCE", x, Math.max(plot.top + 18, y - 24), 12, {
            color: COLORS.green,
          });
        }
      } else {
        this.drawAuditBird(80, mapY(world.bird.y), false);
      }

      if (audit && audit.motion_segment) {
        const segment = audit.motion_segment;
        const startX = mapX(segment.start);
        const startY = mapY(segment.start.y);
        const endX = mapX(segment.end);
        const endY = mapY(segment.end.y);
        const marker = segment.interval.marker;
        const markerX = startX + (endX - startX) * marker;
        const markerY = startY + (endY - startY) * marker;
        ctx.strokeStyle = COLORS.red;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(startX, startY);
        ctx.lineTo(markerX, markerY);
        ctx.stroke();
        ctx.strokeStyle = COLORS.green;
        ctx.beginPath();
        ctx.moveTo(markerX, markerY);
        ctx.lineTo(endX, endY);
        ctx.stroke();
        this.drawAuditBird(startX, startY, true);
        this.drawAuditBird(endX, endY, false);
        this.text("CONTACT INTERVAL", markerX, Math.max(plot.top + 16, markerY - 23), 10, {
          color: COLORS.red,
        });
        this.text("ENDPOINT SAFE", endX, Math.min(plot.bottom - 5, endY + 28), 10, {
          color: COLORS.green,
        });
      }

      this.panel(440, 82, 176, 326, COLORS.panel);
      this.text("FROZEN RESULT", 528, 104, 12, {color: "#a9edf0"});
      const outcome = world.drill.outcome;
      this.text(
        outcome ? outcome.toUpperCase() : "RUNNING",
        528,
        137,
        outcome ? 25 : 18,
        {color: outcome === "bump" ? COLORS.red : (outcome ? COLORS.green : COLORS.gold)}
      );
      this.text("INPUT RECEIPT", 454, 164, 11, {align: "left", color: "#a9edf0"});
      ctx.strokeStyle = "#5d8992";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(456, 184);
      ctx.lineTo(600, 184);
      ctx.stroke();
      const receipt = world.drill_receipt || [];
      receipt.slice(0, 4).forEach((edge, index) => {
        const x = receipt.length <= 1
          ? 464
          : 464 + index * (128 / Math.max(1, receipt.length - 1));
        ctx.fillStyle = edge.kind === "press" ? COLORS.gold : COLORS.cyan;
        ctx.beginPath();
        ctx.arc(x, 184, 5, 0, Math.PI * 2);
        ctx.fill();
        this.text(edge.kind.toUpperCase(), x, 203, 9, {
          color: edge.kind === "press" ? COLORS.gold : COLORS.cyan,
        });
        this.text(`S${edge.step}`, x, 216, 9, {color: "#a9edf0"});
      });
      if (receipt.length === 0) this.text("WAITING", 528, 202, 11, {color: COLORS.gold});

      const specImpulse = spec.targetImpulse;
      this.text(`ACTUAL IMPULSE  ${Math.round(world.actual_impulse || 0)}`, 454, 241, 10, {
        align: "left",
        color: COLORS.cyan,
      });
      this.text(`TARGET IMPULSE  ${Math.round(specImpulse)}`, 454, 258, 10, {
        align: "left",
        color: COLORS.cream,
      });
      this.text("CONTACT INTERVAL", 454, 284, 10, {align: "left", color: "#a9edf0"});
      const interval = audit && audit.contact_interval;
      this.text(
        interval ? `${interval.start.toFixed(2)} → ${interval.end.toFixed(2)}` : "NONE",
        454,
        304,
        13,
        {align: "left", color: interval ? COLORS.red : COLORS.cream}
      );
      if (audit && audit.endpoint_safe) {
        this.text("ENDPOINT SAFE", 454, 322, 10, {align: "left", color: COLORS.green});
      }
      if (spec.slug === "late" && world.phase === "drill_result") {
        const retained = Boolean(world.lastCollision && world.lastCollision.kind === "pipe");
        this.text(
          `OBSERVED CONTACT  ${audit && audit.contact_visible ? "YES" : "NO"}`,
          454, 329, 9,
          {align: "left", color: audit && audit.contact_visible ? COLORS.red : COLORS.cream}
        );
        this.text(
          `RETAINED COLLISION  ${retained ? "YES" : "NO"}`,
          454, 343, 9,
          {align: "left", color: retained ? COLORS.green : COLORS.red}
        );
      }
      this.text("LEDGER", 454, 357, 9, {align: "left", color: "#a9edf0"});
      this.text(
        `${world.drill.score} CLEAR · ${Object.keys(world.lab_results).length}/3`,
        454,
        372,
        13,
        {
        align: "left",
      });

      if (world.phase === "drill_result") {
        this.panel(
          454,
          world.ui.back_button.y,
          world.ui.back_button.width,
          world.ui.back_button.height,
          "#315f3d"
        );
        this.text("BACK TO LAB", 532, 423, 17);
      } else {
        this.text("REPLAY IN FLIGHT", 532, 423, 14, {color: COLORS.gold});
      }
    }

    drawAuditBird(x, y, contact) {
      const ctx = this.context;
      ctx.save();
      ctx.translate(x, y);
      ctx.fillStyle = "#f8d33d";
      ctx.strokeStyle = contact ? COLORS.red : COLORS.cream;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.ellipse(0, 0, 15, 10, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    drawRun(world) {
      const ctx = this.context;
      this.background();
      for (const pipe of world.pipes) this.drawPipe(pipe);
      this.drawBird(world.bird);
      this.text(String(world.score), 320, 48, 34);
      if (world.phase === "dead") {
        ctx.fillStyle = "rgba(10,31,42,.68)";
        ctx.fillRect(0, 0, 640, 480);
        this.text("BUMP!", 320, 194, 38);
        this.text("tap or press to restart", 320, 232, 19, {bold: false});
      }
    }

    drawPipe(pipe) {
      const ctx = this.context;
      const x = pipe.x;
      const width = pipe.width;
      ctx.fillStyle = "#73be46";
      ctx.strokeStyle = "#31572a";
      ctx.lineWidth = 4;
      ctx.fillRect(x, 0, width, pipe.gap_top);
      ctx.strokeRect(x, -3, width, pipe.gap_top + 3);
      ctx.fillRect(x, pipe.gap_bottom, width, 400 - pipe.gap_bottom);
      ctx.strokeRect(x, pipe.gap_bottom, width, 403 - pipe.gap_bottom);
      ctx.fillStyle = "#8fda59";
      ctx.fillRect(x - 6, pipe.gap_top - 20, width + 12, 20);
      ctx.strokeRect(x - 6, pipe.gap_top - 20, width + 12, 20);
      ctx.fillRect(x - 6, pipe.gap_bottom, width + 12, 20);
      ctx.strokeRect(x - 6, pipe.gap_bottom, width + 12, 20);
    }

    drawBird(bird) {
      const ctx = this.context;
      const shape = window.BirdShape;
      ctx.save();
      ctx.translate(bird.x, bird.y);
      ctx.fillStyle = "#f8d33d";
      ctx.strokeStyle = "#3c3023";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.ellipse(0, 0, shape.radiusX, shape.radiusY, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(8, -4, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#222";
      ctx.beginPath();
      ctx.arc(10, -4, 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#f47c32";
      ctx.fillRect(13, -1, 9, 5);
      ctx.strokeRect(13, -1, 9, 5);
      ctx.restore();
    }
  }

  window.Renderer = Renderer;
})();
