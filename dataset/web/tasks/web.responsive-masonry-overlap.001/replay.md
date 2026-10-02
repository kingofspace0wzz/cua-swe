# Replay: web.responsive-masonry-overlap.001

## Manual browser reproduction

1. From `repo/`, run `npm install`, `npm run build`, and `npm run dev`.
2. Open `http://127.0.0.1:4173` at 1180 by 760. Confirm Lamps,
   Freezer, and System form three separate columns and Temperature is visible.
3. Narrow the viewport to 760 by 760. The layout becomes two columns, but the
   System group is placed over the lower part of Freezer. Temperature remains
   in the document yet is painted underneath System and cannot be used.
4. Narrow to 420 by 760. Confirm the three groups form a usable vertical stack
   and the Temperature control works again.
5. Re-expand to 1180 by 760, then repeat the 760, 420, and 1180 width cycle.
   The broken medium collision is deterministic; the unaffected wide and
   narrow layouts remain stable and controls continue to work.

## Evaluation isolation

The durable Chromium reproduction evidence is stored outside the evaluated
workspace under the task's review directory. The behavioral verifier,
gold patch, negative patch, this replay, task metadata, and review material are
author-side evaluation artifacts. The orchestrator supplies only source to
both agent conditions and runs a pristine verifier after the agent exits.
