import http from 'node:http';

// Harness-owned draft workspace service.
//
// Each workspace hands the composer a draft body plus a saved caret bookmark.
// The bookmark carries more than one saved caret anchor recorded during the
// writer's session. Every anchor is the same shape -- a surface-relative pixel
// point -- and the writer's session spanned more than one layout of the same
// draft, so an anchor recorded under an earlier layout no longer points at the
// text it once did. The product only stores whatever bookmark arrives and only
// ever renders whatever caret position it decides to compute; it receives no
// named document position and no flag saying which anchor is still current.
//
// Because the anchors share one shape and carry no authoritative marker, the
// only thing that separates the live anchor from the carried-over one is where
// each lands once the draft actually wraps and renders on this surface.

const args = process.argv.slice(2);
const port = Number((args.includes('--port') ? args[args.indexOf('--port') + 1] : 0) || 4412);
const host = (args.includes('--host') ? args[args.indexOf('--host') + 1] : '') || '127.0.0.1';
const variant = process.env.CONTRACT_VARIANT || 'a';

// Three protected workspace payloads. Each supplies a body whose paragraphs
// wrap on the narrow surface and a list of same-shape saved anchors. Exactly one
// anchor lands on a rendered glyph line (the writer's live spot, described by
// the visible note); the other was recorded under an earlier layout of the same
// draft and now falls into the blank region between wrapped paragraphs.
const workspaces = {
  a: {
    workspace: 'Field notes',
    title: 'Site visit — north corridor',
    note: 'You were partway through the second paragraph, a few words into the line that begins after the wrap.',
    blocks: [
      'Arrived on site just after nine and walked the north corridor end to end before the crew started.',
      'The east stairwell handrail is loose near the third landing and the paint has started flaking along the lower rail where people grip it.',
      'Follow up with the contractor about the loading dock seal.',
    ],
    bookmark: { anchors: [{ x: 60, y: 200 }, { x: 60, y: 135 }] },
  },
  b: {
    workspace: 'Interview log',
    title: 'Candidate debrief',
    note: 'You stopped in the middle of the long answer paragraph, on the second wrapped line.',
    blocks: [
      'Overall a strong signal on the systems round.',
      'They walked through the rate limiter design cleanly and caught the token bucket refill edge case without a hint, then reworked the sharding plan when I pushed on hot keys.',
      'Schedule the follow up loop for next week.',
    ],
    bookmark: { anchors: [{ x: 48, y: 200 }, { x: 48, y: 110 }] },
  },
  c: {
    workspace: 'Release notes',
    title: 'Build 4.8 draft',
    note: 'You left off inside the changelog paragraph, on the third visible line.',
    blocks: [
      'This build focuses on editor stability.',
      'Fixed a caret drift after focus, tightened the paste path so trailing whitespace no longer accumulates, and reduced layout thrash when toggling the outline panel on large documents.',
      'Known issue: the outline panel flickers once on first open.',
    ],
    bookmark: { anchors: [{ x: 40, y: 68 }, { x: 40, y: 132 }] },
  },
};
const payload = workspaces[variant] || workspaces.a;

http.createServer((req, res) => {
  res.setHeader('content-type', 'application/json');
  if (req.url === '/health') { res.end('{"ok":true}'); return; }
  if (req.url === '/api/resume-bookmark') { res.end(JSON.stringify(payload)); return; }
  res.statusCode = 404; res.end('{"error":"not found"}');
}).listen(port, host);
