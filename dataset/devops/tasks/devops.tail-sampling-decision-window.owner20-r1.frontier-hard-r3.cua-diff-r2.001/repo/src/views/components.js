export const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

export const metric = (label, value, testid) =>
  `<div class="metric" data-testid="${testid}"><span>${label}</span><strong>${value}</strong></div>`;
