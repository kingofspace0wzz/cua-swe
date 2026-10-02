import { STATES } from "./evaluate.js";

export class ConstraintLedger {
  constructor() {
    this.reset();
  }

  reset() {
    this.exact = Array(5).fill(null);
    this.minimum = {};
  }

  addRow(word, statuses) {
    const rowMinimum = {};
    statuses.forEach((status, position) => {
      const letter = word[position];
      if (status === STATES.exact) this.exact[position] = letter;
      if (status === STATES.exact || status === STATES.present) {
        rowMinimum[letter] = (rowMinimum[letter] || 0) + 1;
      }
    });
    for (const [letter, count] of Object.entries(rowMinimum)) {
      this.minimum[letter] = Math.max(this.minimum[letter] || 0, count);
    }
  }

  accepts(word) {
    for (let position = 0; position < this.exact.length; position += 1) {
      if (this.exact[position] && word[position] !== this.exact[position]) {
        return false;
      }
    }
    for (const [letter, count] of Object.entries(this.minimum)) {
      const occurrences = [...word].filter((value) => value === letter).length;
      if (occurrences < count) return false;
    }
    return true;
  }

  snapshot() {
    return {
      exact: [...this.exact],
      minimum: { ...this.minimum }
    };
  }
}
