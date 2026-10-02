import { escapeHtml } from "./components.js";
export function renderReceiver(catalog) {
  const receiver = catalog.receiver;
  const rows = receiver.deliveries.map(item => `<div class="ledger-row" data-delivery-id="${escapeHtml(item.traceId)}"><span>${escapeHtml(item.window)}</span><span>${escapeHtml(item.service)}</span><small>first span +0 ms · last span +${item.lastSpanAtMs - item.firstSpanAtMs} ms</small></div>`).join("");
  const identity = `<p class="firmware">Receiver firmware ${escapeHtml(receiver.firmware.build)} · delivery profile ${escapeHtml(receiver.firmware.profileCode)} · envelopes: runbook ${escapeHtml(receiver.runbook.id)}</p>`;
  document.querySelector("#receiver").innerHTML = `${identity}<p class="muted">Spans recorded by the receiver for every window and the replay staging buffer, relative to each trace's first receipt.</p>${rows}`;
  const runbook = document.querySelector("#runbook");
  if (runbook.dataset.loaded !== "yes") {
    runbook.innerHTML = `<p class="muted">Published and maintained by the receiver operations team; the profile envelopes are intentionally not part of this repository.</p><img data-testid="runbook-image" src="/api/runbook" alt="Receiver operations runbook ${escapeHtml(receiver.runbook.id)}">`;
    runbook.dataset.loaded = "yes";
  }
}
