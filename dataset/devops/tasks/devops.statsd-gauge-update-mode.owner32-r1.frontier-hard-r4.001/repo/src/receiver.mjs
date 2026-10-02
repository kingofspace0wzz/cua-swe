import {ingestCapture} from './ingest.mjs';
export function createReceiver(origin) {
  let state = new Map(), cursor = 0, epoch = 0, error = null, timer = null, pending = Promise.resolve();
  async function request(path, body) {
    const response = await fetch(origin + path, body === undefined ? {} : {
      method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error('Receiver request failed: ' + response.status);
    return response.json();
  }
  async function drain() {
    const capture = await request('/capture?after=' + cursor);
    if (capture.epoch !== epoch) return;
    for (const receipt of capture.receipts) {
      const updates = ingestCapture(receipt, state);
      await request('/ingest', {epoch, receipt: receipt.sequence, updates});
      cursor = receipt.sequence;
    }
  }
  function stop() { if (timer) clearInterval(timer); timer = null; }
  function pump() {
    pending = pending.then(drain).catch(e => { error = e.message; stop(); });
  }
  async function begin(seed = false) {
    if (seed) {
      const current = await request('/snapshot');
      if (current.seeded) {
        if (epoch !== current.epoch) {
          state = new Map(Object.entries(current.state)); cursor = current.committedReceipt;
          epoch = current.epoch; error = null;
          if (!timer) { timer = setInterval(pump, 25); pump(); }
        }
        return {alreadySeeded: true, epoch};
      }
    }
    stop(); await pending;
    const snapshot = await request('/begin', {seed});
    if (snapshot.alreadySeeded) return snapshot;
    state = new Map(); cursor = 0; epoch = snapshot.epoch; error = null;
    timer = setInterval(pump, 25); pump(); return snapshot;
  }
  async function reset() {
    stop(); await pending; const snapshot = await request('/reset', {});
    state = new Map(); cursor = 0; epoch = snapshot.epoch; error = null; return snapshot;
  }
  return {begin, reset, status: () => ({cursor, epoch, error}), close: stop};
}
