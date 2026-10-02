// Field Log Composer editing surface, driven by a real Slate editor.
//
// The log body is a Slate document (one paragraph block per entry). Every
// edit runs through Slate core (Editor.insertSoftBreak, Editor.insertBreak,
// Transforms.insertText) on an editor produced by slate-dom.withDOM. A
// minimal vanilla renderer paints editor.children into the contenteditable
// surface and registers the slate-dom node/element maps so that
// DOMEditor.toDOMRange resolves the live caret box straight from Slate.

import { createEditor, Editor, Transforms, Node as SlateNode } from 'slate';
import {
  DOMEditor,
  withDOM,
  EDITOR_TO_ELEMENT,
  EDITOR_TO_WINDOW,
  EDITOR_TO_KEY_TO_ELEMENT,
  ELEMENT_TO_NODE,
  NODE_TO_ELEMENT,
  NODE_TO_INDEX,
  NODE_TO_PARENT,
} from 'slate-dom';
import { onCaretMoved } from './scrollController.js';

const ZERO_WIDTH = String.fromCharCode(65279);
const NEWLINE = String.fromCharCode(10);

let editor = null;
let bodyEl = null;

export function getBodyEl() { return bodyEl; }
export function getEditor() { return editor; }

function docFromBody(blocks) {
  return blocks.map((text) => ({ type: "paragraph", children: [{ text: String(text) }] }));
}

function render() {
  const keyToEl = EDITOR_TO_KEY_TO_ELEMENT.get(editor);
  const savedScrollTop = bodyEl.scrollTop;
  bodyEl.textContent = "";
  NODE_TO_INDEX.set(editor, 0);
  NODE_TO_PARENT.set(editor, editor);
  editor.children.forEach((block, bi) => {
    const p = document.createElement("p");
    p.className = "log-block";
    p.setAttribute("data-slate-node", "element");
    NODE_TO_INDEX.set(block, bi);
    NODE_TO_PARENT.set(block, editor);
    NODE_TO_ELEMENT.set(block, p);
    ELEMENT_TO_NODE.set(p, block);
    keyToEl.set(DOMEditor.findKey(editor, block), p);
    block.children.forEach((leaf, li) => {
      NODE_TO_INDEX.set(leaf, li);
      NODE_TO_PARENT.set(leaf, block);
      const leafSpan = document.createElement("span");
      leafSpan.setAttribute("data-slate-node", "text");
      NODE_TO_ELEMENT.set(leaf, leafSpan);
      ELEMENT_TO_NODE.set(leafSpan, leaf);
      keyToEl.set(DOMEditor.findKey(editor, leaf), leafSpan);
      const str = document.createElement("span");
      const text = leaf.text != null ? String(leaf.text) : "";
      if (text.length === 0) {
        str.setAttribute("data-slate-zero-width", "n");
        str.setAttribute("data-slate-length", "0");
        str.textContent = ZERO_WIDTH;
      } else {
        str.setAttribute("data-slate-string", "true");
        str.setAttribute("data-slate-length", String(text.length));
        // A leaf whose text ends in a newline needs an extra trailing newline in
        // the DOM so the final (empty) visual line has a measurable box and the
        // caret can rest on it; data-slate-length preserves the true length for
        // slate-dom offset math.
        str.textContent = text.charAt(text.length - 1) === NEWLINE ? text + NEWLINE : text;
      }
      leafSpan.appendChild(str);
      p.appendChild(leafSpan);
    });
    bodyEl.appendChild(p);
  });
  // Re-rendering rebuilds the block DOM; keep the surface where the writer left
  // it so a caret move does not itself jump the scroll (the follow controller
  // decides any repositioning). Force a layout read so the freshly rebuilt
  // content height is known before we restore, otherwise the browser clamps
  // the assignment against a stale (zero) scroll range.
  void bodyEl.scrollHeight;
  bodyEl.scrollTop = savedScrollTop;
  syncDOMSelection();
}

// Mirror the Slate selection into the native DOM selection so focus and caret
// measurement track the editor state (the job slate-react does on render).
function syncDOMSelection() {
  if (!editor || !editor.selection) return;
  let domRange;
  try {
    domRange = DOMEditor.toDOMRange(editor, editor.selection);
  } catch (err) {
    return;
  }
  const sel = window.getSelection();
  if (!sel) return;
  const saved = bodyEl.scrollTop;
  sel.removeAllRanges();
  sel.addRange(domRange);
  // Restoring the DOM selection can nudge the scroll; keep the surface put.
  void bodyEl.scrollHeight;
  bodyEl.scrollTop = saved;
}


export function mountLog(body, blocks) {
  bodyEl = body;
  editor = withDOM(createEditor());
  // The field log wants a true in-paragraph soft line break, so override the
  // Slate default (which splits the block) to insert a newline into the
  // current text, matching the upstream Slate soft-break pattern.
  editor.insertSoftBreak = () => {
    Transforms.insertText(editor, NEWLINE);
  };
  editor.children = docFromBody(blocks);
  editor.selection = null;
  EDITOR_TO_ELEMENT.set(editor, bodyEl);
  ELEMENT_TO_NODE.set(bodyEl, editor);
  EDITOR_TO_WINDOW.set(editor, window);
  EDITOR_TO_KEY_TO_ELEMENT.set(editor, new WeakMap());
  bodyEl.setAttribute("data-slate-editor", "true");
  bodyEl.setAttribute("data-slate-node", "value");
  editor.onChange = () => { render(); syncCaretGeometry(); };
  render();
}

export function placeCaretInBlock(index) {
  const path = [index];
  if (!SlateNode.has(editor, path)) return;
  const point = Editor.end(editor, path);
  Transforms.select(editor, point);
  render();
  syncCaretGeometry();
}

export function syncCaretGeometry() {
  if (!editor || !editor.selection) return null;
  let domRange;
  try {
    domRange = DOMEditor.toDOMRange(editor, editor.selection);
  } catch (err) {
    return null;
  }
  const collapsed = domRange.cloneRange();
  collapsed.collapse(false);
  const rect = caretRect(collapsed);
  const bodyRect = bodyEl.getBoundingClientRect();
  const geom = {
    caretTop: rect.top - bodyRect.top + bodyEl.scrollTop,
    caretBottom: rect.bottom - bodyRect.top + bodyEl.scrollTop,
    caretTopViewport: rect.top - bodyRect.top,
    caretBottomViewport: rect.bottom - bodyRect.top,
  };
  bodyEl.dataset.caretTop = String(Math.round(geom.caretTop));
  bodyEl.dataset.caretBottom = String(Math.round(geom.caretBottom));
  bodyEl.dataset.caretTopViewport = String(Math.round(geom.caretTopViewport));
  bodyEl.dataset.caretBottomViewport = String(Math.round(geom.caretBottomViewport));
  bodyEl.dataset.scrollTop = String(Math.round(bodyEl.scrollTop));
  return geom;
}

function caretRect(range) {
  const rects = range.getClientRects();
  if (rects.length) return rects[rects.length - 1];
  const node = range.startContainer;
  if (node && node.nodeType === Node.TEXT_NODE && node.textContent.length) {
    const len = node.textContent.length;
    const off = Math.min(range.startOffset, len);
    const prevCh = off > 0 ? node.textContent.charAt(off - 1) : "";
    // When the caret sits just after a newline it begins a fresh visual line;
    // probing the previous character would report the old line, so probe the
    // character ahead (the trailing newline we render for the empty line).
    if (prevCh === NEWLINE && off < len) {
      const fwd = document.createRange();
      fwd.setStart(node, off);
      fwd.setEnd(node, off + 1);
      const fr = fwd.getClientRects();
      if (fr.length) {
        const first = fr[0];
        return { top: first.top, bottom: first.bottom, left: first.left, right: first.left };
      }
    }
    const probe = document.createRange();
    probe.setStart(node, Math.max(0, off - 1));
    probe.setEnd(node, off);
    const pr = probe.getClientRects();
    if (pr.length) {
      const last = pr[pr.length - 1];
      return { top: last.top, bottom: last.bottom, left: last.right, right: last.right };
    }
  }
  const el = node && node.nodeType === Node.ELEMENT_NODE ? node : (node ? node.parentElement : null);
  if (el) {
    const er = el.getBoundingClientRect();
    return { top: er.bottom - 20, bottom: er.bottom, left: er.left, right: er.left };
  }
  return { top: 0, bottom: 0, left: 0, right: 0 };
}



export function scrollCaretToBottomEdge() {
  const geom = syncCaretGeometry();
  if (!geom) return;
  const margin = Number(bodyEl.dataset.safeMargin) || 0;
  const desiredBottomViewport = bodyEl.clientHeight - margin;
  const delta = geom.caretBottomViewport - desiredBottomViewport;
  const max = bodyEl.scrollHeight - bodyEl.clientHeight;
  bodyEl.scrollTop = Math.max(0, Math.min(max, bodyEl.scrollTop + delta));
  syncCaretGeometry();
}

export function insertSoftBreak() {
  if (!editor) return;
  Editor.insertSoftBreak(editor);
  syncCaretGeometry();
  // The caret has moved to a fresh line; the surface must be kept coherent so
  // the writer keeps seeing what they type.
  // (soft-break caret follow-up)
}

export function insertParagraphBreak() {
  if (!editor) return;
  Editor.insertBreak(editor);
  syncCaretGeometry();
  onCaretMoved(bodyEl, syncCaretGeometry);
}

export function insertText(ch) {
  if (!editor) return;
  Transforms.insertText(editor, ch);
  syncCaretGeometry();
  onCaretMoved(bodyEl, syncCaretGeometry);
}

export function bindKeys(body) {
  body.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && ev.shiftKey) {
      ev.preventDefault();
      insertSoftBreak();
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      insertParagraphBreak();
    }
  });
}


// Evidence, computed at runtime from the live objects, that the editing
// surface is a genuine Slate editor produced by slate + slate-dom (used by
// the framework gate; never a hard-coded flag).
export function frameworkProbe() {
  const ed = editor;
  return {
    isSlateEditor: !!(ed && Editor.isEditor(ed)),
    isDOMEditor: !!(ed && DOMEditor.hasDOMNode(ed, bodyEl)),
    slateApiPresent: typeof Editor.insertSoftBreak === "function" && typeof Transforms.insertText === "function",
    blockCount: ed ? ed.children.length : 0,
    slateText: ed ? SlateNode.string(ed) .length : 0,
  };
}
