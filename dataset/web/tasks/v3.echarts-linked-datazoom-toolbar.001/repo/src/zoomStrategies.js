// Reusable primitives for turning a rubber-band selection on the master chart
// into a concrete data-unit window on another chart.
//
// A rubber-band selection arrives as a normalized fraction pair [lo, hi] of the
// master chart's own domain, together with the master's data-unit window and
// the master's selected sample-index range. Each primitive is one candidate way
// to project that selection onto a target chart; none is privileged here.

// Project the master's normalized fraction pair onto the target chart's own
// domain, yielding a data-unit window sized to the target's extent.
export function byDomainFraction(sel, target) {
  const [d0, d1] = target.domain;
  const span = d1 - d0;
  return [d0 + sel.fraction[0] * span, d0 + sel.fraction[1] * span];
}

// Reuse the master's data-unit window verbatim on the target chart.
export function byRawWindow(sel, _target) {
  return [sel.dataWindow[0], sel.dataWindow[1]];
}

// Reuse the master's selected sample-index range on the target chart, reading
// the target's own points at those indices to form a data-unit window.
export function byRawIndex(sel, target) {
  const pts = target.points;
  const lo = Math.max(0, Math.min(sel.indexRange[0], pts.length - 1));
  const hi = Math.max(0, Math.min(sel.indexRange[1], pts.length - 1));
  return [pts[lo][0], pts[hi][0]];
}

export const STRATEGIES = {
  domainFraction: byDomainFraction,
  rawWindow: byRawWindow,
  rawIndex: byRawIndex,
};
