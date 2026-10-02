const SLOTS = ["u", "v", "w"];
const PERIOD = 180;

const copyObject = (value) => Object.fromEntries(
  Object.entries(value).map(([key, item]) => [
    key,
    item && typeof item === "object" && !Array.isArray(item)
      ? copyObject(item)
      : Array.isArray(item)
        ? [...item]
        : item,
  ]),
);

export function invert(route) {
  const result = {};
  for (const source of SLOTS) result[route[source]] = source;
  return result;
}

export function validRoute(route) {
  return (
    route &&
    SLOTS.every((slot) => SLOTS.includes(route[slot])) &&
    new Set(Object.values(route)).size === 3
  );
}

export function consumeTicket(ticket) {
  if (
    !ticket ||
    !Array.isArray(ticket.alternatives) ||
    ticket.alternatives.length !== 3 ||
    !ticket.alternatives.every(validRoute) ||
    !ticket.receipt ||
    !["u", "v", "w"].every((slot) => Number.isInteger(ticket.receipt[slot])) ||
    !Number.isInteger(ticket.issued)
  ) throw new Error("invalid runtime ticket");
  const signatures = ticket.alternatives.map((route) => SLOTS.map((slot) => route[slot]).join(""));
  if (new Set(signatures).size !== 3) throw new Error("runtime ticket is not three-way");
  const signatureChecksum = signatures
    .map((signature, index) => [...signature].reduce(
      (total, value) => total + value.charCodeAt(0) * (index + 1),
      0,
    ))
    .reduce((left, right) => left ^ right, 0);
  return (
    signatureChecksum ^
    ticket.receipt.u * 3 ^
    ticket.receipt.v * 5 ^
    ticket.receipt.w * 7 ^
    ticket.issued
  );
}

export function createRecord() {
  return {
    clock: 45,
    pulses: 0,
    active: true,
    generation: 0,
    assignment: {u: "a", v: "b", w: "c"},
    route: {u: "u", v: "v", w: "w"},
    trail: ["u", "u", "u"],
    capsules: {
      a: {tone: 0, open: true, charge: 1},
      b: {tone: 1, open: false, charge: 1},
      c: {tone: 2, open: false, charge: 1},
    },
  };
}

export function snapshotRecord(record) {
  return copyObject(record);
}

export function restoreRecord(record, note) {
  record.clock = note.clock;
  record.pulses = note.pulses;
  record.active = note.active;
  record.generation = note.generation;
  record.assignment = copyObject(note.assignment);
  record.route = copyObject(note.route);
  record.trail = [...note.trail];
  record.capsules = copyObject(note.capsules);
}

export function setRunning(record, active) {
  record.active = Boolean(active);
}

export function setRoute(record, route) {
  record.route = copyObject(route);
  record.generation += 1;
}

export function tick(record) {
  if (!record.active) return false;
  record.clock += 1;
  for (const key of Object.keys(record.capsules)) {
    record.capsules[key].charge = 0.72 + 0.28 * Math.sin(
      (record.clock + record.capsules[key].tone * 60) * Math.PI / 90,
    );
  }
  if (record.clock < PERIOD) return false;
  record.clock = 0;
  record.pulses += 1;
  return true;
}

export function push(record) {
  const next = {};
  for (const source of SLOTS) next[record.route[source]] = record.assignment[source];
  record.assignment = next;
  record.trail = [...record.trail.slice(-2), openSlot(record)];
}

export function pull(record) {
  const next = {};
  for (const destination of SLOTS) {
    next[destination] = record.assignment[record.route[destination]];
  }
  record.assignment = next;
  record.trail = [...record.trail.slice(-2), openSlot(record)];
}

export function openSlot(record) {
  return SLOTS.find((slot) => record.capsules[record.assignment[slot]].open) ?? "u";
}

export function phase(record) {
  return record.clock / PERIOD;
}

export function complete(record) {
  return (
    Number.isInteger(record.clock) &&
    Number.isInteger(record.pulses) &&
    typeof record.active === "boolean" &&
    Number.isInteger(record.generation) &&
    SLOTS.every((slot) => SLOTS.includes(record.route[slot])) &&
    new Set(Object.values(record.route)).size === 3 &&
    SLOTS.every((slot) => record.assignment[slot] in record.capsules) &&
    new Set(Object.values(record.assignment)).size === 3 &&
    Array.isArray(record.trail) &&
    record.trail.length === 3 &&
    record.trail.every((slot) => SLOTS.includes(slot)) &&
    Object.values(record.capsules).every((capsule) => (
      Number.isInteger(capsule.tone) &&
      typeof capsule.open === "boolean" &&
      Number.isFinite(capsule.charge)
    ))
  );
}
