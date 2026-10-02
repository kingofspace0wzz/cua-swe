import {clear, element} from "./components.js";

export function renderChart(snapshot) {
  const chart = document.querySelector('[data-test="chart"]');
  clear(chart);
  const timeAxis = document.querySelector('[data-test="time-axis"]');
  clear(timeAxis);
  const maximum = Math.max(...snapshot.points.map((point) => point.value), 1);
  for (const point of snapshot.points) {
    const column = element("div", "point");
    column.dataset.pointId = point.id;
    column.dataset.time = String(point.time);
    column.dataset.value = String(point.value);
    column.style.height = `${Math.max(2, (point.value / maximum) * 100)}%`;
    column.title = `${point.time}s · ${point.formatted}`;
    chart.append(column);
    const tick = element("span", "time-tick");
    tick.textContent = `${point.time}s`;
    timeAxis.append(tick);
  }
}
