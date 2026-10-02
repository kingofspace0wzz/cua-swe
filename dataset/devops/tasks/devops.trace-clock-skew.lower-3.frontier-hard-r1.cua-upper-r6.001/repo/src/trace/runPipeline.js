export function runPipeline(rawSpans, adjusters) {
  let spans = rawSpans.map((span) => ({ ...span }));
  const annotations = [];
  for (const adjuster of adjusters) {
    const before = new Map(spans.map((span) => [span.id, span.startMs]));
    spans = adjuster.apply(spans);
    for (const span of spans) {
      const prior = before.get(span.id);
      if (prior !== undefined && prior !== span.startMs) {
        annotations.push({
          spanId: span.id,
          adjuster: adjuster.name,
          shiftMs: span.startMs - prior,
        });
      }
    }
  }
  return { spans, annotations };
}
