// Renders one chart panel of the Fleet Analytics Console onto a canvas and
// keeps a visible window read-out in the panel header.
//
// A chart panel shows a metric plotted across the chart's own x-domain. The
// panel remembers the visible x-window it is currently framed to. When the
// window narrows, the canvas redraws the same series confined to that window
// and the header read-out prints the framed interval so an analyst can see
// exactly which slice each chart is showing.

function niceNum(v) {
  return Math.round(v * 100) / 100;
}

export class ChartPanel {
  constructor(chart, rootEl) {
    this.chart = chart;
    this.window = chart.domain.slice(); // full domain to begin with
    this.el = rootEl;
    this.el.className = 'panel ' + (chart.role === 'master' ? 'panel-master' : 'panel-linked');
    this.el.dataset.chart = chart.id;
    this.el.innerHTML = `
      <div class="panel-head">
        <span class="panel-label">${chart.label}</span>
        <span class="panel-window"
              data-chart-window="${chart.id}"
              data-lo="" data-hi=""></span>
      </div>
      <canvas class="panel-canvas" width="300" height="150"></canvas>`;
    this.canvas = this.el.querySelector('canvas');
    this.readout = this.el.querySelector('.panel-window');
    this.draw();
  }

  setWindow(win) {
    // Clamp to the chart's own domain so a projected window never runs past the
    // data this chart actually holds.
    const [d0, d1] = this.chart.domain;
    const lo = Math.max(d0, Math.min(win[0], win[1]));
    const hi = Math.min(d1, Math.max(win[0], win[1]));
    this.window = [lo, hi];
    this.draw();
  }

  reset() {
    this.window = this.chart.domain.slice();
    this.draw();
  }

  draw() {
    const ctx = this.canvas.getContext('2d');
    const W = this.canvas.width;
    const H = this.canvas.height;
    ctx.clearRect(0, 0, W, H);
    const [lo, hi] = this.window;
    const span = hi - lo || 1;
    const pts = this.chart.points.filter((p) => p[0] >= lo - 1e-9 && p[0] <= hi + 1e-9);
    const ys = this.chart.points.map((p) => p[1]);
    const ymin = Math.min(...ys);
    const ymax = Math.max(...ys) || 1;
    const yspan = ymax - ymin || 1;
    ctx.strokeStyle = this.chart.role === 'master' ? '#1f6feb' : '#6e7781';
    ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach((p, i) => {
      const x = ((p[0] - lo) / span) * (W - 8) + 4;
      const y = H - 8 - ((p[1] - ymin) / yspan) * (H - 16);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
    // Update the read-out.
    this.readout.dataset.lo = String(niceNum(lo));
    this.readout.dataset.hi = String(niceNum(hi));
    this.readout.textContent = `${niceNum(lo)} \u2013 ${niceNum(hi)}`;
  }
}
