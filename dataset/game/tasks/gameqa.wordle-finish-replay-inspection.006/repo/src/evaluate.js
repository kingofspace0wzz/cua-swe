export const STATES = Object.freeze({
  empty: "empty",
  exact: "exact",
  present: "present",
  absent: "absent"
});

export const STATUS_STRENGTH = Object.freeze({
  [STATES.empty]: 0,
  [STATES.absent]: 1,
  [STATES.present]: 2,
  [STATES.exact]: 3
});

export function strongerStatus(left, right) {
  return STATUS_STRENGTH[left] >= STATUS_STRENGTH[right] ? left : right;
}

export function evaluateGuess(answer, guess) {
  const remaining = answer.toLowerCase().split("");
  const letters = guess.toLowerCase().split("");
  const result = Array(letters.length).fill(STATES.absent);

  for (let index = 0; index < letters.length; index += 1) {
    if (letters[index] === remaining[index]) {
      result[index] = STATES.exact;
      remaining[index] = null;
    }
  }

  for (let index = 0; index < letters.length; index += 1) {
    if (result[index] === STATES.exact) continue;
    const match = remaining.indexOf(letters[index]);
    if (match >= 0) {
      remaining[match] = null;
      result[index] = STATES.present;
    }
  }

  return result;
}
