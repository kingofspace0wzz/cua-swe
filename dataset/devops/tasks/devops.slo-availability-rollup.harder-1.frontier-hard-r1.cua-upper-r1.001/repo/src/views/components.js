export const escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
export const percent = (value) => `${(value * 100).toFixed(3)}%`;
export const metric = (label, value, testid, tone = "") => `<div class="metric ${tone}" data-testid="${testid}"><span>${label}</span><strong>${value}</strong></div>`;
