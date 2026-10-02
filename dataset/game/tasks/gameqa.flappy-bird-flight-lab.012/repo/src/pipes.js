(function () {
  "use strict";

  const PIPE_WIDTH = 58;
  const PIPE_SPEED = 104;
  const LAB_SPEED = 300;
  const PIPE_SPACING = 245;
  const GAP_SEQUENCE = [
    [145, 285],
    [128, 268],
    [166, 306],
    [140, 280],
  ];

  class PipeField {
    constructor() {
      this.reset();
    }

    reset(mode) {
      this.mode = mode && mode.kind === "drill" ? "drill" : "run";
      if (this.mode === "drill") {
        const layout = mode.layout;
        this.pipes = [{
          id: mode.id,
          x: layout.x,
          gapTop: layout.gapTop,
          gapBottom: layout.gapBottom,
          scored: false,
        }];
        this.nextId = 2;
        return;
      }
      this.pipes = GAP_SEQUENCE.map((gap, index) => ({
        id: index + 1,
        x: 432 + index * PIPE_SPACING,
        gapTop: gap[0],
        gapBottom: gap[1],
        scored: false,
      }));
      this.nextId = this.pipes.length + 1;
    }

    step(dt, birdFrame) {
      let scored = 0;
      const scoreEvents = [];
      let collision = null;
      const speed = this.mode === "drill" ? LAB_SPEED : PIPE_SPEED;

      for (const pipe of this.pipes) {
        pipe.x -= speed * dt;
        const left = pipe.x;
        const right = left + PIPE_WIDTH;
        const bird = birdFrame.bounds;
        const overlaps = bird.right > left && bird.left < right;

        if (
          overlaps
          && (bird.top < pipe.gapTop || bird.bottom > pipe.gapBottom)
        ) {
          collision = Object.freeze({
            kind: "pipe",
            pipe_id: pipe.id,
            pipe_left: left,
            pipe_right: right,
            gap_top: pipe.gapTop,
            gap_bottom: pipe.gapBottom,
            bird,
          });
          break;
        }

        if (!pipe.scored && right < bird.left) {
          pipe.scored = true;
          scored += 1;
          scoreEvents.push(Object.freeze({
            pipe_id: pipe.id,
            pipe_right: right,
            bird_left: bird.left,
          }));
        }
      }

      if (this.mode === "drill") {
        return Object.freeze({
          scored,
          score_events: Object.freeze(scoreEvents),
          collision,
          pipes: this.snapshot(),
        });
      }

      while (this.pipes.length && this.pipes[0].x + PIPE_WIDTH < -20) {
        this.pipes.shift();
      }
      while (this.pipes.length < 4) {
        const tail = this.pipes[this.pipes.length - 1];
        const gap = GAP_SEQUENCE[(this.nextId - 1) % GAP_SEQUENCE.length];
        const x = tail ? tail.x + PIPE_SPACING : 700;
        this.pipes.push({
          id: this.nextId,
          x,
          gapTop: gap[0],
          gapBottom: gap[1],
          scored: false,
        });
        this.nextId += 1;
      }

      return Object.freeze({
        scored,
        score_events: Object.freeze(scoreEvents),
        collision,
        pipes: this.snapshot(),
      });
    }

    snapshot() {
      return this.pipes.map((pipe) => Object.freeze({
        id: pipe.id,
        x: pipe.x,
        width: PIPE_WIDTH,
        gap_top: pipe.gapTop,
        gap_bottom: pipe.gapBottom,
        scored: pipe.scored,
      }));
    }
  }

  window.PipeField = PipeField;
})();
