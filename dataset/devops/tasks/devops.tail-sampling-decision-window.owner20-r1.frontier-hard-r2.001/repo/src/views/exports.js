import { escapeHtml } from "./components.js";

export function renderExports(snapshot) {
  document.querySelector("#exports").innerHTML = snapshot.exports.length
    ? snapshot.exports.map((item) =>
      `<li><strong>${escapeHtml(item.service)}</strong><code>${escapeHtml(item.id)}</code><span>${escapeHtml(item.reasons.join(", "))}</span></li>`,
    ).join("")
    : "<li>No traces exported.</li>";
}
