import {circularDistance, normalizeAngle} from './angles.js';

const CLEARANCE = 24;

export class Occupancy {
  constructor() {
    this.reset();
  }

  reset() {
    this.pins = [180, 300, 359];
  }

  tryAttach(localAngle) {
    const angle = normalizeAngle(localAngle);
    const blocked = this.pins.some((pin) => circularDistance(pin, angle) < CLEARANCE);
    this.pins.push(angle);
    return {accepted: !blocked, angle};
  }
}
