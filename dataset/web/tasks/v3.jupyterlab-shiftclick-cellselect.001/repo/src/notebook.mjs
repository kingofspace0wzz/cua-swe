// Notebook product surface.
//
// This is an authored, minimal reproduction of JupyterLab's notebook cell
// selection surface. It renders the cells of a notebook document and owns the
// Shift-click cell-range-selection gesture in exactly the way JupyterLab's
// `Notebook._evtMouseDown` does. The bug reproduced here is
// jupyterlab/jupyterlab#19242 / PR #19243: after selecting text inside a code
// editor, Shift-clicking another cell's prompt no longer extends the cell
// range selection.
//
// The notebook DOCUMENT (which cells exist, their kinds, and the DOM of their
// outputs — including outputs that attach an open shadow root the way widget
// libraries such as Panel or Bokeh do) is delivered ONLY by the evaluator-owned
// scene feed. This source builds the cell chrome and owns the selection policy,
// but it never enumerates which output structures a real notebook can contain.

const NB_CELL_CLASS = 'jp-Cell';

export class Notebook {
  constructor(root) {
    this.root = root;
    this.node = root;
    /** @type {Cell[]} */
    this.widgets = [];
    this.activeCellIndex = -1;
    this._selected = new Set();
    this.node.addEventListener('mousedown', this, true);
  }

  /**
   * Render a notebook document delivered by the scene feed.
   * @param {{cells: Array}} doc
   */
  render(doc) {
    this.node.innerHTML = '';
    this.widgets = [];
    this._selected = new Set();
    this.activeCellIndex = -1;
    for (const spec of doc.cells) {
      const cell = new Cell(spec);
      this.widgets.push(cell);
      this.node.appendChild(cell.node);
    }
  }

  handleEvent(event) {
    if (event.type === 'mousedown') {
      this._evtMouseDown(event);
    }
  }

  /** Find index of the cell containing `node`, or -1. */
  _findCell(node) {
    let n = node;
    while (n && n !== this.node) {
      if (n.classList && n.classList.contains(NB_CELL_CLASS)) {
        const idx = this.widgets.findIndex(c => c.node === n);
        if (idx !== -1) {
          return idx;
        }
      }
      n = n.parentElement;
    }
    return -1;
  }

  _targetArea(node, index) {
    if (index === -1) {
      return 'notebook';
    }
    let n = node;
    while (n && n !== this.node) {
      if (n.classList && n.classList.contains('jp-InputArea-prompt')) {
        return 'prompt';
      }
      if (n.classList && n.classList.contains('jp-InputArea-editor')) {
        return 'input';
      }
      n = n.parentElement;
    }
    return 'cell';
  }

  isSelectedOrActive(cell) {
    const idx = this.widgets.indexOf(cell);
    return idx === this.activeCellIndex || this._selected.has(idx);
  }

  deselectAll() {
    this._selected.clear();
    this._syncClasses();
  }

  /** Extend a contiguous cell selection from the active cell to `index`. */
  extendContiguousSelectionTo(index) {
    const anchor = this.activeCellIndex === -1 ? index : this.activeCellIndex;
    const lo = Math.min(anchor, index);
    const hi = Math.max(anchor, index);
    this._selected = new Set();
    for (let i = lo; i <= hi; i++) {
      this._selected.add(i);
    }
    this.activeCellIndex = index;
    this._syncClasses();
  }

  _syncClasses() {
    this.widgets.forEach((cell, i) => {
      cell.node.classList.toggle('jp-mod-selected', this._selected.has(i) || i === this.activeCellIndex);
      cell.node.classList.toggle('jp-mod-active', i === this.activeCellIndex);
    });
  }

  _evtMouseDown(event) {
    const button = event.button;
    const shiftKey = event.shiftKey;
    const target = event.target;
    const index = this._findCell(target);
    const widget = index === -1 ? null : this.widgets[index];
    const targetArea = this._targetArea(target, index);

    if (targetArea === 'notebook') {
      this.deselectAll();
    } else if (targetArea === 'prompt' || targetArea === 'cell') {
      // We don't want to prevent the default selection behavior
      // if there is currently text selected.
      const hasSelection = (window.getSelection() ?? '').toString() !== '';
      if (
        button === 0 &&
        shiftKey &&
        !hasSelection &&
        !['INPUT', 'OPTION'].includes(target.tagName)
      ) {
        // Prevent browser selecting text in prompt or output
        event.preventDefault();

        // Shift-click - extend selection
        try {
          this.extendContiguousSelectionTo(index);
        } catch (e) {
          console.error(e);
          this.deselectAll();
          return;
        }
      } else if (button === 0 && !shiftKey) {
        if (!this.isSelectedOrActive(widget)) {
          this.deselectAll();
          this.activeCellIndex = index;
          this._syncClasses();
        }
      }
    }
  }

  /** Expose selection state for behavioral inspection. */
  selectionState() {
    return {
      active: this.activeCellIndex,
      selected: this.widgets.map((_, i) => this._selected.has(i) || i === this.activeCellIndex)
    };
  }
}

/**
 * A single notebook cell. Code cells own an editor and an output area; rendered
 * markdown cells own an editor and a rendered-input region. The exact output
 * DOM (including outputs that attach an open shadow root) is provided by the
 * scene feed and injected verbatim; this class only builds the cell chrome.
 */
class Cell {
  constructor(spec) {
    this.spec = spec;
    const node = document.createElement('div');
    node.className = `${NB_CELL_CLASS} jp-Cell-${spec.kind}`;
    node.dataset.cellId = spec.id;

    const input = document.createElement('div');
    input.className = 'jp-InputArea';

    const prompt = document.createElement('div');
    prompt.className = 'jp-InputArea-prompt';
    prompt.textContent = spec.prompt ?? '[ ]:';
    input.appendChild(prompt);

    if (spec.kind === 'markdown' && spec.rendered) {
      const rendered = document.createElement('div');
      rendered.className = 'jp-RenderedMarkdown jp-MarkdownOutput';
      rendered.innerHTML = spec.renderedHTML ?? '';
      input.appendChild(rendered);
      this.renderedInput = rendered;
    } else {
      const editor = document.createElement('div');
      editor.className = 'jp-InputArea-editor';
      editor.setAttribute('contenteditable', 'plaintext-only');
      editor.spellcheck = false;
      editor.textContent = spec.source ?? '';
      input.appendChild(editor);
      this.editor = editor;
    }

    node.appendChild(input);

    if (spec.kind === 'code' && spec.output) {
      const outputArea = document.createElement('div');
      outputArea.className = 'jp-OutputArea';
      if (spec.output.shadow) {
        // Widget-library style output: an open shadow root, as attached by
        // libraries such as Panel or Bokeh.
        const host = document.createElement('div');
        host.className = 'jp-OutputArea-output';
        const shadow = host.attachShadow({ mode: 'open' });
        shadow.innerHTML = spec.output.html ?? '';
        outputArea.appendChild(host);
        this.outputHost = host;
      } else {
        const out = document.createElement('div');
        out.className = 'jp-OutputArea-output';
        out.innerHTML = spec.output.html ?? '';
        outputArea.appendChild(out);
      }
      node.appendChild(outputArea);
      this.outputArea = outputArea;
    }

    this.node = node;
  }
}
