import { escapeHtml, percent } from "./components.js";
export function renderDetail(snapshot) {
  const slice = snapshot.selected;
  document.querySelector("#detail").innerHTML = slice ? `<dl>
    <dt>Slice</dt><dd>${escapeHtml(slice.id)}</dd><dt>Endpoint</dt><dd>${escapeHtml(slice.endpoint)}</dd>
    <dt>Region</dt><dd>${escapeHtml(slice.region)}</dd><dt>Availability</dt><dd>${percent(slice.availability)}</dd>
    <dt>Good / bad / total</dt><dd>${slice.good} / ${slice.bad} / ${slice.total}</dd>
    <dt>Verdict</dt><dd>${slice.verdict}</dd>
  </dl>` : "<p>Select a slice.</p>";
}
