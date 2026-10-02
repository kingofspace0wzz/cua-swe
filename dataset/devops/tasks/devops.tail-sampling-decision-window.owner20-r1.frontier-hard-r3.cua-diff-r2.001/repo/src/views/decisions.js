import { escapeHtml } from "./components.js";

export function renderDecisions(snapshot) {
  document.querySelector("#decisions").innerHTML = snapshot.decisions
    .map((trace) => `
      <li class="${trace.sampled ? "sampled" : "dropped"}" data-trace-id="${trace.id}">
        <button>
          <span>${escapeHtml(trace.service)}</span>
          <strong>${trace.sampled ? "sampled" : "dropped"}</strong>
          <code>${escapeHtml(trace.id)}</code>
          <small>${escapeHtml(trace.bucket)} · ${trace.durationMs}ms · ${escapeHtml(trace.reasons.join(", ") || "no policy")}</small>
        </button>
      </li>`)
    .join("");
}
