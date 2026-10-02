export function normalizeAngle(value) {
  return ((value % 360) + 360) % 360;
}

export function circularDistance(left, right) {
  const distance = Math.abs(normalizeAngle(left) - normalizeAngle(right));
  return Math.min(distance, 360 - distance);
}
