import { buildDoc, renderDoc } from './editor.js';
import { setResumeBookmark, resumeFocus } from './focusResume.js';

const state = { doc: null };

async function loadWorkspace() {
  const res = await fetch('/api/resume-bookmark');
  return res.json();
}

function mount(payload) {
  // The document body arrives as the writer left it; the composer decides where
  // the caret resumes when focus returns from the keyboard.
  state.doc = buildDoc(payload.blocks);
  const surface = document.getElementById('surface');
  const editor = renderDoc(surface, state.doc);
  document.getElementById('draft-title').textContent = payload.title;
  document.getElementById('resume-note').textContent = payload.note;
  document.getElementById('workspace-label').textContent = payload.workspace;
  setResumeBookmark(payload.bookmark);

  // The real editable surface is the ProseMirror node Tiptap renders inside the
  // host; wire keyboard focus resume onto it.
  const pmRoot = editor.view.dom;
  pmRoot.setAttribute('tabindex', '0');
  pmRoot.addEventListener('focus', () => {
    resumeFocus(surface, state.doc);
  });
  document.addEventListener('keydown', (e) => {
    // Resume-drafting shortcut: bring focus back to the composer.
    if (e.altKey && (e.key === 'r' || e.key === 'R')) {
      e.preventDefault();
      pmRoot.focus();
      resumeFocus(surface, state.doc);
    }
  });
}

loadWorkspace().then(mount);
