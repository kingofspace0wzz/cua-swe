import { clear, element } from "./components.js";

export function renderHosts(trace, adjusted) {
  const host = clear(document.querySelector('[data-test="hosts"]'));
  const rawById = new Map(trace.spans.map((span) => [span.id, span]));
  const notes = new Map((trace.hostNotes || []).map((entry) => [entry.host, entry.note]));
  const shifts = new Map();
  for (const span of adjusted) {
    const shift = span.startMs - rawById.get(span.id).startMs;
    if (!shifts.has(span.host)) shifts.set(span.host, []);
    shifts.get(span.host).push(shift);
  }
  for (const [name, values] of [...shifts].sort()) {
    const unique = [...new Set(values)];
    const row = element("div", "host-row");
    row.dataset.test = `host-${name}`;
    const heading = element("div", "host-heading");
    heading.append(
      element("strong", "", name),
      element("span", unique.length === 1 && unique[0] !== 0 ? "changed" : "", unique.length === 1 ? `${unique[0]}ms` : "inconsistent"),
    );
    row.append(heading, element("small", "host-note", notes.get(name) || ""));
    host.append(row);
  }
}
