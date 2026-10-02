import { byId, clear, element } from "./components.js";

function outsideParent(span, index) {
  if (span.parentId === null) return false;
  const parent = index.get(span.parentId);
  return Boolean(parent && (span.startMs < parent.startMs || span.endMs > parent.endMs));
}

export function renderWaterfall(trace, spans, annotations) {
  const host = clear(document.querySelector('[data-test="waterfall"]'));
  const index = byId(spans);
  const root = spans.find((span) => span.parentId === null);
  const width = Math.max(root?.durationMs || 1, 1);
  const adjustedIds = new Set(annotations.map((item) => item.spanId));
  for (const span of spans) {
    const row = element("article", "span-row");
    const outside = outsideParent(span, index);
    row.dataset.test = `span-${span.id}`;
    row.dataset.outside = String(outside);
    row.dataset.startMs = String(span.startMs);
    row.dataset.endMs = String(span.endMs);
    row.dataset.durationMs = String(span.durationMs);
    const name = element("div", "span-name");
    name.append(
      element("strong", "", `${span.service} · ${span.operation}`),
      element("small", "", `${span.host} · ${span.durationMs}ms`),
    );
    const track = element("div", "bar-track");
    const bar = element("div", `bar${outside ? " outside" : ""}${adjustedIds.has(span.id) ? " adjusted" : ""}`);
    bar.style.left = `${((span.startMs - root.startMs) / width) * 100}%`;
    bar.style.width = `${Math.max((span.durationMs / width) * 100, 1)}%`;
    track.append(bar);
    const range = element("span", "range", `${span.startMs}ms → ${span.endMs}ms`);
    row.append(name, track, range);
    host.append(row);
  }
}

export function countOutside(spans) {
  const index = byId(spans);
  return spans.filter((span) => outsideParent(span, index)).length;
}
