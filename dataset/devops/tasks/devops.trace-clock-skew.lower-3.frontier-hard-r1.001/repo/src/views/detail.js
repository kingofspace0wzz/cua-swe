import { byId, clear, element } from "./components.js";

function comparisonCard(trace, adjusted) {
  const rawById = byId(trace.spans);
  const adjustedById = byId(adjusted);
  const offending = trace.spans.find((span) => {
    if (span.parentId === null) return false;
    const parent = rawById.get(span.parentId);
    return span.startMs < parent.startMs || span.endMs > parent.endMs;
  });
  if (!offending) return null;
  const parent = rawById.get(offending.parentId);
  const shown = adjustedById.get(offending.id);
  const direction = offending.startMs < parent.startMs ? "leads" : "trails";
  const shift = shown.startMs - offending.startMs;
  const card = element("article", "comparison-card");
  card.dataset.test = "skew-comparison-card";
  card.dataset.direction = direction;
  card.dataset.corrected = String(
    shown.startMs >= parent.startMs && shown.endMs <= parent.endMs,
  );
  card.append(
    element("p", "eyebrow", `${direction} parent clock`),
    element("strong", "", trace.title),
    element("p", "comparison-host", `${offending.host} · coherent shift ${shift}ms`),
    element("p", "comparison-raw", `reported ${offending.startMs} → ${offending.endMs}`),
    element("p", "comparison-shown", `displayed ${shown.startMs} → ${shown.endMs}`),
    element("p", "comparison-duration", `duration ${shown.durationMs}ms`),
    element("p", "comparison-root", `parent ${parent.startMs} → ${parent.endMs}`),
  );
  return card;
}

export function renderSkewComparison(comparisons) {
  const host = clear(document.querySelector('[data-test="skew-comparison"]'));
  for (const comparison of comparisons) {
    const card = comparisonCard(comparison.trace, comparison.adjusted);
    if (card) host.append(card);
  }
}

export function renderDetail(raw, adjusted) {
  const host = clear(document.querySelector('[data-test="span-detail"]'));
  const adjustedById = byId(adjusted);
  const header = element("div", "detail-row header");
  for (const value of ["Span", "Host", "Reported", "Displayed", "Duration"]) {
    header.append(element("strong", "", value));
  }
  host.append(header);
  for (const span of raw) {
    const shown = adjustedById.get(span.id);
    const row = element("div", "detail-row");
    row.dataset.test = `detail-${span.id}`;
    row.append(
      element("span", "", span.operation),
      element("span", "", span.host),
      element("span", "", `${span.startMs} → ${span.endMs}`),
      element("span", shown.startMs === span.startMs ? "" : "changed", `${shown.startMs} → ${shown.endMs}`),
      element("span", "", `${shown.durationMs}ms`),
    );
    host.append(row);
  }
}
