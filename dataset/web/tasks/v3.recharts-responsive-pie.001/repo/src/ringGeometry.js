// Ring geometry helpers for the Allocation Ring Studio.
//
// The studio draws a donut ("ring") of allocation slices inside a responsive
// card. A card is a flex container: it may reserve a strip of itself for a
// dockable legend, and it always keeps a small gutter of breathing room around
// its drawable area. The ring must be centered in, and sized to, whatever
// drawable area is actually left once the card has laid itself out on screen.
//
// This module offers two ways to describe a measured box and a couple of small
// primitives for turning a box into a ring. It does NOT decide which measured
// box is the right one to feed the ring; that is wired up in view.js from the
// element the studio chooses to observe.

// A measured box is {left, top, width, height} in card-local pixels.
export function boxFromRect(rect, host) {
  const h = host.getBoundingClientRect();
  return {
    left: rect.left - h.left,
    top: rect.top - h.top,
    width: rect.width,
    height: rect.height,
  };
}

// Turn a measured box into a ring: centered in the box, radius sized to the
// tighter half-extent scaled by the board's ring scale. Returns pixel center
// and outer/inner radius.
export function ringFromBox(box, ringScale, holeRatio) {
  const cx = box.left + box.width / 2;
  const cy = box.top + box.height / 2;
  const half = Math.min(box.width, box.height) / 2;
  const outer = Math.max(0, half * ringScale);
  const inner = outer * holeRatio;
  return { cx, cy, outer, inner };
}

// Slice geometry: cumulative angles from a list of weighted values, starting at
// twelve o'clock and sweeping clockwise. Returns arcs with start/end radians.
export function sliceArcs(values) {
  const total = values.reduce((a, v) => a + v, 0) || 1;
  let acc = -Math.PI / 2;
  return values.map((v) => {
    const sweep = (v / total) * Math.PI * 2;
    const arc = { start: acc, end: acc + sweep };
    acc += sweep;
    return arc;
  });
}

// Whether a ring of the given center/outer radius stays inside a frame of the
// given width/height with a required margin. Used by the view to annotate the
// live read-out; it does not choose geometry.
export function ringFits(ring, frameW, frameH, margin) {
  return (
    ring.cx - ring.outer >= margin &&
    ring.cy - ring.outer >= margin &&
    ring.cx + ring.outer <= frameW - margin &&
    ring.cy + ring.outer <= frameH - margin
  );
}
