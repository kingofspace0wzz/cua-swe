// Scroll coordination for the Field Log Composer body.
//
// After the caret moves the body may need to scroll so the writer keeps seeing
// where they are typing. The body element carries a live caret line box on its
// dataset; the workspace frame sizes the body between its top and bottom bands.
// Several coordination modes are kept here because different log frames have
// historically wanted different follow behavior; the mode in force is selected
// by the constant below.

// Follow modes. Each takes the scroll body and returns a target scrollTop, or
// null to leave the current scroll position untouched.
const modes = {
  // Leave the body wherever it is. Movement never repositions the surface.
  hold(body) {
    return null;
  },

  // Bring the caret line fully inside the body, scrolling as little as needed.
  // If the caret line sits below the visible band, scroll down just far enough
  // that its lower edge clears the reserved bottom margin; if it sits above,
  // scroll up just far enough that its upper edge clears the top margin.
  reveal(body) {
    const caretTop = Number(body.dataset.caretTopViewport);
    const caretBottom = Number(body.dataset.caretBottomViewport);
    const margin = readSafeMargin(body);
    const view = body.clientHeight;
    let scrollTop = body.scrollTop;
    if (caretBottom > view - margin) {
      scrollTop += caretBottom - (view - margin);
    } else if (caretTop < margin) {
      scrollTop -= (margin - caretTop);
    }
    return clampScroll(body, scrollTop);
  },

  // Snap the caret line to the top of the visible band regardless of how far
  // that scrolls the earlier content out of the body.
  snap(body) {
    const caretTop = Number(body.dataset.caretTopViewport);
    const margin = readSafeMargin(body);
    const scrollTop = body.scrollTop + caretTop - margin;
    return clampScroll(body, scrollTop);
  },
};

function readSafeMargin(body) {
  const m = Number(body.dataset.safeMargin);
  return Number.isFinite(m) ? m : 0;
}

function clampScroll(body, scrollTop) {
  const max = body.scrollHeight - body.clientHeight;
  return Math.max(0, Math.min(max, scrollTop));
}

// Coordination mode currently in force for the composer body.
const ACTIVE_MODE = 'hold';

// Notify the controller that the caret moved. When a follow mode is in force
// it repositions the body and re-syncs the published caret geometry.
export function onCaretMoved(body, resync) {
  const target = modes[ACTIVE_MODE](body);
  if (target === null || target === undefined) return;
  body.scrollTop = target;
  if (typeof resync === 'function') resync();
}
