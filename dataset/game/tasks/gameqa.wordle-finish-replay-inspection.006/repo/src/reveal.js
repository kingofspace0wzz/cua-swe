export class RevealTimeline {
  constructor(stepMs = 170) {
    this.stepMs = stepMs;
    this.pending = new Set();
    this.generation = 0;
  }

  begin(packet, onStep, onDone) {
    const generation = this.generation;
    packet.statuses.forEach((status, index) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(timer);
        if (generation !== this.generation) return;
        onStep({ ...packet, status, index });
        if (index === packet.statuses.length - 1) onDone(packet);
      }, index * this.stepMs);
      this.pending.add(timer);
    });
  }

  close() {
    this.generation += 1;
    for (const timer of this.pending) window.clearTimeout(timer);
    this.pending.clear();
  }
}
