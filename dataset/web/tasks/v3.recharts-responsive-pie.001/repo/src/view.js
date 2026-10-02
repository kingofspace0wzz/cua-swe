// Live renderer for the Allocation Ring Studio.
//
// Given a board, this builds the card (via cardLayout), then keeps the ring in
// sync with the card's on-screen size using a ResizeObserver. Whenever the
// observed element reports a size, the ring is sized from that measured box and
// painted onto the plot canvas, and a read-out is published so the rest of the
// studio (and the header chrome) can show where the ring landed.
//
// The ring is always painted onto the plot canvas, which fills the plot area.
// The measured box the observer reports is what sizes the ring; picking the
// element to observe is the one wiring decision this file makes.
import { buildCard } from './cardLayout.js';
import { boxFromRect, sliceArcs, ringFits } from './ringGeometry.js';
import { resolveRing } from './ringResolver.js';

export function mountBoard(host, board) {
  const parts = buildCard(host, board);
  const { card, plot, canvas } = parts;
  const ctx = canvas.getContext('2d');

  function readout(ring, plotW, plotH) {
    const fits = ringFits(ring, plotW, plotH, board.margin);
    const strip = document.getElementById('live-readout');
    if (strip) {
      strip.dataset.cx = String(Math.round(ring.cx));
      strip.dataset.cy = String(Math.round(ring.cy));
      strip.dataset.outer = String(Math.round(ring.outer));
      strip.dataset.plotw = String(Math.round(plotW));
      strip.dataset.ploth = String(Math.round(plotH));
      strip.dataset.fits = fits ? '1' : '0';
      strip.textContent =
        `ring r=${Math.round(ring.outer)}px  center=(${Math.round(ring.cx)}, ${Math.round(ring.cy)})  ` +
        `plot ${Math.round(plotW)}x${Math.round(plotH)}  ${fits ? 'within frame' : 'overflowing frame'}`;
    }
  }

  function paint(measuredBox) {
    const pr = plot.getBoundingClientRect();
    const plotW = pr.width;
    const plotH = pr.height;
    canvas.width = Math.max(1, Math.round(plotW));
    canvas.height = Math.max(1, Math.round(plotH));
    canvas.style.width = plotW + 'px';
    canvas.style.height = plotH + 'px';
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Resolve the ring from the measured box, then paint it centered on the
    // plot canvas that holds it. resolveRing owns how the measured box becomes
    // the drawable frame the ring is sized to.
    const sized = resolveRing(measuredBox, board);
    const ring = { cx: plotW / 2, cy: plotH / 2, outer: sized.outer, inner: sized.inner };

    const arcs = sliceArcs(board.slices.map((s) => s.value));
    arcs.forEach((arc, i) => {
      ctx.beginPath();
      ctx.moveTo(ring.cx, ring.cy);
      ctx.arc(ring.cx, ring.cy, ring.outer, arc.start, arc.end);
      ctx.closePath();
      ctx.fillStyle = board.slices[i].color;
      ctx.fill();
    });
    // Punch the donut hole.
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath();
    ctx.arc(ring.cx, ring.cy, ring.inner, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalCompositeOperation = 'source-over';

    readout(ring, plotW, plotH);
  }

  // Keep the ring synced to the card's live size. The observed element's
  // reported content box is the box the ring is sized from.
  const observed = card;
  const ro = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const box = boxFromRect(entry.target.getBoundingClientRect(), plot);
      paint(box);
    }
  });
  ro.observe(observed);

  // Paint once immediately so the ring is present before the first observer
  // callback settles.
  paint(boxFromRect(observed.getBoundingClientRect(), plot));

  return { ...parts, repaint: () => paint(boxFromRect(observed.getBoundingClientRect(), plot)), disconnect: () => ro.disconnect() };
}
