const RESULT_LEAD_MS = 560;
const RESULT_STAGGER_MS = 95;
const RESULT_DURATION_MS = 760;
const RESULT_FALLBACK_GRACE_MS = 900;
const REPLAY_DURATION_MS = 1800;
const REPLAY_PAUSE_FRACTION = 0.34;

export class ResultMotion {
  constructor(resultElement) {
    this.resultElement = resultElement;
    this.replayButton = resultElement.querySelector("#replay-finish");
    this.continueButton = resultElement.querySelector("#continue-finish");
    this.playbackStatus = resultElement.querySelector("#finish-playback-status");
    this.pending = new Set();
    this.frames = new Set();
    this.active = new Map();
    this.replayActive = new Map();
    this.startedCount = 0;
    this.finishedCount = 0;
    this.animationEndCount = 0;
    this.fallbackCount = 0;
    this.sequence = 0;
    this.operation = "idle";
    this.completedRow = null;
    this.replayCount = 0;
    this.completedReplayCount = 0;
    this.resetReplayRun();
    this.replayButton.addEventListener("click", () => this.replay());
    this.continueButton.addEventListener("click", () => this.continueReplay());
    this.syncControls();
  }

  resetReplayRun() {
    this.replayPhase = "idle";
    this.replayStartedCount = 0;
    this.replayPausedCount = 0;
    this.replayContinueCount = 0;
    this.replayFinishedCount = 0;
    this.replayAnimationEndCount = 0;
    this.replayFallbackCount = 0;
    this.replayMissingAnimationCount = 0;
  }

  reset(boardElement) {
    this.sequence += 1;
    for (const timer of this.pending) window.clearTimeout(timer);
    this.pending.clear();
    for (const frame of this.frames) window.cancelAnimationFrame(frame);
    this.frames.clear();
    for (const entry of [...this.active.values(), ...this.replayActive.values()]) {
      entry.animation?.cancel();
    }
    this.active.clear();
    this.replayActive.clear();
    this.startedCount = 0;
    this.finishedCount = 0;
    this.animationEndCount = 0;
    this.fallbackCount = 0;
    this.operation = "idle";
    this.completedRow = null;
    this.replayCount = 0;
    this.completedReplayCount = 0;
    this.resetReplayRun();
    boardElement
      .querySelectorAll(".is-celebrating")
      .forEach((element) => {
        element.classList.remove("is-celebrating");
        element.style.removeProperty("animation-duration");
      });
    this.resultElement.hidden = true;
    this.syncControls();
  }

  celebrate(rowElement) {
    if (this.startedCount || this.pending.size || this.active.size) return;
    this.operation = "initial";
    this.completedRow = rowElement;
    this.queue(rowElement);
  }

  replay() {
    if (
      !this.completedRow ||
      this.finishedCount !== 5 ||
      this.pending.size ||
      this.replayActive.size ||
      ["starting", "paused", "playing"].includes(this.replayPhase)
    ) {
      return;
    }
    this.operation = "replay";
    this.replayCount += 1;
    this.resetReplayRun();
    this.replayPhase = "starting";
    this.syncControls();
    this.queue(this.completedRow);
  }

  queue(rowElement) {
    const sequence = this.sequence;
    const slots = [...rowElement.querySelectorAll(".tile-slot")];
    slots.forEach((slot, column) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(timer);
        if (sequence !== this.sequence) return;
        const target = slot.querySelector(".tile-motion");
        this.startTarget(target, `${rowElement.dataset.row}:${column}`, sequence);
      }, RESULT_LEAD_MS + column * RESULT_STAGGER_MS);
      this.pending.add(timer);
    });
  }

  startTarget(target, id, sequence) {
    const replay = this.operation === "replay";
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    target.classList.remove("is-celebrating");
    target.style.removeProperty("animation-duration");
    void target.offsetWidth;
    if (replay && !reducedMotion) {
      target.style.animationDuration = `${REPLAY_DURATION_MS}ms`;
    }
    target.classList.add("is-celebrating");
    const collection = replay ? this.replayActive : this.active;
    const entry = {
      id,
      startedAt: performance.now(),
      target: target.className,
      animation: null,
      scheduleFallback: null
    };
    collection.set(id, entry);
    if (replay) this.replayStartedCount += 1;
    else this.startedCount += 1;

    let finished = false;
    let fallback = null;
    const clearFallback = () => {
      if (fallback === null) return;
      window.clearTimeout(fallback);
      this.pending.delete(fallback);
      fallback = null;
    };
    const finish = (source) => {
      if (finished || sequence !== this.sequence) return;
      finished = true;
      clearFallback();
      target.classList.remove("is-celebrating");
      target.style.removeProperty("animation-duration");
      collection.delete(id);
      if (replay) {
        this.replayFinishedCount += 1;
        if (source === "animationend") this.replayAnimationEndCount += 1;
        else this.replayFallbackCount += 1;
        if (this.replayFinishedCount === 5) {
          this.completedReplayCount += 1;
          this.replayPhase = "complete";
          this.operation = "idle";
          this.resultElement.hidden = false;
          this.syncControls();
        }
      } else {
        this.finishedCount += 1;
        if (source === "animationend") this.animationEndCount += 1;
        else this.fallbackCount += 1;
        if (this.finishedCount === 5) {
          this.operation = "idle";
          this.resultElement.hidden = false;
          this.syncControls();
        }
      }
    };
    const onAnimationEnd = (event) => {
      if (event.target !== target || !event.animationName.includes("result-hop")) return;
      target.removeEventListener("animationend", onAnimationEnd);
      finish("animationend");
    };
    target.addEventListener("animationend", onAnimationEnd);
    const scheduleFallback = (delay) => {
      clearFallback();
      fallback = window.setTimeout(() => {
        this.pending.delete(fallback);
        fallback = null;
        target.removeEventListener("animationend", onAnimationEnd);
        finish("fallback");
      }, delay);
      this.pending.add(fallback);
    };
    entry.scheduleFallback = scheduleFallback;

    if (!replay) {
      scheduleFallback(RESULT_DURATION_MS + RESULT_FALLBACK_GRACE_MS);
      return;
    }
    if (reducedMotion) {
      this.replayPhase = "playing";
      this.syncControls();
      scheduleFallback(RESULT_FALLBACK_GRACE_MS);
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      this.frames.delete(frame);
      if (sequence !== this.sequence || finished) return;
      const animation = target
        .getAnimations()
        .find((candidate) =>
          String(candidate.animationName || "").includes("result-hop")
        );
      if (!animation) {
        this.replayMissingAnimationCount += 1;
        scheduleFallback(REPLAY_DURATION_MS + RESULT_FALLBACK_GRACE_MS);
        return;
      }
      const timing = animation.effect?.getComputedTiming();
      const duration = Number(timing?.duration) || REPLAY_DURATION_MS;
      animation.currentTime = duration * REPLAY_PAUSE_FRACTION;
      animation.pause();
      entry.animation = animation;
      this.replayPausedCount += 1;
      if (
        this.replayPausedCount === 5 &&
        this.replayActive.size === 5 &&
        this.replayMissingAnimationCount === 0
      ) {
        this.replayPhase = "paused";
        this.syncControls();
      }
    });
    this.frames.add(frame);
  }

  continueReplay() {
    if (this.replayPhase !== "paused" || this.replayActive.size !== 5) return;
    this.replayPhase = "playing";
    this.replayContinueCount += 1;
    this.syncControls();
    for (const entry of this.replayActive.values()) {
      const animation = entry.animation;
      if (!animation) continue;
      const timing = animation.effect?.getComputedTiming();
      const duration = Number(timing?.duration) || REPLAY_DURATION_MS;
      const elapsed = Number(animation.currentTime) || 0;
      entry.scheduleFallback(
        Math.max(1, duration - elapsed) + RESULT_FALLBACK_GRACE_MS
      );
      animation.play();
    }
  }

  syncControls() {
    const available = Boolean(
      this.completedRow && this.finishedCount === 5
    );
    const busy = ["starting", "paused", "playing"].includes(this.replayPhase);
    this.replayButton.disabled = !available || busy;
    this.continueButton.hidden = this.replayPhase !== "paused";
    this.continueButton.disabled = this.replayPhase !== "paused";
    const messages = {
      idle: available ? "Ready to replay." : "Finish playback unlocks after a win.",
      starting: "Preparing a replay frame…",
      paused: "Paused mid-finish for inspection.",
      playing: "Continuing the finish…",
      complete: "Replay complete. Ready again."
    };
    this.playbackStatus.textContent = messages[this.replayPhase];
  }

  snapshot() {
    return {
      startedCount: this.startedCount,
      finishedCount: this.finishedCount,
      animationEndCount: this.animationEndCount,
      fallbackCount: this.fallbackCount,
      activeTiles: [...this.active.values()].map((entry) => ({
        id: entry.id,
        startedAt: entry.startedAt,
        target: entry.target
      })),
      complete: this.finishedCount === 5,
      replay: {
        available: Boolean(this.completedRow && this.finishedCount === 5),
        phase: this.replayPhase,
        count: this.replayCount,
        completedCount: this.completedReplayCount,
        startedCount: this.replayStartedCount,
        pausedCount: this.replayPausedCount,
        continueCount: this.replayContinueCount,
        finishedCount: this.replayFinishedCount,
        animationEndCount: this.replayAnimationEndCount,
        fallbackCount: this.replayFallbackCount,
        missingAnimationCount: this.replayMissingAnimationCount,
        activeTiles: [...this.replayActive.values()].map((entry) => ({
          id: entry.id,
          startedAt: entry.startedAt,
          target: entry.target,
          paused: entry.animation?.playState === "paused"
        })),
        replayControlVisible:
          !this.resultElement.hidden && !this.replayButton.hidden,
        replayControlEnabled: !this.replayButton.disabled,
        continueControlVisible:
          !this.resultElement.hidden && !this.continueButton.hidden,
        status: this.playbackStatus.textContent
      }
    };
  }
}
