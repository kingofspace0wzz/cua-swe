// Product entry point for the notebook cell-selection surface.
//
// Loads the notebook document from the same-origin /scene proxy (which the
// server forwards to the evaluator-owned scene feed), renders it, and wires up
// the Notebook selection controller. The scene document is the only place the
// concrete cell kinds and output DOM live; this shell never hard-codes them.
import { Notebook } from './notebook.mjs';

async function boot() {
  const params = new URLSearchParams(window.location.search);
  const payload = params.get('doc') || 'A';
  const root = document.getElementById('notebook');
  const notebook = new Notebook(root);
  window.__notebook = notebook;

  try {
    const res = await fetch(`/scene?doc=${encodeURIComponent(payload)}`, {
      cache: 'no-store'
    });
    if (!res.ok) {
      throw new Error(`scene feed responded ${res.status}`);
    }
    const doc = await res.json();
    notebook.render(doc);
    // Start with the document's active cell, defaulting to the last cell.
    const active =
      typeof doc.activeCell === 'number' ? doc.activeCell : notebook.widgets.length - 1;
    notebook.activeCellIndex = active;
    notebook._syncClasses();
    window.__ready = true;
  } catch (err) {
    window.__error = String(err && err.message ? err.message : err);
  }
}

boot();
