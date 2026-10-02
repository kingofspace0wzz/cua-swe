import {PhaseClock} from './phase_clock.js';
import {Rover} from './rover.js';

const pointKey = (point) => `${point.x},${point.y}`;
const samePoint = (left, right) => left.x === right.x && left.y === right.y;
const clonePoint = (point) => ({x: point.x, y: point.y});

export class SignalMaze {
  constructor(root, config) {
    this.root = root;
    this.config = config;
    this.routeElement = document.querySelector('#route');
    this.warningElement = document.querySelector('#warning');
    this.livesElement = document.querySelector('#lives');
    this.messageElement = document.querySelector('#message');
    this.walkable = new Set(config.walkable.map(([x, y]) => `${x},${y}`));
    this.held = new Set();
    this.phase = new PhaseClock(config.phase);
    this.rover = new Rover(config.rover);
    this.cells = new Map();
    this.renderBoard();
    this.bindInput();
    this.reset();
    this.timer = window.setInterval(() => this.tick(), config.tickMs);
  }

  bindInput() {
    window.addEventListener('keydown', (event) => {
      if (event.key.startsWith('Arrow')) {
        event.preventDefault();
        this.held.add(event.key);
      }
    });
    window.addEventListener('keyup', (event) => {
      if (event.key.startsWith('Arrow')) {
        event.preventDefault();
        this.held.delete(event.key);
      }
    });
    window.addEventListener('blur', () => this.held.clear());
  }

  reset() {
    this.held.clear();
    this.tickCount = 0;
    this.player = {
      position: clonePoint(this.config.playerStart),
      lives: 3,
      active: true,
    };
    this.phase.reset();
    this.rover.reset();
    this.alert = {active: false, remaining: 0};
    this.releaseRemaining = null;
    this.pulseCollected = false;
    this.contacts = 0;
    this.outcome = null;
    this.message = 'Follow the corridor to the exit.';
    this.render();
    return this.getState();
  }

  tick() {
    if (!this.player.active || this.outcome) {
      this.render();
      return;
    }
    this.tickCount += 1;

    if (this.phase.step()) this.rover.onGlobalMode(this.phase.mode);

    if (this.alert.active) {
      this.alert.remaining -= 1;
      this.releaseRemaining -= 1;
      if (this.releaseRemaining === 0) {
        this.rover.release(this.phase.mode, true);
      }
      if (this.alert.remaining === 0) this.finishAlert();
    }

    this.rover.step(this.phase.mode, this.alert.active);
    this.movePlayer();
    this.collectPulse();
    this.resolveContact();
    this.resolveExit();
    this.render();
  }

  startAlert() {
    this.alert.active = true;
    this.alert.remaining = this.config.alertTicks;
    this.releaseRemaining = this.config.releaseTicks;
    this.rover.enterAlert(this.phase.mode);
    this.message = 'TEAL WARNING — rover contact is safe.';
  }

  finishAlert() {
    this.alert.active = false;
    this.alert.remaining = 0;
    this.rover.exitAlert(this.phase.mode);
    this.message = 'Warning cleared — active contact restored.';
  }

  movePlayer() {
    const vectors = {
      ArrowUp: {x: 0, y: -1},
      ArrowRight: {x: 1, y: 0},
      ArrowDown: {x: 0, y: 1},
      ArrowLeft: {x: -1, y: 0},
    };
    const key = ['ArrowUp', 'ArrowRight', 'ArrowDown', 'ArrowLeft']
        .find((candidate) => this.held.has(candidate));
    if (!key) return;
    const vector = vectors[key];
    const next = {
      x: this.player.position.x + vector.x,
      y: this.player.position.y + vector.y,
    };
    if (this.walkable.has(pointKey(next))) this.player.position = next;
  }

  collectPulse() {
    if (this.pulseCollected || !samePoint(this.player.position, this.config.pulse)) {
      return;
    }
    this.pulseCollected = true;
    this.startAlert();
  }

  resolveContact() {
    if (!samePoint(this.player.position, this.rover.position)) return;
    if (!this.rover.hazard) {
      this.message = 'Safe pass confirmed while teal warning is active.';
      return;
    }
    this.contacts += 1;
    this.player.lives -= 1;
    this.player.active = false;
    this.outcome = 'collision';
    this.message = 'Signal clash — route handoff failed.';
  }

  resolveExit() {
    if (!samePoint(this.player.position, this.config.exit)) return;
    this.player.active = false;
    this.outcome = 'success';
    this.message = 'Exit reached. Route handoff stable.';
  }

  renderBoard() {
    this.root.style.setProperty('--columns', this.config.width);
    for (let y = 0; y < this.config.height; y += 1) {
      for (let x = 0; x < this.config.width; x += 1) {
        const cell = document.createElement('div');
        const walkable = this.walkable.has(`${x},${y}`);
        cell.className = `cell ${walkable ? 'walkable' : 'wall'}`;
        if (samePoint({x, y}, this.config.rover.dock)) cell.classList.add('dock');
        this.root.append(cell);
        this.cells.set(`${x},${y}`, cell);
      }
    }
  }

  addPiece(point, className) {
    const element = document.createElement('div');
    element.className = `piece ${className}`;
    this.cells.get(pointKey(point)).append(element);
  }

  render() {
    this.root.querySelectorAll('.piece').forEach((piece) => piece.remove());
    this.addPiece(this.config.exit, 'exit');
    if (!this.pulseCollected) this.addPiece(this.config.pulse, 'pulse');
    this.addPiece(this.player.position, 'player');
    const roverClass = this.rover.appearance === 'warning' ?
        'rover warning' : 'rover';
    this.addPiece(this.rover.position, roverClass);
    this.routeElement.textContent = this.phase.mode.toUpperCase();
    this.warningElement.textContent = this.alert.active ?
        `${this.alert.remaining} TICKS` : 'CLEAR';
    this.livesElement.textContent = String(this.player.lives);
    this.messageElement.textContent = this.message;
    this.messageElement.className = this.outcome === 'collision' ?
        'message hit' : this.outcome === 'success' ?
          'message success' : 'message';
  }

  getState() {
    return JSON.parse(JSON.stringify({
      tick: this.tickCount,
      player: {
        position: clonePoint(this.player.position),
        lives: this.player.lives,
        active: this.player.active,
      },
      phase: this.phase.snapshot(),
      alert: {...this.alert},
      rover: this.rover.snapshot(),
      metrics: {
        pulseCollected: this.pulseCollected,
        contacts: this.contacts,
        releaseRemaining: this.releaseRemaining,
      },
      terminal: {
        isTerminal: this.outcome !== null,
        outcome: this.outcome,
      },
      scenarioSeal: this.config.seals.scenario,
    }));
  }
}

