export class PhaseClock {
  constructor(config) {
    this.initial = config.initial;
    this.next = config.next;
    this.duration = config.ticks;
    this.reset();
  }

  reset() {
    this.mode = this.initial;
    this.elapsed = 0;
  }

  step() {
    if (this.mode === this.next) return false;
    this.elapsed += 1;
    if (this.elapsed < this.duration) return false;
    this.mode = this.next;
    return true;
  }

  snapshot() {
    return {
      mode: this.mode,
      elapsed: this.elapsed,
      duration: this.duration,
    };
  }
}

