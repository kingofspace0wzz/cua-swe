import { ConstraintLedger } from "./constraints.js";
import { evaluateGuess, STATES, strongerStatus } from "./evaluate.js";
import { RevealTimeline } from "./reveal.js";

const ROWS = 6;
const COLS = 5;
const LETTERS = "abcdefghijklmnopqrstuvwxyz";

function emptyRow() {
  return {
    word: "",
    tiles: Array.from({ length: COLS }, () => ({
      letter: "",
      status: STATES.empty,
      revealed: false
    }))
  };
}

export class LetterGame {
  constructor(challenge, render) {
    this.challenge = challenge;
    this.render = render;
    this.timeline = new RevealTimeline(challenge.revealStepMs || 170);
    this.constraints = new ConstraintLedger();
    this.round = 0;
    this.hardEnabled = true;
    this.restart();
  }

  restart() {
    this.round += 1;
    this.timeline.close();
    this.constraints.reset();
    this.rows = Array.from({ length: ROWS }, emptyRow);
    this.keyboard = Object.fromEntries(
      [...LETTERS].map((letter) => [letter, STATES.empty])
    );
    this.currentRow = 0;
    this.input = "";
    this.active = true;
    this.revealActive = false;
    this.revealCount = 0;
    this.validationRejections = 0;
    this.hardRejections = 0;
    this.completed = false;
    this.message = "Daily row ready";
    this.messageKind = "info";
    this.render(this.snapshot());
  }

  setHardMode(enabled) {
    if (this.currentRow > 0 || this.revealActive) {
      this.message = "Hard guidance is fixed after the first submission";
      this.messageKind = "error";
      this.render(this.snapshot());
      return false;
    }
    this.hardEnabled = Boolean(enabled);
    this.message = this.hardEnabled ? "Hard guidance enabled" : "Hard guidance disabled";
    this.messageKind = "info";
    this.render(this.snapshot());
    return true;
  }

  inputLetter(letter) {
    if (
      !this.active ||
      this.revealActive ||
      !/^[a-z]$/.test(letter) ||
      this.input.length >= COLS
    ) {
      return;
    }
    this.input += letter;
    this.syncInput();
  }

  erase() {
    if (!this.active || this.revealActive || !this.input) return;
    this.input = this.input.slice(0, -1);
    this.syncInput();
  }

  syncInput() {
    const row = this.rows[this.currentRow];
    if (!row) return;
    row.word = this.input;
    row.tiles.forEach((tile, index) => {
      tile.letter = this.input[index] || "";
      tile.status = STATES.empty;
      tile.revealed = false;
    });
    this.render(this.snapshot());
  }

  submit() {
    if (!this.active) return;
    if (this.revealActive) {
      this.reject("Let the current row finish", "validation");
      return;
    }
    if (this.input.length !== COLS) {
      this.reject("Five letters are required", "validation");
      return;
    }
    if (!this.challenge.acceptedWords.includes(this.input)) {
      this.reject("Entry is not in this puzzle", "validation");
      return;
    }
    if (
      this.hardEnabled &&
      this.currentRow > 0 &&
      !this.constraints.accepts(this.input)
    ) {
      this.reject("Hard guidance is not satisfied", "hard");
      return;
    }

    const rowIndex = this.currentRow;
    const word = this.input;
    const statuses = evaluateGuess(this.challenge.answer, word);
    this.rows[rowIndex].word = word;
    this.rows[rowIndex].tiles.forEach((tile, index) => {
      tile.letter = word[index];
    });
    this.currentRow += 1;
    this.input = "";
    this.revealActive = true;
    this.revealCount = 0;
    this.message = "Turning the row…";
    this.messageKind = "info";
    this.timeline.begin(
      {
        round: this.round,
        rowIndex,
        word,
        statuses
      },
      (step) => this.applyRevealStep(step),
      (packet) => this.finishReveal(packet)
    );
    this.render(this.snapshot());
  }

  reject(message, kind) {
    const round = this.round;
    if (kind === "hard") this.hardRejections += 1;
    else this.validationRejections += 1;
    this.message = message;
    this.messageKind = "error";
    this.render(this.snapshot(), { shakeRow: this.currentRow });
    window.setTimeout(() => {
      if (!this.active || this.round !== round || this.revealActive) return;
      this.input = "";
      this.syncInput();
    }, 190);
  }

  applyRevealStep(step) {
    if (step.round !== this.round) return;
    const tile = this.rows[step.rowIndex].tiles[step.index];
    tile.status = step.status;
    tile.revealed = true;
    this.revealCount = step.index + 1;
    const letter = step.word[step.index];
    this.keyboard[letter] = strongerStatus(this.keyboard[letter], step.status);
    this.render(this.snapshot(), {
      revealTile: [step.rowIndex, step.index]
    });
  }

  finishReveal(packet) {
    if (packet.round !== this.round) return;
    this.constraints.addRow(packet.word, packet.statuses);
    this.revealActive = false;
    this.revealCount = packet.statuses.length;
    if (packet.word === this.challenge.answer) {
      this.active = false;
      this.completed = true;
      this.message = "Pattern complete";
      this.messageKind = "success";
      this.render(this.snapshot(), {
        startCelebration: { rowIndex: packet.rowIndex }
      });
      return;
    }
    if (this.currentRow >= ROWS) {
      this.active = false;
      this.message = "No rows remain";
      this.messageKind = "error";
    } else {
      this.message = "Next row ready";
      this.messageKind = "info";
    }
    this.render(this.snapshot());
  }

  snapshot() {
    return {
      challenge: {
        id: this.challenge.id,
        name: this.challenge.name,
        mode: this.challenge.mode,
        seed: this.challenge.seed,
        level: this.challenge.level
      },
      round: this.round,
      rows: this.rows.map((row) => ({
        word: row.word,
        tiles: row.tiles.map((tile) => ({ ...tile }))
      })),
      keyboard: { ...this.keyboard },
      currentRow: this.currentRow,
      input: this.input,
      active: this.active,
      reveal: {
        active: this.revealActive,
        revealedTiles: this.revealCount
      },
      validation: {
        rejected: this.validationRejections,
        hardRejected: this.hardRejections
      },
      hardMode: {
        enabled: this.hardEnabled,
        ...this.constraints.snapshot()
      },
      terminal: {
        isTerminal: !this.active,
        success: this.completed
      },
      message: this.message,
      messageKind: this.messageKind,
      is_actionable: this.active && !this.revealActive
    };
  }
}
