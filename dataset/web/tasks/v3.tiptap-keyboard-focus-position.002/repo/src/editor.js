// Draft Composer editor engine, backed by a real Tiptap/ProseMirror editor.
//
// The document is a flat sequence of paragraph blocks. Tiptap owns the
// contenteditable surface, the document model, and — crucially — the mapping
// between rendered pixel coordinates and document positions. Caret arithmetic
// here delegates to ProseMirror's live layout via view.posAtCoords and
// view.coordsAtPos, so results depend on how the text actually wraps at
// runtime rather than any precomputed offset.

import { Editor } from '@tiptap/core';
import Document from '@tiptap/extension-document';
import Paragraph from '@tiptap/extension-paragraph';
import Text from '@tiptap/extension-text';
import { TextSelection } from '@tiptap/pm/state';

// Build a ProseMirror document JSON from the plain block strings.
export function buildDoc(blocks) {
  const list = blocks.slice();
  return {
    blocks: list,
    content: {
      type: 'doc',
      content: list.map((text) => ({
        type: 'paragraph',
        content: text ? [{ type: 'text', text }] : [],
      })),
    },
  };
}

// Mount a real Tiptap editor into the surface host and render the document.
export function renderDoc(root, doc) {
  root.innerHTML = '';
  const editor = new Editor({
    element: root,
    extensions: [Document, Paragraph, Text],
    content: doc.content,
    autofocus: false,
    editable: true,
  });
  doc.editor = editor;
  // Expose for observation/screenshot tooling.
  root.__editor = editor;
  return editor;
}

// Place the ProseMirror selection at a linear document position and publish the
// resulting rendered caret geometry so it is observable on screen and in tests.
export function placeCaretAtPos(root, doc, pos) {
  const editor = doc.editor;
  if (!editor) return;
  const view = editor.view;
  const size = view.state.doc.content.size;
  const clamped = Math.max(1, Math.min(pos, size));
  const tr = view.state.tr.setSelection(TextSelection.create(view.state.doc, clamped));
  view.dispatch(tr);
  editor.commands.focus();
  reflectCaret(root, view, view.state.selection.from);
}

function reflectCaret(root, view, pos) {
  const coords = view.coordsAtPos(pos);
  const rootRect = view.dom.getBoundingClientRect();
  const top = Math.round(coords.top - rootRect.top);
  const left = Math.round(coords.left - rootRect.left);
  root.dataset.caretPos = String(pos);
  root.dataset.caretTop = String(top);
  root.dataset.caretLeft = String(left);
  const host = root.parentElement;
  let bar = host.querySelector('.caret-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.className = 'caret-bar';
    host.appendChild(bar);
  }
  const hostRect = host.getBoundingClientRect();
  bar.style.top = (coords.top - hostRect.top) + 'px';
  bar.style.left = (coords.left - hostRect.left) + 'px';
  bar.style.height = (Math.max(coords.bottom - coords.top, 14)) + 'px';
}

// Map a pixel anchor expressed relative to the editor surface to the nearest
// document position using ProseMirror's LIVE hit-testing (view.posAtCoords).
// The result depends on how the text wraps at runtime.
export function posFromCoords(root, doc, anchor) {
  const editor = doc.editor;
  if (!editor) return 1;
  const view = editor.view;
  const rootRect = view.dom.getBoundingClientRect();
  const hit = view.posAtCoords({
    left: rootRect.left + anchor.x,
    top: rootRect.top + anchor.y,
  });
  return hit ? hit.pos : 1;
}
