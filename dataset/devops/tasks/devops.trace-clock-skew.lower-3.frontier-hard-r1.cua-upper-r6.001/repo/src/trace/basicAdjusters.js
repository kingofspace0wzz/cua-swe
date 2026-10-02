export function dedupeSpans(spans) {
  const seen = new Set();
  return spans.filter((span) => {
    if (seen.has(span.id)) return false;
    seen.add(span.id);
    return true;
  });
}

export function sortSpans(spans) {
  return spans.slice().sort((left, right) =>
    left.startMs - right.startMs || left.id.localeCompare(right.id),
  );
}
