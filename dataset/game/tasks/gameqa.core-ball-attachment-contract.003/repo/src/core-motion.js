import {normalizeAngle} from './angles.js';

const CRUISE_SPEED = 36;
const SPRINT_SPEED = 144;
const SHIFT_TIME = 800;

export class CoreMotion {
  constructor() {
    this.reset();
  }

  reset() {
    this.angle = 0;
    this.speed = CRUISE_SPEED;
    this.transition = null;
  }

  step(deltaMs) {
    const seconds = deltaMs / 1000;
    if (!this.transition) {
      this.angle = normalizeAngle(this.angle + this.speed * seconds);
      return;
    }

    const startProgress = Math.min(1, this.transition.elapsed / SHIFT_TIME);
    const endElapsed = Math.min(SHIFT_TIME, this.transition.elapsed + deltaMs);
    const endProgress = endElapsed / SHIFT_TIME;
    const startSpeed = CRUISE_SPEED + (SPRINT_SPEED - CRUISE_SPEED) * startProgress;
    const endSpeed = CRUISE_SPEED + (SPRINT_SPEED - CRUISE_SPEED) * endProgress;
    this.angle = normalizeAngle(this.angle + ((startSpeed + endSpeed) / 2) * seconds);
    this.transition.elapsed += deltaMs;
    this.speed = endSpeed;
    if (this.transition.elapsed >= SHIFT_TIME) {
      this.speed = SPRINT_SPEED;
      this.transition = null;
    }
  }

  beginPaceChange() {
    if (this.speed === CRUISE_SPEED && !this.transition) {
      this.transition = {elapsed: 0};
    }
  }

  predictAngleAt(deltaMs) {
    return normalizeAngle(this.angle + this.speed * deltaMs / 1000);
  }

  get launchProfile() {
    if (this.transition) return 'shifting';
    return this.speed === SPRINT_SPEED ? 'sprint' : 'cruise';
  }

  get paceProgress() {
    if (this.transition) return this.transition.elapsed / SHIFT_TIME;
    return this.speed === SPRINT_SPEED ? 1 : 0;
  }

  get isTransitioning() {
    return Boolean(this.transition);
  }
}
