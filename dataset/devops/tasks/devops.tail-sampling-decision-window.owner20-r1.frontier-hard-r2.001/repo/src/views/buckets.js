import { escapeHtml } from "./components.js";

export function renderBuckets(snapshot) {
  document.querySelector("#buckets").innerHTML = `
    <table>
      <thead><tr><th>Bucket</th><th>Received</th><th>Sampled</th><th>Rate</th></tr></thead>
      <tbody>
        ${snapshot.buckets.map((bucket) => `
          <tr data-bucket="${bucket.id}">
            <td>${escapeHtml(bucket.label)}</td>
            <td>${bucket.received}</td>
            <td>${bucket.sampled}</td>
            <td>${bucket.received ? Math.round(bucket.sampled / bucket.received * 100) : 0}%</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}
