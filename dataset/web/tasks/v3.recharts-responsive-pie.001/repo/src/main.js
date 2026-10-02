// Allocation Ring Studio bootstrap.
//
// The studio shows a live allocation ring on the left and a saved reference of
// how that same board looked when it was approved on the right, so an analyst
// can confirm the live ring matches the approved one. A profile selector across
// the top re-lays the board at different card shapes (widescreen, sidebar,
// stacked, compact); each profile is fetched fresh from the board service and
// re-mounted, which re-measures and re-draws the ring.
import { mountBoard } from './view.js';

const PROFILES = ['widescreen', 'sidebar', 'stacked', 'compact'];
let mounted = null;

async function loadBoard(profile) {
  const r = await fetch(`/studio/board?profile=${encodeURIComponent(profile)}`);
  return r.json();
}

function renderReference(board) {
  const host = document.getElementById('reference');
  host.innerHTML = '';
  const frame = document.createElement('div');
  frame.className = 'reference-frame';
  frame.style.width = board.card.width + 'px';
  frame.style.height = board.card.height + 'px';
  const img = document.createElement('img');
  img.className = 'reference-img';
  img.alt = 'approved reference';
  img.src = board.reference;
  frame.appendChild(img);
  host.appendChild(frame);
}

function paintSelector(active) {
  const bar = document.getElementById('profile-bar');
  bar.innerHTML = '';
  PROFILES.forEach((p) => {
    const b = document.createElement('button');
    b.className = 'profile-btn' + (p === active ? ' active' : '');
    b.dataset.profile = p;
    b.textContent = p[0].toUpperCase() + p.slice(1);
    b.addEventListener('click', () => activate(p));
    bar.appendChild(b);
  });
}

async function activate(profile) {
  const board = await loadBoard(profile);
  document.getElementById('board-title').textContent = board.title;
  document.getElementById('board-note').textContent = board.note;
  paintSelector(profile);
  if (mounted && mounted.disconnect) mounted.disconnect();
  mounted = mountBoard(document.getElementById('live'), board);
  renderReference(board);
  document.body.dataset.profile = profile;
  document.body.dataset.ready = '1';
}

// Expose a scripted profile switch so a harness (or a keyboard test) can drive
// the same code path a click drives.
window.__selectProfile = (p) => activate(p);

activate('widescreen');
