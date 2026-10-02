// Evaluator-owned scene feed for the notebook cell-selection task
// (jupyterlab/jupyterlab#19243).
//
// This feed delivers the NOTEBOOK DOCUMENT for each protected payload: which
// cells exist, their kind (code / rendered markdown), the editor source, and
// the concrete OUTPUT DOM — including outputs that attach an open shadow root
// the way widget libraries such as Panel or Bokeh do. The decisive fact that
// the notebook must treat output areas AND rendered-markdown inputs (including
// shadow-rooted outputs) as browser-owned text regions, while a code editor is
// NOT such a region, is exercised only through the running document delivered
// here. It is never present in agent-visible repo/ source, which owns only the
// selection gesture and the generic cell chrome.
import http from 'node:http';

function arg(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const host = arg('--host', '127.0.0.1');
const port = Number(arg('--port', '4270'));

// Protected notebook documents. Each is a three-cell notebook. The verifier
// drives a text selection and a Shift-click and asserts the resulting cell
// selection against the correct region-aware policy.
const DOCS = {
  // P1 - selection anchored in a CODE EDITOR, then Shift-click a later cell's
  // prompt. A code editor is NOT a browser-owned text region, so the notebook
  // MUST extend the cell range selection.
  A: {
    scenario: 'editor-then-prompt',
    activeCell: 0,
    cells: [
      { id: 'c0', kind: 'code', prompt: '[1]:', source: 'first value here' },
      { id: 'c1', kind: 'code', prompt: '[2]:', source: 'second value here' },
      { id: 'c2', kind: 'code', prompt: '[3]:', source: 'third value here' }
    ]
  },
  // P2 - selection anchored in a plain OUTPUT AREA, then Shift-click within the
  // same output. Output is a browser-owned text region, so the notebook must
  // leave the gesture to the browser and NOT turn it into a cell selection.
  B: {
    scenario: 'output-then-output',
    activeCell: 2,
    cells: [
      {
        id: 'c0',
        kind: 'code',
        prompt: '[1]:',
        source: 'print(long_text)',
        output: { shadow: false, html: '<p id="out-first">alpha beta gamma</p><p id="out-second">delta epsilon zeta</p>' }
      },
      { id: 'c1', kind: 'code', prompt: '[2]:', source: '1 + 1' },
      { id: 'c2', kind: 'code', prompt: '[3]:', source: '2 + 2' }
    ]
  },
  // P3 - selection anchored in a RENDERED MARKDOWN input, then Shift-click a
  // later cell's prompt. A rendered markdown input is a browser-owned text
  // region, so the notebook must NOT extend the cell selection.
  C: {
    scenario: 'markdown-then-prompt',
    activeCell: 2,
    cells: [
      {
        id: 'c0',
        kind: 'markdown',
        rendered: true,
        prompt: '',
        renderedHTML: '<p id="md-first">alpha beta gamma</p><p id="md-second">delta epsilon zeta</p>'
      },
      { id: 'c1', kind: 'code', prompt: '[1]:', source: '1 + 1' },
      { id: 'c2', kind: 'code', prompt: '[2]:', source: '2 + 2' }
    ]
  },
  // P4 - selection anchored inside a SHADOW-DOM OUTPUT (open shadow root as
  // attached by widget libraries), then Shift-click within the same output.
  // The output is a browser-owned text region even though it lives inside a
  // shadow root, so the notebook must NOT extend the cell selection. Detecting
  // this requires traversing out of the shadow root.
  D: {
    scenario: 'shadow-output-then-output',
    activeCell: 2,
    cells: [
      {
        id: 'c0',
        kind: 'code',
        prompt: '[1]:',
        source: 'HTML(widget)',
        output: { shadow: true, html: '<p id="shadow-first">alpha beta gamma</p><p id="shadow-second">delta epsilon zeta</p>' }
      },
      { id: 'c1', kind: 'code', prompt: '[2]:', source: '1 + 1' },
      { id: 'c2', kind: 'code', prompt: '[3]:', source: '2 + 2' }
    ]
  },
  // P5 - selection anchored in an OUTPUT AREA, then Shift-click a DIFFERENT
  // cell's PROMPT (cell chrome, not a text region). Because the click lands
  // outside any browser-owned text region, the notebook MUST extend the cell
  // range selection even though a text selection exists in an output. This is
  // the case a coarse "anything outside a code editor is a text selection"
  // repair gets wrong: the decisive rule is that BOTH the anchor and the
  // clicked region must be browser-owned text regions.
  E: {
    scenario: 'output-then-other-prompt',
    activeCell: 0,
    cells: [
      {
        id: 'c0',
        kind: 'code',
        prompt: '[1]:',
        source: 'print(long_text)',
        output: { shadow: false, html: '<p id="out-first">alpha beta gamma</p><p id="out-second">delta epsilon zeta</p>' }
      },
      { id: 'c1', kind: 'code', prompt: '[2]:', source: '1 + 1' },
      { id: 'c2', kind: 'code', prompt: '[3]:', source: '2 + 2' }
    ]
  }
};

http
  .createServer((request, response) => {
    const url = new URL(request.url, `http://${request.headers.host}`);
    if (url.pathname === '/health') {
      response.writeHead(200, { 'content-type': 'text/plain' });
      response.end('ok');
      return;
    }
    if (url.pathname === '/scene') {
      const key = (url.searchParams.get('doc') || 'A').toUpperCase();
      const doc = DOCS[key] || DOCS.A;
      const body = Buffer.from(JSON.stringify(doc));
      response.writeHead(200, {
        'content-type': 'application/json; charset=utf-8',
        'content-length': body.length,
        'cache-control': 'no-store'
      });
      response.end(body);
      return;
    }
    response.writeHead(404, { 'content-type': 'text/plain' });
    response.end('not found');
  })
  .listen(port, host, () => {
    process.stdout.write(`scene feed listening on http://${host}:${port}\n`);
  });
