import { mountEditor, insertBlock, blockNode, blockOffsetTop, scrollRegion } from './editor.js';
import { snapshotBefore, settleAfterPaste } from './pasteFlow.js';

const state = {
  doc: null,
  quill: null,
  session: null,
  applied: false,
};

async function loadSession() {
  const res = await fetch('/api/session');
  return res.json();
}

function renderPresence(session) {
  const bar = document.getElementById('presence');
  bar.innerHTML = '';
  for (const p of session.presence) {
    const chip = document.createElement('span');
    chip.className = 'presence-chip ' + (p.actorKind === 'self' ? 'is-self' : 'is-peer');
    chip.dataset.actorId = p.actorId;
    // Presence chip carries the collaborator label and, when known, a short
    // note about where that collaborator is currently focused in the document
    // (co-reading here with you, or working elsewhere).
    chip.dataset.focus = p.focus || '';
    chip.textContent = p.actorLabel;
    if (p.actorKind === 'peer' && p.focusNote) {
      const note = document.createElement('small');
      note.className = 'focus-note';
      note.textContent = p.focusNote;
      chip.appendChild(document.createTextNode(' '));
      chip.appendChild(note);
    }
    bar.appendChild(chip);
  }
  // Status line describing the pending edit and who authored it.
  const author = session.presence.find((p) => p.actorId === session.paste.actorId);
  const status = document.getElementById('sync-status');
  status.dataset.actorId = session.paste.actorId;
  status.dataset.actorKind = author ? author.actorKind : '';
  status.dataset.actorFocus = author ? (author.focus || '') : '';
  status.textContent = session.paste.statusLine;
}

// Perform the pending paste. The actor context comes straight from the session.
function performPaste() {
  if (state.applied) return;
  const quill = state.quill;
  const paste = state.session.paste;
  const before = snapshotBefore(quill, state.session.readerAnchorId);
  const insertedNode = insertBlock(quill, state.doc, paste.atIndex, paste.block);
  const author = state.session.presence.find((p) => p.actorId === paste.actorId);
  const ctx = {
    before,
    insertedNode,
    actorId: paste.actorId,
    actorKind: author ? author.actorKind : '',
    // Where the paste's author is currently focused in the shared document,
    // straight from the presence roster (co-reading here, or working away).
    actorFocus: author ? (author.focus || '') : '',
  };
  settleAfterPaste(quill, ctx);
  state.applied = true;
  scrollRegion(quill).dataset.pasteApplied = '1';
}

function mount(session) {
  state.session = session;
  const host = document.getElementById('reader');
  const { quill, doc } = mountEditor(host, session.blocks);
  state.quill = quill;
  state.doc = doc;
  const region = scrollRegion(quill);
  document.getElementById('space-label').textContent = session.space;
  document.getElementById('guide-text').textContent = session.guide;
  renderPresence(session);

  // Park the reader where the session says they were last reading, using the
  // block that Quill rendered for that line.
  const anchor = blockNode(quill, session.readerAnchorId);
  if (anchor) {
    const top = blockOffsetTop(quill, anchor);
    region.scrollTop = region.scrollTop + top - session.readerAnchorViewportTop;
  }

  // The pending edit is applied like any other collaborative update: the agent
  // triggers it from the sync control or with the keyboard shortcut.
  document.getElementById('apply-btn').addEventListener('click', performPaste);
  document.addEventListener('keydown', (e) => {
    if (e.altKey && (e.key === 'p' || e.key === 'P')) {
      e.preventDefault();
      performPaste();
    }
  });
}

loadSession().then(mount);
