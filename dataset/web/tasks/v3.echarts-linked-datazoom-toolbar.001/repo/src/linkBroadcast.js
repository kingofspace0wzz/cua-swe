// Broadcasts a master rubber-band selection to the linked charts.
//
// When the analyst rubber-bands a sub-window on the master chart, the console
// must bring every linked chart to the window that frames the corresponding
// slice of the shared story on that chart. This module turns the master
// gesture into a selection descriptor and then decides, per linked chart, the
// data-unit window that chart should show.
import { STRATEGIES } from './zoomStrategies.js';

// Build the selection descriptor from the normalized rubber-band on the master.
// It carries the fraction of the master domain that was framed, the master's
// own data-unit window, and the master's selected sample-index range, so the
// broadcast can be expressed in whichever of those terms fits.
export function describeSelection(master, fraction) {
  const [d0, d1] = master.domain;
  const span = d1 - d0;
  const dataWindow = [d0 + fraction[0] * span, d0 + fraction[1] * span];
  const n = master.points.length;
  const indexRange = [
    Math.round(fraction[0] * (n - 1)),
    Math.round(fraction[1] * (n - 1)),
  ];
  return { fraction: fraction.slice(), dataWindow, indexRange };
}

// Resolve the data-unit window a single linked chart should show for a
// selection. The strategy primitives in ./zoomStrategies.js are all available;
// this handler currently reuses the master's own framed data window directly,
// which is the window the analyst saw the rubber-band cover on the master.
export function resolveLinkedWindow(sel, chart) {
  return STRATEGIES.rawWindow(sel, chart);
}

// Compute the data-unit window each linked chart should show.
export function broadcast(master, linked, fraction) {
  const sel = describeSelection(master, fraction);
  const out = {};
  linked.forEach((chart) => {
    out[chart.id] = resolveLinkedWindow(sel, chart);
  });
  return out;
}
