import {
  complete,
  consumeTicket,
  createRecord,
  openSlot,
  push,
  restoreRecord,
  setRoute,
  setRunning,
  snapshotRecord,
  tick,
} from "./triad.js";

export function createField() {
  return createRecord();
}

export function stepField(field) {
  if (tick(field)) push(field);
}

export function snapshotField(field) {
  return snapshotRecord(field);
}

export function restoreField(field, note) {
  restoreRecord(field, note);
}

export function stageField(field, ticket) {
  const checksum = consumeTicket(ticket);
  setRoute(field, ticket.alternatives[checksum % 3]);
}

export function runField(field, active) {
  setRunning(field, active);
}

export function fieldOpenSlot(field) {
  return openSlot(field);
}

export function fieldComplete(field) {
  return complete(field);
}
