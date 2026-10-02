(function () {
  "use strict";

  class FlightInput {
    constructor(target) {
      this.target = target;
      this.down = false;
      this.pressed = false;
      this.released = false;
      this.source = null;
      this.command = null;
      this.pointer = Object.freeze({x: 0, y: 0});
      this.receipt = [];
      this.pressedAt = null;

      this.onKeyDown = (event) => {
        if (event.code === "Digit1" || event.code === "Digit2" || event.code === "Digit3") {
          event.preventDefault();
          this.command = Number(event.code.slice(-1)) - 1;
          return;
        }
        if (event.code !== "Space" && event.code !== "ArrowUp") return;
        event.preventDefault();
        if (!event.repeat) this.press("keyboard");
      };
      this.onKeyUp = (event) => {
        if (event.code !== "Space" && event.code !== "ArrowUp") return;
        event.preventDefault();
        this.release("keyboard");
      };
      this.onPointerDown = (event) => {
        event.preventDefault();
        const rect = target.getBoundingClientRect();
        this.pointer = Object.freeze({
          x: (event.clientX - rect.left) * target.width / rect.width,
          y: (event.clientY - rect.top) * target.height / rect.height,
        });
        this.press("pointer");
      };
      this.onPointerUp = (event) => {
        event.preventDefault();
        this.release("pointer");
      };

      window.addEventListener("keydown", this.onKeyDown);
      window.addEventListener("keyup", this.onKeyUp);
      target.addEventListener("pointerdown", this.onPointerDown);
      window.addEventListener("pointerup", this.onPointerUp);
      target.addEventListener("contextmenu", (event) => event.preventDefault());
    }

    press(source) {
      if (this.down) return;
      this.down = true;
      this.pressed = true;
      this.source = source;
      this.pressedAt = performance.now();
      this.receipt.push(Object.freeze({
        kind: "press",
        source,
        at: this.pressedAt,
        held_ms: 0,
      }));
    }

    release(source) {
      if (!this.down || (this.source && this.source !== source)) return;
      const releasedAt = performance.now();
      this.down = false;
      this.released = true;
      this.source = null;
      this.receipt.push(Object.freeze({
        kind: "release",
        source,
        at: releasedAt,
        held_ms: this.pressedAt === null
          ? 0
          : Math.max(0, releasedAt - this.pressedAt),
      }));
      this.pressedAt = null;
    }

    sample() {
      const result = Object.freeze({
        down: this.down,
        pressed: this.pressed,
        released: this.released,
        receipt: Object.freeze(this.receipt.slice()),
        command: this.command,
        pointer: this.pointer,
      });
      this.pressed = false;
      this.released = false;
      this.receipt = [];
      this.command = null;
      return result;
    }

    clear() {
      this.down = false;
      this.pressed = false;
      this.released = false;
      this.source = null;
      this.command = null;
      this.receipt = [];
      this.pressedAt = null;
    }
  }

  window.FlightInput = FlightInput;
})();
