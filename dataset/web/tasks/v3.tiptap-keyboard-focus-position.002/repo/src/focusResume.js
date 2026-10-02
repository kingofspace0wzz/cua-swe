// Keyboard-focus resume plumbing for the Draft Composer.
// A workspace bookmark preserves the saved caret anchors recorded during the
// writer's session. This module owns the final resolution.

import { posFromCoords, placeCaretAtPos } from './editor.js';

// Saved workspace bookmark. Keep both fields intact for compatibility.
let bookmark = null;

export function setResumeBookmark(bm) {
  bookmark = bm || null;
}

// Resolve a linear document position on keyboard focus.
export function resolveResumePosition(root, doc) {
  if (!bookmark) return 1;
  return resumeStrategy(root, doc, bookmark);
}

// Decide the resume position from the saved bookmark.
function resumeStrategy(root, doc, bm) {
  return 1;
}

export function resumeFocus(root, doc) {
  const pos = resolveResumePosition(root, doc);
  placeCaretAtPos(root, doc, pos);
  return pos;
}
