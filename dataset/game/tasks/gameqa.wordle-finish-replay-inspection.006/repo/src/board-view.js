import { STATES } from "./evaluate.js";
import { ResultMotion } from "./motion.js";

const KEY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"];

function tileFace(face, className) {
  const element = document.createElement("div");
  element.className = `tile-face ${className}`;
  element.dataset.face = face;
  return element;
}

export class BoardView {
  constructor() {
    this.boardElement = document.querySelector("#board");
    this.keyboardElement = document.querySelector("#keyboard");
    this.noticeElement = document.querySelector("#notice");
    this.modeNameElement = document.querySelector("#mode-name");
    this.modeLabelElement = document.querySelector("#mode-label");
    this.roundElement = document.querySelector("#round-label");
    this.guidanceElement = document.querySelector("#guidance");
    this.hardModeElement = document.querySelector("#hard-mode");
    this.resultElement = document.querySelector("#result");
    this.motion = new ResultMotion(this.resultElement);
    this.lastRound = null;
    this.handlers = {};
    this.createBoard();
    this.createKeyboard();
    this.bindControls();
  }

  setHandlers(handlers) {
    this.handlers = handlers;
  }

  createBoard() {
    this.boardElement.replaceChildren();
    for (let row = 0; row < 6; row += 1) {
      const rowElement = document.createElement("div");
      rowElement.className = "board-row";
      rowElement.dataset.row = String(row);
      for (let column = 0; column < 5; column += 1) {
        const slot = document.createElement("div");
        slot.className = "tile-slot";
        slot.dataset.row = String(row);
        slot.dataset.column = String(column);
        slot.dataset.status = STATES.empty;
        const motion = document.createElement("div");
        motion.className = "tile-motion";
        motion.dataset.status = STATES.empty;
        motion.append(tileFace("front", "tile-front"));
        motion.append(tileFace("back", "tile-back"));
        slot.append(motion);
        rowElement.append(slot);
      }
      this.boardElement.append(rowElement);
    }
  }

  createKey(label, value, wide = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `key${wide ? " wide" : ""}`;
    button.dataset.key = value;
    button.dataset.status = STATES.empty;
    button.textContent = label;
    button.addEventListener("click", () => this.handlers.key?.(value));
    return button;
  }

  createKeyboard() {
    this.keyboardElement.replaceChildren();
    KEY_ROWS.forEach((letters, rowIndex) => {
      const row = document.createElement("div");
      row.className = "key-row";
      if (rowIndex === 2) row.append(this.createKey("Enter", "enter", true));
      [...letters].forEach((letter) => row.append(this.createKey(letter, letter)));
      if (rowIndex === 2) row.append(this.createKey("Erase", "erase", true));
      this.keyboardElement.append(row);
    });
  }

  bindControls() {
    document.querySelector("#restart").addEventListener("click", () => {
      this.handlers.restart?.();
    });
    document.querySelectorAll("[data-mode]").forEach((button) => {
      button.addEventListener("click", () => this.handlers.mode?.(button.dataset.mode));
    });
    this.hardModeElement.addEventListener("change", () => {
      const accepted = this.handlers.hard?.(this.hardModeElement.checked);
      if (accepted === false) this.hardModeElement.checked = !this.hardModeElement.checked;
    });
  }

  paintGuidance(hardMode) {
    this.guidanceElement.replaceChildren();
    const chips = [];
    hardMode.exact.forEach((letter, position) => {
      if (!letter) return;
      const chip = document.createElement("span");
      chip.className = "guidance-chip exact";
      chip.dataset.kind = "exact";
      chip.dataset.letter = letter;
      chip.dataset.position = String(position);
      chip.textContent = `${letter.toUpperCase()} fixed at ${position + 1}`;
      chips.push(chip);
    });
    for (const [letter, count] of Object.entries(hardMode.minimum)) {
      const chip = document.createElement("span");
      chip.className = "guidance-chip present";
      chip.dataset.kind = "minimum";
      chip.dataset.letter = letter;
      chip.dataset.count = String(count);
      chip.textContent = `${letter.toUpperCase()} × ${count}+`;
      chips.push(chip);
    }
    if (!chips.length) {
      const empty = document.createElement("span");
      empty.className = "guidance-empty";
      empty.textContent = "No active clues";
      this.guidanceElement.append(empty);
    } else {
      this.guidanceElement.append(...chips);
    }
  }

  render(state, animation = {}) {
    if (this.lastRound !== state.round) {
      this.motion.reset(this.boardElement);
      this.lastRound = state.round;
    }
    this.modeNameElement.textContent = state.challenge.name;
    this.modeLabelElement.textContent =
      state.challenge.mode === "daily" ? "Daily puzzle" : "Practice puzzle";
    this.roundElement.textContent = `Round ${state.round}`;
    this.noticeElement.textContent = state.message;
    this.noticeElement.dataset.kind = state.messageKind;
    this.hardModeElement.checked = state.hardMode.enabled;
    this.hardModeElement.disabled = state.currentRow > 0 || state.reveal.active;
    document.querySelectorAll("[data-mode]").forEach((button) => {
      button.dataset.active = String(button.dataset.mode === state.challenge.mode);
    });

    state.rows.forEach((row, rowIndex) => {
      const rowElement = this.boardElement.querySelector(`[data-row="${rowIndex}"].board-row`);
      row.tiles.forEach((tile, columnIndex) => {
        const slot = rowElement.querySelector(`.tile-slot[data-column="${columnIndex}"]`);
        const motion = slot.querySelector(".tile-motion");
        const front = motion.querySelector(".tile-front");
        const back = motion.querySelector(".tile-back");
        front.textContent = tile.letter;
        back.textContent = tile.letter;
        slot.dataset.status = tile.revealed ? tile.status : STATES.empty;
        motion.dataset.status = tile.revealed ? tile.status : STATES.empty;
        slot.dataset.filled = String(Boolean(tile.letter));
        motion.classList.toggle("is-revealed", tile.revealed);
        motion.setAttribute(
          "aria-label",
          tile.letter
            ? `${tile.letter.toUpperCase()} ${tile.revealed ? tile.status : "unrevealed"}`
            : "empty"
        );
      });
    });

    Object.entries(state.keyboard).forEach(([letter, status]) => {
      const key = this.keyboardElement.querySelector(`[data-key="${letter}"]`);
      key.dataset.status = status;
      key.setAttribute("aria-label", `${letter.toUpperCase()} ${status}`);
    });
    this.paintGuidance(state.hardMode);
    this.resultElement.hidden = !state.terminal.success || !this.motion.snapshot().complete;

    if (animation.shakeRow !== undefined) {
      const row = this.boardElement.querySelector(
        `.board-row[data-row="${animation.shakeRow}"]`
      );
      row.classList.remove("shake");
      void row.offsetWidth;
      row.classList.add("shake");
    }
    if (animation.startCelebration) {
      const row = this.boardElement.querySelector(
        `.board-row[data-row="${animation.startCelebration.rowIndex}"]`
      );
      this.motion.celebrate(row);
    }
  }

  visibleFace(slot) {
    const motion = slot.querySelector(".tile-motion");
    const slotRect = slot.getBoundingClientRect();
    const rect = motion.getBoundingClientRect();
    const x = rect.left + rect.width * 0.22;
    const y = rect.top + rect.height * 0.22;
    const hit = document.elementFromPoint(x, y);
    const face = hit?.closest?.(".tile-face");
    return {
      face: face?.dataset.face || null,
      color: face ? getComputedStyle(face).backgroundColor : null,
      motionRect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height
      },
      slotRect: {
        x: slotRect.x,
        y: slotRect.y,
        width: slotRect.width,
        height: slotRect.height
      },
      transform: getComputedStyle(motion).transform,
      transitionDuration: getComputedStyle(motion).transitionDuration
    };
  }

  snapshot() {
    const tiles = [...this.boardElement.querySelectorAll(".tile-slot")].map((slot) => ({
      row: Number(slot.dataset.row),
      column: Number(slot.dataset.column),
      status: slot.dataset.status,
      letter: slot.querySelector(".tile-front").textContent.toLowerCase(),
      celebrating:
        slot.classList.contains("is-celebrating") ||
        slot.querySelector(".tile-motion").classList.contains("is-celebrating"),
      ...this.visibleFace(slot)
    }));
    const keyboard = Object.fromEntries(
      [...this.keyboardElement.querySelectorAll(".key[data-key]")]
        .filter((key) => key.dataset.key.length === 1)
        .map((key) => [key.dataset.key, key.dataset.status || STATES.empty])
    );
    const guidance = [...this.guidanceElement.querySelectorAll(".guidance-chip")].map(
      (chip) => ({
        kind: chip.dataset.kind,
        letter: chip.dataset.letter,
        position:
          chip.dataset.position === undefined ? null : Number(chip.dataset.position),
        count: chip.dataset.count === undefined ? null : Number(chip.dataset.count),
        text: chip.textContent
      })
    );
    return {
      tiles,
      keyboard,
      guidance,
      motion: this.motion.snapshot(),
      resultVisible: !this.resultElement.hidden
    };
  }
}
