import {
  createField,
  fieldComplete,
  fieldOpenSlot,
  restoreField,
  runField,
  snapshotField,
  stageField,
  stepField,
} from "./field.js";
import {
  createPanel,
  panelComplete,
  panelOpenSlot,
  restorePanel,
  runPanel,
  snapshotPanel,
  stagePanel,
  stepPanel,
} from "./panel.js";

const START = {x: 72, y: 385};
const CHECKPOINT = {x: 438, y: 300};
const LANE_Y = {u: 215, v: 300, w: 385};
const PLAYER_RADIUS = 13;
const GATE_X = 655;
const HAZARD_RADIUS = 27;
const MOVE_SPEED = 255;

const clamp = (value, minimum, maximum) =>
  Math.max(minimum, Math.min(maximum, value));

const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

const nearestSlot = (y) => Object.entries(LANE_Y)
  .sort((left, right) => Math.abs(y - left[1]) - Math.abs(y - right[1]))[0][0];

const cloneTicket = (ticket) => ({
  alternatives: ticket.alternatives.map((plan) => ({...plan})),
  receipt: {...ticket.receipt},
  issued: ticket.issued,
});

export class Session {
  constructor(ticket, seed = 2903, level = 1) {
    this.ticket = cloneTicket(ticket);
    this.seed = seed;
    this.level = level;
    this.keys = new Set();
    this.restart();
  }

  restart() {
    this.player = {
      x: START.x,
      y: START.y,
      alive: true,
      respawning: false,
      flash: 0,
    };
    this.field = createField();
    this.panel = createPanel();
    this.tokens = [false, false];
    this.checkpoint = null;
    this.returnState = {
      armed: false,
      committed: false,
      ticket: null,
      returns: 0,
    };
    this.deaths = 0;
    this.elapsed = 0;
    this.respawnTicks = 0;
    this.completed = false;
    this.keys.clear();
  }

  setLevel(level) {
    this.level = Number(level) || 1;
    this.restart();
  }

  update(dt) {
    this.elapsed += dt;
    stepField(this.field);
    stepPanel(this.panel);
    if (this.completed) return;
    if (this.player.respawning) {
      this.player.flash = Math.max(0, this.player.flash - dt);
      this.respawnTicks -= 1;
      if (this.respawnTicks <= 0) this.restoreCheckpoint();
      return;
    }

    let dx = 0;
    let dy = 0;
    if (this.keys.has("arrowleft") || this.keys.has("a")) dx -= 1;
    if (this.keys.has("arrowright") || this.keys.has("d")) dx += 1;
    if (this.keys.has("arrowup") || this.keys.has("w")) dy -= 1;
    if (this.keys.has("arrowdown") || this.keys.has("s")) dy += 1;
    if (dx || dy) {
      const scale = MOVE_SPEED * dt / Math.hypot(dx, dy);
      this.player.x = clamp(this.player.x + dx * scale, 42, 958);
      this.player.y = clamp(this.player.y + dy * scale, 180, 420);
    }

    this.collectTokens();
    this.activateCheckpoint();
    this.commitReturn();
    this.resolveGate();
    this.resolveExit();
  }

  collectTokens() {
    const sites = [{x: 300, y: 385}, {x: 825, y: 215}];
    sites.forEach((site, index) => {
      if (!this.tokens[index] && distance(this.player, site) < 28) {
        this.tokens[index] = true;
      }
    });
  }

  activateCheckpoint() {
    if (this.checkpoint || !this.tokens[0]) return;
    if (
      Math.abs(this.player.x - CHECKPOINT.x) > 31 ||
      Math.abs(this.player.y - CHECKPOINT.y) > 126
    ) return;
    this.checkpoint = {
      x: CHECKPOINT.x,
      y: LANE_Y.u,
      tokens: [...this.tokens],
      field: snapshotField(this.field),
      panel: snapshotPanel(this.panel),
      ticket: cloneTicket(this.ticket),
    };
  }

  commitReturn() {
    if (
      !this.returnState.armed ||
      this.returnState.committed ||
      this.player.x <= 505
    ) return;
    stageField(this.field, this.returnState.ticket);
    stagePanel(this.panel, this.returnState.ticket);
    runField(this.field, true);
    runPanel(this.panel, true);
    this.returnState.committed = true;
  }

  resolveGate() {
    if (Math.abs(this.player.x - GATE_X) > 48) return;
    const slot = nearestSlot(this.player.y);
    if (slot === fieldOpenSlot(this.field)) return;
    const hazard = {x: GATE_X, y: LANE_Y[slot]};
    if (distance(this.player, hazard) < PLAYER_RADIUS + HAZARD_RADIUS) {
      this.deaths += 1;
      this.player.alive = false;
      this.player.respawning = true;
      this.player.flash = 0.44;
      this.respawnTicks = 28;
    }
  }

  restoreCheckpoint() {
    const note = this.checkpoint;
    if (note) {
      this.player.x = note.x;
      this.player.y = note.y;
      this.tokens = [...note.tokens];
      restoreField(this.field, note.field);
      restorePanel(this.panel, note.panel);
      this.returnState = {
        armed: true,
        committed: false,
        ticket: cloneTicket(note.ticket),
        returns: this.returnState.returns + 1,
      };
      runField(this.field, true);
      runPanel(this.panel, true);
    } else {
      this.player.x = START.x;
      this.player.y = START.y;
      this.tokens = [false, false];
      this.field = createField();
      this.panel = createPanel();
      this.returnState = {
        armed: false,
        committed: false,
        ticket: null,
        returns: 0,
      };
    }
    this.player.alive = true;
    this.player.respawning = false;
    this.player.flash = 0;
    this.respawnTicks = 0;
    this.keys.clear();
  }

  resolveExit() {
    if (this.player.x < 930 || !this.tokens.every(Boolean)) return;
    this.completed = true;
    this.keys.clear();
    runField(this.field, false);
    runPanel(this.panel, false);
  }

  keyDown(key) {
    const normalized = key.toLowerCase();
    if (normalized === "r") {
      this.restart();
      return;
    }
    this.keys.add(normalized);
  }

  keyUp(key) {
    this.keys.delete(key.toLowerCase());
  }

  getState() {
    const safe = Boolean(
      this.checkpoint &&
      Math.abs(this.player.x - CHECKPOINT.x) <= 48 &&
      Math.abs(this.player.y - CHECKPOINT.y) <= 132
    );
    return {
      seed: this.seed,
      level: this.level,
      is_actionable: !this.player.respawning && !this.completed,
      game_state: {
        elapsed_time: this.elapsed,
        player: {...this.player},
        checkpoint: {
          active: Boolean(this.checkpoint),
          returns: this.returnState.returns,
          saved: this.checkpoint
            ? {
                field: snapshotField(this.checkpoint.field),
                panel: snapshotPanel(this.checkpoint.panel),
              }
            : null,
        },
        safe_zone: {occupied: safe},
        triad: {
          field: snapshotField(this.field),
          panel: snapshotPanel(this.panel),
          field_open: fieldOpenSlot(this.field),
          panel_open: panelOpenSlot(this.panel),
          field_complete: fieldComplete(this.field),
          panel_complete: panelComplete(this.panel),
          return_armed: this.returnState.armed,
          return_committed: this.returnState.committed,
        },
      },
      metrics: {
        tokens: this.tokens.filter(Boolean).length,
        remaining_tokens: this.tokens.filter((value) => !value).length,
        deaths: this.deaths,
      },
      terminal: {
        isTerminal: this.completed,
        outcome: this.completed ? "success" : null,
      },
    };
  }
}

export const lanes = {...LANE_Y};
