import {normalizeAngle} from './angles.js';

const OPENING_FLIGHT_TIME = 20000;
const CRUISE_QUEUE_FLIGHT_TIME = 770;
const SHIFT_QUEUE_FLIGHT_TIME = 710;
const SPRINT_FLIGHT_TIME = 600;
const IMPACT_ANGLE = 90;

export class ShotController {
  constructor(coreMotion) {
    this.coreMotion = coreMotion;
    this.reset();
  }

  reset() {
    this.active = null;
    this.waiting = null;
  }

  request(now) {
    const prepared = this.prepare(now, Boolean(this.active));
    if (!this.active) {
      this.active = this.activate(prepared, now);
      return 'launched';
    }
    if (!this.waiting) {
      this.waiting = prepared;
      return 'queued';
    }
    return 'full';
  }

  prepare(now, fromQueue) {
    const plannedFlightTime = fromQueue
      ? CRUISE_QUEUE_FLIGHT_TIME
      : this.flightTimeFor({fromQueue}, this.coreMotion.launchProfile);
    return {
      acceptedAt: now,
      fromQueue,
      plannedCoreAngle: this.coreMotion.predictAngleAt(plannedFlightTime),
    };
  }

  activate(prepared, now) {
    const launchProfile = this.coreMotion.launchProfile;
    const flightTime = this.flightTimeFor(prepared, launchProfile);
    return {
      ...prepared,
      flightTime,
      launchProfile,
      launchedAt: now,
      progress: 0,
    };
  }

  flightTimeFor(prepared, launchProfile) {
    if (prepared.fromQueue) {
      return launchProfile === 'shifting' ? SHIFT_QUEUE_FLIGHT_TIME : CRUISE_QUEUE_FLIGHT_TIME;
    }
    return launchProfile === 'sprint' ? SPRINT_FLIGHT_TIME : OPENING_FLIGHT_TIME;
  }

  step(now) {
    if (!this.active) return [];
    this.active.progress = Math.min(1, (now - this.active.launchedAt) / this.active.flightTime);
    if (this.active.progress < 1) return [];

    const arrival = {
      worldAngle: IMPACT_ANGLE,
      localAngle: normalizeAngle(IMPACT_ANGLE - this.active.plannedCoreAngle),
      acceptedAt: this.active.acceptedAt,
      launchedAt: this.active.launchedAt,
    };
    this.active = null;
    if (this.waiting) {
      this.active = this.activate(this.waiting, now);
      this.waiting = null;
    }
    return [arrival];
  }

  getState() {
    return {
      active: this.active ? {
        progress: this.active.progress,
        acceptedAt: this.active.acceptedAt,
        launchedAt: this.active.launchedAt,
        flightTime: this.active.flightTime,
        launchProfile: this.active.launchProfile,
      } : null,
      waiting: this.waiting ? 1 : 0,
    };
  }
}
