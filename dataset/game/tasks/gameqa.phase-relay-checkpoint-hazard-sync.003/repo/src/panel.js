import {
  complete,
  consumeTicket,
  createRecord,
  openSlot,
  pull,
  restoreRecord,
  setRoute,
  setRunning,
  snapshotRecord,
  tick,
} from "./triad.js";

export function createPanel() {
  return createRecord();
}

export function stepPanel(panel) {
  if (tick(panel)) pull(panel);
}

export function snapshotPanel(panel) {
  return snapshotRecord(panel);
}

export function restorePanel(panel, note) {
  restoreRecord(panel, note);
}

export function stagePanel(panel, ticket) {
  const checksum = consumeTicket(ticket);
  setRoute(panel, ticket.alternatives[(checksum + 1) % 3]);
}

export function runPanel(panel, active) {
  setRunning(panel, active);
}

export function panelOpenSlot(panel) {
  return openSlot(panel);
}

export function panelComplete(panel) {
  return complete(panel);
}
