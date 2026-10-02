import {CoreMotion} from './core-motion.js';
import {Occupancy} from './occupancy.js';
import {ShotController} from './shot-controller.js';

const STEP_MS = 20;
const CENTER = {x: 380, y: 285};
const CORE_RADIUS = 58;
const PIN_ORBIT = 132;
const SHOTS_TO_CLEAR = 4;

export class Game {
  constructor(canvas, ui) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d');
    this.ui = ui;
    this.motion = new CoreMotion();
    this.occupancy = new Occupancy();
    this.shots = new ShotController(this.motion);
    this.manual = false;
    this.seed = 808;
    this.level = 1;
    this.lastFrame = performance.now();
    this.accumulator = 0;
    this.reset();
    requestAnimationFrame((time) => this.frame(time));
  }

  reset(options = {}) {
    this.manual = Boolean(options.manual);
    this.seed = Number.isFinite(options.seed) ? options.seed : this.seed;
    this.level = Number.isFinite(options.level) ? options.level : 1;
    this.now = 0;
    this.phase = 'ready';
    this.remaining = SHOTS_TO_CLEAR;
    this.motion.reset();
    this.occupancy.reset();
    this.shots.reset();
    this.metrics = {inputs: 0, attachments: 0, failures: 0, completed: 0};
    this.lastAttachment = null;
    this.ui.showReady();
    this.publish();
    this.render();
    return this.getState();
  }

  start() {
    if (this.phase !== 'ready') return false;
    this.phase = 'playing';
    this.ui.hideOverlay();
    this.publish();
    return true;
  }

  fire() {
    if (this.phase !== 'playing' || this.remaining <= 0) return 'ignored';
    this.metrics.inputs += 1;
    const result = this.shots.request(this.now);
    this.ui.setStatus(result === 'queued' ? 'Next pin waiting' : result === 'launched' ? 'Pin launched' : 'Launcher full');
    this.publish();
    return result;
  }

  step(deltaMs = STEP_MS) {
    if (this.phase !== 'playing') return;
    this.now += deltaMs;
    this.motion.step(deltaMs);
    const arrivals = this.shots.step(this.now);
    for (const arrival of arrivals) {
      const result = this.occupancy.tryAttach(arrival.localAngle);
      this.lastAttachment = {
        accepted: result.accepted,
        localAngle: result.angle,
        worldAngle: arrival.worldAngle,
        coreAngle: this.motion.angle,
        at: this.now,
      };
      if (!result.accepted) {
        this.metrics.failures += 1;
        this.phase = 'failed';
        this.ui.showFailure();
        break;
      }

      this.metrics.attachments += 1;
      this.remaining -= 1;
      if (this.metrics.attachments === 1) this.motion.beginPaceChange();
      if (this.remaining === 0) {
        this.metrics.completed += 1;
        this.phase = 'passed';
        this.ui.showPass();
      }
    }
    this.publish();
  }

  advance(durationMs) {
    this.manual = true;
    const bounded = Math.max(0, Math.min(30000, Number(durationMs) || 0));
    const steps = Math.floor(bounded / STEP_MS);
    for (let index = 0; index < steps; index += 1) this.step(STEP_MS);
    this.render();
    return this.getState();
  }

  frame(timestamp) {
    const elapsed = Math.min(100, timestamp - this.lastFrame);
    this.lastFrame = timestamp;
    if (!this.manual) {
      this.accumulator += elapsed;
      while (this.accumulator >= STEP_MS) {
        this.step(STEP_MS);
        this.accumulator -= STEP_MS;
      }
    }
    this.render();
    requestAnimationFrame((time) => this.frame(time));
  }

  pinPoint(localAngle, radius = PIN_ORBIT) {
    const radians = (localAngle + this.motion.angle) * Math.PI / 180;
    return {
      x: CENTER.x + Math.cos(radians) * radius,
      y: CENTER.y + Math.sin(radians) * radius,
    };
  }

  render() {
    const context = this.context;
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    const wash = context.createRadialGradient(CENTER.x, CENTER.y, 10, CENTER.x, CENTER.y, 320);
    wash.addColorStop(0, 'rgba(61, 194, 237, .14)');
    wash.addColorStop(1, 'rgba(3, 9, 16, 0)');
    context.fillStyle = wash;
    context.fillRect(0, 0, this.canvas.width, this.canvas.height);

    context.strokeStyle = 'rgba(116, 203, 234, .13)';
    context.lineWidth = 1;
    for (let radius = 92; radius <= 260; radius += 56) {
      context.beginPath();
      context.arc(CENTER.x, CENTER.y, radius, 0, Math.PI * 2);
      context.stroke();
    }

    for (const localAngle of this.occupancy.pins) {
      const pin = this.pinPoint(localAngle);
      context.strokeStyle = '#9ddff5';
      context.lineWidth = 3;
      context.beginPath();
      context.moveTo(CENTER.x, CENTER.y);
      context.lineTo(pin.x, pin.y);
      context.stroke();
      context.fillStyle = '#effbff';
      context.beginPath();
      context.arc(pin.x, pin.y, 13, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = '#0a1b28';
      context.beginPath();
      context.arc(pin.x, pin.y, 4, 0, Math.PI * 2);
      context.fill();
    }

    context.save();
    context.translate(CENTER.x, CENTER.y);
    context.rotate(this.motion.angle * Math.PI / 180);
    context.strokeStyle = '#67dcff';
    context.lineWidth = 5;
    context.beginPath();
    context.arc(0, 0, CORE_RADIUS, 0, Math.PI * 1.62);
    context.stroke();
    context.restore();
    context.fillStyle = '#102d40';
    context.beginPath();
    context.arc(CENTER.x, CENTER.y, CORE_RADIUS - 8, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = '#eafaff';
    context.font = '800 24px system-ui';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(String(this.remaining), CENTER.x, CENTER.y);

    const shot = this.shots.active;
    if (shot) {
      const startY = 635;
      const endY = CENTER.y + PIN_ORBIT;
      const eased = 1 - Math.pow(1 - shot.progress, 2);
      const y = startY + (endY - startY) * eased;
      context.strokeStyle = 'rgba(103, 220, 255, .38)';
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(CENTER.x, y + 18);
      context.lineTo(CENTER.x, 655);
      context.stroke();
      context.fillStyle = '#fff3b0';
      context.beginPath();
      context.arc(CENTER.x, y, 13, 0, Math.PI * 2);
      context.fill();
    }
    if (this.shots.waiting) {
      context.strokeStyle = 'rgba(255, 218, 107, .72)';
      context.lineWidth = 2;
      context.beginPath();
      context.arc(CENTER.x, 657, 16, 0, Math.PI * 2);
      context.stroke();
      context.fillStyle = '#ffda6b';
      context.beginPath();
      context.arc(CENTER.x, 657, 9, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = '#ffecad';
      context.font = '800 11px system-ui';
      context.fillText('NEXT', CENTER.x, 625);
    }
  }

  publish() {
    this.ui.update(this.getState());
  }

  getState() {
    return {
      scenario: {seed: this.seed, level: this.level, timeMs: this.now, manual: this.manual},
      round: {phase: this.phase, remaining: this.remaining},
      motion: {
        angle: this.motion.angle,
        speed: this.motion.speed,
        transition: {active: this.motion.isTransitioning, progress: this.motion.paceProgress},
      },
      shots: this.shots.getState(),
      occupancy: {pins: [...this.occupancy.pins]},
      lastAttachment: this.lastAttachment ? {...this.lastAttachment} : null,
      metrics: {...this.metrics},
    };
  }
}
