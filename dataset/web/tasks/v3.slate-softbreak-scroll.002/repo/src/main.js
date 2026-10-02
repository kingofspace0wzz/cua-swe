// Boots the Field Log Composer inside its workspace frame. The editing surface
// is a real Slate editor (see slateComposer.js); this module wires the frame
// geometry from the workspace service and the scripted review helpers.
import { mountLog, bindKeys, insertText, insertSoftBreak, syncCaretGeometry, placeCaretInBlock, scrollCaretToBottomEdge, frameworkProbe } from './slateComposer.js';

async function boot() {
  let frame;
  try {
    const res = await fetch('/api/composer-frame');
    frame = await res.json();
  } catch {
    frame = { workspace: 'Log', title: 'Untitled', frame: { height: 420, topBand: 48, bottomBand: 40 }, body: ['Empty log.'] };
  }

  document.getElementById('workspace-name').textContent = frame.workspace;
  document.getElementById('log-title').textContent = frame.title;

  const shell = document.getElementById('frame-shell');
  const topBar = document.getElementById('action-bar');
  const bottomBar = document.getElementById('status-strip');
  const body = document.getElementById('surface');

  // The workspace frame sizes its bands; the scrollable log body is what is
  // left between them. The reserved bands double as the safe margin the body
  // keeps clear of the caret.
  shell.style.height = frame.frame.height + 'px';
  topBar.style.height = frame.frame.topBand + 'px';
  bottomBar.style.height = frame.frame.bottomBand + 'px';
  const bodyHeight = frame.frame.height - frame.frame.topBand - frame.frame.bottomBand;
  body.style.height = bodyHeight + 'px';
  // Each workspace fixes its own text scale, so one continued line is a
  // different height on each frame. The base surface font size is 15px.
  const fontScale = Number.isFinite(frame.fontScale) ? frame.fontScale : 1;
  body.style.fontSize = (15 * fontScale).toFixed(2) + 'px';
  // The follow behavior keeps the caret clear of the smaller reserved band.
  body.dataset.safeMargin = String(Math.min(frame.frame.topBand, frame.frame.bottomBand));

  mountLog(body, frame.body);
  bindKeys(body);
  // The writer is partway through the log on the active entry, with the surface
  // scrolled so that entry sits at the bottom edge of the visible band.
  const activeBlock = Number.isInteger(frame.caretBlock) ? frame.caretBlock : Math.max(0, frame.body.length - 2);
  placeCaretInBlock(activeBlock);
  scrollCaretToBottomEdge();
  syncCaretGeometry();

  // Live "cursor in view" flag in the status strip. The composer publishes the
  // caret's line box (relative to the visible band) onto the body dataset after
  // every edit; this reads that live geometry and reports only whether the
  // writing spot is currently inside the visible log body. It never carries a
  // target scroll position -- just the observed in-view / below-fold state, the
  // same thing a person sees by looking at the surface.
  const cursorFlag = document.getElementById('cursor-flag');
  function refreshCursorFlag() {
    if (!cursorFlag) return;
    const caretTop = Number(body.dataset.caretTopViewport);
    const caretBottom = Number(body.dataset.caretBottomViewport);
    if (!Number.isFinite(caretTop) || !Number.isFinite(caretBottom)) return;
    const margin = Number(body.dataset.safeMargin) || 0;
    const bandTop = margin;
    const bandBottom = body.clientHeight - margin;
    const visible = caretBottom <= bandBottom + 1 && caretTop >= bandTop - 1;
    cursorFlag.dataset.cursorVisible = visible ? '1' : '0';
    cursorFlag.textContent = visible ? 'Cursor in view' : 'Cursor below fold';
  }
  // Recompute whenever the composer republishes the live caret geometry.
  const flagObserver = new MutationObserver(refreshCursorFlag);
  flagObserver.observe(body, {
    attributes: true,
    attributeFilter: ['data-caret-bottom-viewport', 'data-caret-top-viewport'],
  });
  refreshCursorFlag();

  // Scripted helpers so the composer is drivable without a physical keyboard
  // during automated review; they mirror the key handlers.
  window.__composer = {
    type(text) {
      body.focus({ preventScroll: true });
      for (const ch of text) insertText(ch);
    },
    softBreak() {
      body.focus({ preventScroll: true });
      insertSoftBreak();
    },
    caret() {
      return {
        caretTopViewport: Number(body.dataset.caretTopViewport),
        caretBottomViewport: Number(body.dataset.caretBottomViewport),
        scrollTop: body.scrollTop,
        clientHeight: body.clientHeight,
        scrollHeight: body.scrollHeight,
        safeMargin: Number(body.dataset.safeMargin),
      };
    },
    framework() {
      return frameworkProbe();
    },
  };

  document.body.dataset.ready = '1';
}

boot();
