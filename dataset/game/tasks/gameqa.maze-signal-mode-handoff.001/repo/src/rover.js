const clonePoint = (point) => ({x: point.x, y: point.y});

export class Rover {
  constructor(config) {
    this.config = config;
    this.reset();
  }

  reset() {
    this.state = 'dock';
    this.position = clonePoint(this.config.dock);
    this.mode = 'dock';
    this.appearance = 'active';
    this.hazard = true;
    this.branch = null;
    this.alertActive = false;
    this.pendingAppearance = null;
    this.appearanceLag = 0;
  }

  enterAlert(globalMode) {
    this.alertActive = true;
    this.hazard = false;
    this.appearance = 'warning';
    if (this.state !== 'dock') this.mode = 'warning';
    this.entryMode = globalMode;
  }

  release(globalMode, alertActive) {
    this.state = 'junction';
    this.position = clonePoint(this.config.junction);
    this.mode = globalMode;
    if (alertActive) {
      this.alertActive = true;
      this.appearance = 'warning';
      this.hazard = false;
    }
  }

  onGlobalMode(globalMode) {
    if (!this.alertActive && this.state !== 'dock' && !this.branch) {
      this.mode = globalMode;
    }
  }

  exitAlert(globalMode) {
    this.alertActive = false;
    this.mode = globalMode;
    this.hazard = true;
    this.pendingAppearance = globalMode;
    this.appearanceLag = 2;
  }

  step(globalMode, alertActive) {
    if (this.state === 'junction' && !alertActive && !this.branch) {
      const target = this.mode === 'corner' ?
          this.config.cornerStep : this.config.trackStep;
      this.position = clonePoint(target);
      this.branch = this.mode === 'corner' ? 'left' : 'right';
      this.state = 'branch';
    }

    if (!this.alertActive && !this.branch) this.mode = globalMode;

    if (this.appearanceLag > 0) {
      this.appearanceLag -= 1;
      if (this.appearanceLag === 0) {
        this.appearance = this.pendingAppearance;
        this.pendingAppearance = null;
      }
    }
  }

  snapshot() {
    return {
      state: this.state,
      position: clonePoint(this.position),
      mode: this.mode,
      appearance: this.appearance,
      hazard: this.hazard,
      branch: this.branch,
      alertActive: this.alertActive,
    };
  }
}

