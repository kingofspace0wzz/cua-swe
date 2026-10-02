// Wires the Fleet Analytics Console together: builds the master and linked
// chart panels, installs the toolbox rubber-band handler on the master, and
// broadcasts each selection to the linked panels.
import { loadManifest, masterChart, linkedCharts } from './manifest.js';
import { ChartPanel } from './chartView.js';
import { broadcast } from './linkBroadcast.js';

export async function mountDashboard(root) {
  const { manifest } = await loadManifest();
  const title = document.querySelector('#ws-title');
  if (title) title.textContent = manifest.title;

  const master = masterChart(manifest);
  const linked = linkedCharts(manifest);

  const masterHost = root.querySelector('#master-host');
  const linkedHost = root.querySelector('#linked-host');
  masterHost.innerHTML = '';
  linkedHost.innerHTML = '';

  const masterPanel = new ChartPanel(master, document.createElement('div'));
  masterHost.appendChild(masterPanel.el);

  const linkedPanels = {};
  linked.forEach((chart) => {
    const el = document.createElement('div');
    linkedHost.appendChild(el);
    linkedPanels[chart.id] = new ChartPanel(chart, el);
  });

  // Apply a normalized rubber-band [lo, hi] drawn on the master: narrow the
  // master to that fraction of its own domain, then broadcast to the linked
  // panels so they frame the corresponding slice.
  function applyToolboxZoom(fraction) {
    const [d0, d1] = master.domain;
    const span = d1 - d0;
    masterPanel.setWindow([d0 + fraction[0] * span, d0 + fraction[1] * span]);
    const windows = broadcast(master, linked, fraction);
    linked.forEach((chart) => {
      linkedPanels[chart.id].setWindow(windows[chart.id]);
    });
  }

  function resetAll() {
    masterPanel.reset();
    linked.forEach((chart) => linkedPanels[chart.id].reset());
  }

  // Toolbox buttons.
  const zoomBtn = document.querySelector('#tb-zoom');
  const resetBtn = document.querySelector('#tb-reset');
  let armed = false;
  if (zoomBtn) {
    zoomBtn.addEventListener('click', () => {
      armed = !armed;
      zoomBtn.classList.toggle('armed', armed);
      masterPanel.el.classList.toggle('selecting', armed);
    });
  }
  if (resetBtn) resetBtn.addEventListener('click', resetAll);

  // Rubber-band selection on the master canvas: press-drag-release paints a
  // horizontal band and applies it as a fraction of the master domain.
  let dragStart = null;
  const canvas = masterPanel.canvas;
  const bandFraction = (clientX) => {
    const rect = canvas.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  };
  canvas.addEventListener('pointerdown', (e) => {
    if (!armed) return;
    dragStart = bandFraction(e.clientX);
  });
  canvas.addEventListener('pointerup', (e) => {
    if (!armed || dragStart == null) return;
    const end = bandFraction(e.clientX);
    const lo = Math.min(dragStart, end);
    const hi = Math.max(dragStart, end);
    dragStart = null;
    if (hi - lo > 0.02) applyToolboxZoom([lo, hi]);
  });

  // Scripted-gesture hook so an automated pass can drive the exact same code
  // path as a manual rubber-band. It applies the manifest's scripted window if
  // no explicit fraction is supplied.
  window.__runToolboxZoom = (fraction) => applyToolboxZoom(fraction || manifest.gesture.window);
  window.__scriptedGesture = manifest.gesture;
  window.__chartIds = manifest.charts.map((c) => c.id);
  window.__linkedIds = linked.map((c) => c.id);
  window.__masterId = master.id;

  document.body.dataset.ready = '1';
}
