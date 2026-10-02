(function () {
  "use strict";

  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const SHAPE = Object.freeze({radiusX: 15, radiusY: 10});

  function boundsFor(x, y) {
    const width = SHAPE.radiusX * 2;
    const height = SHAPE.radiusY * 2;
    return Object.freeze({
      left: x - width / 2,
      right: x + width / 2,
      top: y - height / 2,
      bottom: y + height / 2,
      width,
      height,
    });
  }

  class Bird {
    constructor() {
      this.x = 154;
      this.reset();
    }

    reset() {
      this.y = 248;
      this.velocityY = 0;
      this.rotation = 0;
      this.chargeSeconds = 0;
      this.flapClock = 1;
      this.lastImpulse = 0;
      this.pose = this.snapshotPose();
    }

    snapshotPose() {
      return Object.freeze({
        x: this.x,
        y: this.y,
        velocity_y: this.velocityY,
        rotation: this.rotation,
        flap_clock: this.flapClock,
        last_impulse: this.lastImpulse,
        bounds: boundsFor(this.x, this.y),
      });
    }

    step(dt, control) {
      this.flapClock += dt;

      if (control.pressed) {
        this.chargeSeconds = 0;
      }
      if (control.down && !control.pressed) {
        this.chargeSeconds = Math.min(0.055, this.chargeSeconds + dt);
      }
      if (control.released) {
        const impulse = 120 + this.chargeSeconds * 15000;
        this.lastImpulse = Math.min(250, impulse);
        this.velocityY = -this.lastImpulse;
        this.flapClock = 0;
        this.chargeSeconds = 0;
      }

      this.velocityY = Math.min(340, this.velocityY + 620 * dt);
      this.y += this.velocityY * dt;
      this.rotation = clamp(this.velocityY * 0.17, -30, 82);
      this.pose = this.snapshotPose();
      return this.pose;
    }

    snapshot() {
      return this.pose;
    }
  }

  window.Bird = Bird;
  window.BirdShape = SHAPE;
})();
