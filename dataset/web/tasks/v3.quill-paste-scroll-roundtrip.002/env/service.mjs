import http from 'node:http';

// Harness-owned collaboration session service.
//
// Each session hands the reading surface a shared document, the block the local
// reader was last parked on, its presence roster, and one pending paste. The
// paste carries the id of whoever authored it. The roster marks each actor as
// the local reader (self) or a remote collaborator (peer), and — for a remote
// collaborator — where in the document that collaborator is currently focused:
// a peer may be "reading here" alongside the local reader at the same passage,
// or working "away" elsewhere in the document. The product only learns who
// pasted and where each collaborator is looking; it is told nothing about how
// the reading region should settle for that combination. That settling policy
// lives with the harness.
//
// Sessions vary the document, the parked reading position, where the pending
// paste lands, the author, and the collaborator's focus, so that no rule that
// keys on the author alone can satisfy every session.

const args = process.argv.slice(2);
const port = Number((args.includes('--port') ? args[args.indexOf('--port') + 1] : 0) || 4433);
const host = (args.includes('--host') ? args[args.indexOf('--host') + 1] : '') || '127.0.0.1';
const variant = process.env.CONTRACT_VARIANT || 'a';

function longDoc(prefix, count) {
  const seeds = [
    'The intake queue keeps a rolling window of the last thirty submissions so reviewers can catch duplicates before they fan out to the wider team for triage.',
    'Each entry records the requester, the affected surface, and a short reproduction note that the on-call engineer expands during the first pass.',
    'When a submission clears triage it moves to the staging lane where the fix is drafted against a snapshot of the reporting build.',
    'Reviewers annotate the staging lane inline, and those annotations roll up into the weekly summary that leadership reads on Monday.',
    'The verification lane holds anything waiting on a reproduction from the reporter, and it drains automatically once the reporter confirms.',
    'A separate archive lane keeps closed items searchable for a full quarter before they are compacted into the cold store.',
    'Automation posts a digest into the shared channel every afternoon so nobody has to poll the board to know what changed.',
    'The playbook asks every reviewer to leave a one line rationale when they move an item so the trail stays legible later.',
  ];
  const blocks = [{ id: `${prefix}-h`, kind: 'head', text: 'Working agreement' }];
  for (let i = 0; i < count; i++) {
    blocks.push({ id: `${prefix}-${i}`, kind: 'para', text: seeds[i % seeds.length] });
  }
  return blocks;
}

// Five protected sessions. self-* sessions are authored by the local reader.
// peer-* sessions are authored by a remote collaborator; a peer is either
// working "away" from the reader's passage or "reading here" alongside the
// reader at the same spot. The parked position, the paste index, and the peer's
// focus differ across sessions.
//
//   focus: 'here'  -> the collaborator is co-reading at the local reader's
//                     current passage; their edit lands right where the reader
//                     is looking.
//   focus: 'away'  -> the collaborator is working elsewhere; their edit lands
//                     away from (above) the reader's current passage.
const sessions = {
  // self, shallow parked position, paste lands well below the fold.
  a: {
    space: 'Support triage',
    guide: 'You are drafting near the top of the shared doc. Your own paste is on its way in.',
    prefix: 's1',
    count: 16,
    readerIndex: 2,
    readerViewportTop: 40,
    pasteIndex: 12,
    author: 'self',
    statusLine: 'You added a paragraph.',
    block: { kind: 'para', text: 'Adding a note: batch the duplicate submissions before they reach the staging lane, otherwise the weekly summary double counts them and the Monday read looks worse than reality.' },
  },
  // self, deep parked position, paste lands further down, off the current fold.
  b: {
    space: 'Launch notes',
    guide: 'You are drafting deep in the shared doc. Your own paste is on its way in.',
    prefix: 's2',
    count: 22,
    readerIndex: 6,
    readerViewportTop: 40,
    pasteIndex: 18,
    author: 'self',
    statusLine: 'You added a paragraph.',
    block: { kind: 'para', text: 'Adding a note: the archive lane should compact on a rolling schedule so the cold store never sees a quarter-end spike that stalls the nightly job.' },
  },
  // peer working AWAY, shallow parked position, paste lands ABOVE the reader.
  c: {
    space: 'Incident review',
    guide: 'You are reading near the middle of the shared doc while a collaborator works elsewhere.',
    prefix: 'p1',
    count: 14,
    readerIndex: 8,
    readerViewportTop: 50,
    pasteIndex: 3,
    author: 'peer',
    peerLabel: 'Priya',
    peerFocus: 'away',
    peerFocusNote: 'editing the intake section',
    statusLine: 'Priya added a paragraph.',
    block: { kind: 'para', text: 'From Priya: pulling the verification lane earlier in the flow would keep reporters from waiting on a reproduction that the on-call already has in hand.' },
  },
  // peer working AWAY, deep parked position, paste lands ABOVE the reader.
  d: {
    space: 'Roadmap sync',
    guide: 'You are reading deep in the shared doc while a collaborator works elsewhere.',
    prefix: 'p2',
    count: 18,
    readerIndex: 13,
    readerViewportTop: 70,
    pasteIndex: 5,
    author: 'peer',
    peerLabel: 'Marcus',
    peerFocus: 'away',
    peerFocusNote: 'editing the archive section',
    statusLine: 'Marcus added a paragraph.',
    block: { kind: 'para', text: 'From Marcus: the afternoon digest should link straight into the staging lane so leadership can scan the drafted fixes without hunting for them.' },
  },
  // peer READING HERE (co-reading at the reader's passage), paste lands right at
  // the reader's current spot.
  e: {
    space: 'Design critique',
    guide: 'You are reading in the shared doc and a collaborator is reading here with you.',
    prefix: 'p3',
    count: 20,
    readerIndex: 9,
    readerViewportTop: 50,
    pasteIndex: 18,
    author: 'peer',
    peerLabel: 'Dana',
    peerFocus: 'here',
    peerFocusNote: 'reading here with you',
    statusLine: 'Dana added a paragraph.',
    block: { kind: 'para', text: 'From Dana: the one line rationale on each move is exactly what makes the trail legible; we should surface it in the weekly summary too.' },
  },
};

function buildPayload(v) {
  const s = sessions[v] || sessions.a;
  const blocks = longDoc(s.prefix, s.count);
  const readerAnchorId = blocks[s.readerIndex].id;
  const selfId = 'you';
  const peerId = 'peer-1';
  const presence = [{ actorId: selfId, actorLabel: 'You', actorKind: 'self', focus: 'reader', focusNote: 'that is you' }];
  if (s.author === 'peer') {
    presence.push({
      actorId: peerId,
      actorLabel: s.peerLabel,
      actorKind: 'peer',
      focus: s.peerFocus,
      focusNote: s.peerFocusNote,
      focusAnchorId: s.peerFocus === 'here' ? readerAnchorId : null,
    });
  } else {
    presence.push({ actorId: peerId, actorLabel: 'Ada', actorKind: 'peer', focus: 'away', focusNote: 'browsing versions' });
  }
  const pasteActorId = s.author === 'peer' ? peerId : selfId;
  const pasteBlockId = `${s.prefix}-ins`;
  return {
    space: s.space,
    guide: s.guide,
    blocks,
    readerAnchorId,
    readerAnchorViewportTop: s.readerViewportTop,
    presence,
    paste: {
      actorId: pasteActorId,
      atIndex: s.pasteIndex,
      statusLine: s.statusLine,
      block: { id: pasteBlockId, kind: s.block.kind, text: s.block.text },
    },
  };
}

const payload = buildPayload(variant);

http.createServer((req, res) => {
  res.setHeader('content-type', 'application/json');
  if (req.url === '/health') { res.end('{"ok":true}'); return; }
  if (req.url === '/api/session') { res.end(JSON.stringify(payload)); return; }
  res.statusCode = 404; res.end('{"error":"not found"}');
}).listen(port, host);
