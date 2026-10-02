import { escapeHtml, percent } from "./components.js";
export function renderSlices(snapshot) {
  document.querySelector("#slices").innerHTML = `<table><thead><tr><th>Endpoint</th><th>Region</th><th>Good</th><th>Bad</th><th>Total</th><th>Availability</th><th>Slice verdict</th></tr></thead><tbody>
    ${snapshot.slices.map((slice) => `<tr data-slice-id="${slice.id}" class="${slice.verdict}">
      <td><button>${escapeHtml(slice.endpoint)}</button></td><td>${escapeHtml(slice.region)}</td>
      <td>${slice.good}</td><td>${slice.bad}</td><td>${slice.total}</td>
      <td>${percent(slice.availability)}</td><td>${slice.verdict}</td>
    </tr>`).join("")}
  </tbody></table>`;
}
