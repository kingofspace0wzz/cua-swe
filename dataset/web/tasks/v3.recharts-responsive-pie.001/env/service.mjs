import http from 'node:http';
import crypto from 'node:crypto';

// Harness-owned board service for the Allocation Ring Studio.
//
// A board describes one allocation ring rendered inside a responsive card. The
// board hands the studio only the raw layout inputs -- card size, the legend's
// dock side and reserved extent, the gutter, the ring scale and hole ratio, and
// the allocation slices. It never tells the studio the settled plot box the ring
// must be sized to, nor the resulting radius or center. Those are facts the
// studio must resolve from the card once the browser has laid it out on screen.
//
// The service also renders, entirely on its own, the APPROVED reference image of
// how each board looked when it was signed off: a correctly sized ring centered
// in the settled plot area of that card. The reference ships only as pixels (an
// SVG data URI), never as a copyable radius/center number in the payload, so the
// studio and the agent see an image, not a constant.
//
// Profiles differ in card shape, dock side, reserve, and gutter so a handling
// that happens to look right on one profile is exposed on another.

const args = process.argv.slice(2);
const port = Number((args.includes('--port') ? args[args.indexOf('--port') + 1] : 0) || 4910);
const host = (args.includes('--host') ? args[args.indexOf('--host') + 1] : '') || '127.0.0.1';
const variant = process.env.CONTRACT_VARIANT || 'ledger';

function seal(seed) {
  return crypto.createHash('sha256').update('board-seal:' + seed).digest('hex').slice(0, 24);
}

// Layout constants that mirror the studio's own card CSS. The header is a fixed
// strip; the card body pads by the gutter and lays the plot area beside (right
// dock) or above (bottom dock) the legend rail, which reserves a fixed extent.
const HEADER = 30;

function settledPlot(board) {
  const bodyW = board.card.width - board.gutter * 2;
  const bodyH = board.card.height - HEADER - board.gutter * 2;
  if (board.legend.dock === 'right') {
    return { w: bodyW - board.legend.reserve, h: bodyH };
  }
  if (board.legend.dock === 'bottom') {
    return { w: bodyW, h: bodyH - board.legend.reserve };
  }
  return { w: bodyW, h: bodyH };
}

function referenceSVG(board) {
  const p = settledPlot(board);
  const half = Math.min(p.w, p.h) / 2;
  const outer = half * board.ringScale;
  const inner = outer * board.holeRatio;
  // Center of the settled plot area, expressed in card coordinates.
  const plotLeft = board.gutter;
  const plotTop = HEADER + board.gutter;
  const cx = plotLeft + p.w / 2;
  const cy = plotTop + p.h / 2;
  const total = board.slices.reduce((a, s) => a + s.value, 0) || 1;
  let acc = -Math.PI / 2;
  const arcs = board.slices.map((s) => {
    const sweep = (s.value / total) * Math.PI * 2;
    const a = { start: acc, end: acc + sweep, color: s.color };
    acc += sweep;
    return a;
  });
  const wedge = (a) => {
    const x0 = cx + outer * Math.cos(a.start);
    const y0 = cy + outer * Math.sin(a.start);
    const x1 = cx + outer * Math.cos(a.end);
    const y1 = cy + outer * Math.sin(a.end);
    const large = a.end - a.start > Math.PI ? 1 : 0;
    return `<path d="M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} A ${outer} ${outer} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z" fill="${a.color}"/>`;
  };
  const legendRect =
    board.legend.dock === 'right'
      ? `<rect x="${board.card.width - board.gutter - board.legend.reserve}" y="${plotTop}" width="${board.legend.reserve}" height="${p.h}" fill="#f2f5fa"/>`
      : board.legend.dock === 'bottom'
      ? `<rect x="${plotLeft}" y="${plotTop + p.h}" width="${p.w}" height="${board.legend.reserve}" fill="#f2f5fa"/>`
      : '';
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${board.card.width}" height="${board.card.height}" viewBox="0 0 ${board.card.width} ${board.card.height}">` +
    `<rect width="100%" height="100%" fill="#fbfcfe"/>` +
    `<rect x="0" y="0" width="${board.card.width}" height="${HEADER}" fill="#ffffff"/>` +
    `<line x1="0" y1="${HEADER}" x2="${board.card.width}" y2="${HEADER}" stroke="#dfe4ea"/>` +
    legendRect +
    arcs.map(wedge).join('') +
    `<circle cx="${cx}" cy="${cy}" r="${inner}" fill="#fbfcfe"/>` +
    `</svg>`;
  return 'data:image/svg+xml;base64,' + Buffer.from(svg).toString('base64');
}

// Each variant is a distinct board with its own slices, ring scale, and hole
// ratio, and its own set of four profiles. Profiles vary the card shape, dock
// side, reserve, and gutter. No profile records the settled plot box or radius.
const VARIANTS = {
  ledger: {
    title: 'Endowment Allocation',
    ringScale: 0.86,
    holeRatio: 0.52,
    margin: 4,
    slices: [
      { label: 'Public Equity', value: 38, color: '#2f6fed' },
      { label: 'Fixed Income', value: 24, color: '#37b6a6' },
      { label: 'Private Markets', value: 21, color: '#f2a23c' },
      { label: 'Real Assets', value: 11, color: '#c05fd0' },
      { label: 'Cash', value: 6, color: '#8a94a6' },
    ],
    profiles: {
      widescreen: { card: { width: 520, height: 300 }, legend: { dock: 'none', reserve: 0 }, gutter: 18 },
      sidebar: { card: { width: 460, height: 300 }, legend: { dock: 'right', reserve: 150 }, gutter: 16 },
      stacked: { card: { width: 360, height: 340 }, legend: { dock: 'bottom', reserve: 96 }, gutter: 14 },
      compact: { card: { width: 320, height: 300 }, legend: { dock: 'right', reserve: 138 }, gutter: 12 },
    },
    notes: {
      widescreen: 'Widescreen board: the legend sits inline, so the ring has the full card body.',
      sidebar: 'Sidebar board: the legend is docked to the right of the ring.',
      stacked: 'Stacked board: the legend runs along the bottom under the ring.',
      compact: 'Compact board: a narrow card with the legend docked to the right.',
    },
  },
  pension: {
    title: 'Pension Reserve Mix',
    ringScale: 0.78,
    holeRatio: 0.46,
    margin: 4,
    slices: [
      { label: 'Domestic Bonds', value: 33, color: '#3b82c4' },
      { label: 'Global Equity', value: 29, color: '#e0663f' },
      { label: 'Infrastructure', value: 18, color: '#6bbf59' },
      { label: 'Hedge', value: 12, color: '#b07fd4' },
      { label: 'Liquidity', value: 8, color: '#9aa3b2' },
    ],
    profiles: {
      widescreen: { card: { width: 540, height: 320 }, legend: { dock: 'none', reserve: 0 }, gutter: 20 },
      sidebar: { card: { width: 480, height: 300 }, legend: { dock: 'right', reserve: 168 }, gutter: 18 },
      stacked: { card: { width: 380, height: 360 }, legend: { dock: 'bottom', reserve: 112 }, gutter: 16 },
      compact: { card: { width: 300, height: 280 }, legend: { dock: 'right', reserve: 126 }, gutter: 10 },
    },
    notes: {
      widescreen: 'Widescreen board: the legend sits inline, so the ring has the full card body.',
      sidebar: 'Sidebar board: the legend is docked to the right of the ring.',
      stacked: 'Stacked board: the legend runs along the bottom under the ring.',
      compact: 'Compact board: a narrow card with the legend docked to the right.',
    },
  },
  sovereign: {
    title: 'Sovereign Fund Split',
    ringScale: 0.9,
    holeRatio: 0.58,
    margin: 4,
    slices: [
      { label: 'Equities', value: 44, color: '#2563c9' },
      { label: 'Rates', value: 22, color: '#2fa8a0' },
      { label: 'Credit', value: 17, color: '#e6a12e' },
      { label: 'Alts', value: 17, color: '#a763c9' },
    ],
    profiles: {
      widescreen: { card: { width: 560, height: 300 }, legend: { dock: 'none', reserve: 0 }, gutter: 22 },
      sidebar: { card: { width: 500, height: 320 }, legend: { dock: 'right', reserve: 182 }, gutter: 20 },
      stacked: { card: { width: 400, height: 380 }, legend: { dock: 'bottom', reserve: 124 }, gutter: 18 },
      compact: { card: { width: 340, height: 300 }, legend: { dock: 'right', reserve: 150 }, gutter: 14 },
    },
    notes: {
      widescreen: 'Widescreen board: the legend sits inline, so the ring has the full card body.',
      sidebar: 'Sidebar board: the legend is docked to the right of the ring.',
      stacked: 'Stacked board: the legend runs along the bottom under the ring.',
      compact: 'Compact board: a narrow card with the legend docked to the right.',
    },
  },
};

const def = VARIANTS[variant] || VARIANTS.ledger;
const token = seal(variant);

function boardFor(profile) {
  const prof = def.profiles[profile] || def.profiles.widescreen;
  const board = {
    title: def.title,
    note: def.notes[profile] || '',
    card: prof.card,
    legend: prof.legend,
    gutter: prof.gutter,
    ringScale: def.ringScale,
    holeRatio: def.holeRatio,
    margin: def.margin,
    slices: def.slices,
  };
  board.reference = referenceSVG(board);
  return board;
}

http.createServer((req, res) => {
  res.setHeader('content-type', 'application/json');
  res.setHeader('x-board-seal', token);
  const url = new URL(req.url, 'http://x');
  if (url.pathname === '/health') { res.end('{"ok":true}'); return; }
  if (url.pathname === '/studio/board') {
    const profile = url.searchParams.get('profile') || 'widescreen';
    res.end(JSON.stringify(boardFor(profile)));
    return;
  }
  res.statusCode = 404; res.end('{"error":"not found"}');
}).listen(port, host);
