// Card layout for the Allocation Ring Studio.
//
// A board arrives with a card size, a dockable legend, and a gutter. This
// module builds the live card DOM for one board: an outer card, a header strip,
// a plot area that holds the drawn ring, and a legend rail that can be docked to
// the right or along the bottom (or hidden). The legend rail is a real flex
// sibling of the plot area, so once the browser lays the card out the plot area
// genuinely occupies less than the whole card whenever the legend is docked.
//
// The board decides the card size, dock side, legend reserve, and gutter. This
// module just realizes them as CSS; it does not compute the ring.

export function buildCard(host, board) {
  host.innerHTML = '';
  const card = document.createElement('div');
  card.className = 'ring-card';
  card.style.width = board.card.width + 'px';
  card.style.height = board.card.height + 'px';
  card.dataset.dock = board.legend.dock;

  const header = document.createElement('div');
  header.className = 'card-header';
  header.textContent = board.title;
  card.appendChild(header);

  const body = document.createElement('div');
  body.className = 'card-body';
  body.style.flexDirection = board.legend.dock === 'bottom' ? 'column' : 'row';
  body.style.padding = board.gutter + 'px';
  card.appendChild(body);

  const plot = document.createElement('div');
  plot.className = 'plot-area';
  plot.dataset.plot = '1';
  const canvas = document.createElement('canvas');
  canvas.className = 'ring-canvas';
  plot.appendChild(canvas);
  body.appendChild(plot);

  let legend = null;
  if (board.legend.dock !== 'none') {
    legend = document.createElement('div');
    legend.className = 'legend-rail';
    legend.dataset.dock = board.legend.dock;
    // The legend reserve is a real fixed extent along the dock axis. It is a
    // sibling of the plot area, so it takes this many pixels away from what the
    // plot area is left with.
    if (board.legend.dock === 'right') {
      legend.style.width = board.legend.reserve + 'px';
      legend.style.height = '100%';
    } else {
      legend.style.height = board.legend.reserve + 'px';
      legend.style.width = '100%';
    }
    board.slices.forEach((s) => {
      const row = document.createElement('div');
      row.className = 'legend-row';
      const sw = document.createElement('span');
      sw.className = 'swatch';
      sw.style.background = s.color;
      const lbl = document.createElement('span');
      lbl.className = 'legend-label';
      lbl.textContent = s.label;
      row.appendChild(sw);
      row.appendChild(lbl);
      legend.appendChild(row);
    });
    body.appendChild(legend);
  }

  host.appendChild(card);
  return { card, body, plot, legend, canvas };
}
