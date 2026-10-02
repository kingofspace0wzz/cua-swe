// Scroll handling for the collaborative paste pipeline.
//
// When a block is pasted into the live Quill document the reading region has to
// settle somewhere. The pipeline captures a snapshot of Quill's scroll region
// just before the insertion (its scrollTop, the reading-anchor block, and where
// that anchor sat in the viewport), performs the insertion through Quill, then
// hands a context to the settle step to choose a final scroll position on
// Quill's editor root.
//
// Several settle strategies are available. They read only the live rendered
// Quill layout (via Quill's bounds and the rendered line nodes), so their
// results are derived at runtime rather than fixed here. The pipeline does not
// encode which strategy each kind of paste should use.

import { blockNode, blockOffsetTop, scrollRegion } from './editor.js';

// Snapshot the Quill scroll region before an insertion mutates the layout.
export function snapshotBefore(quill, readerAnchorId) {
  const region = scrollRegion(quill);
  const anchor = blockNode(quill, readerAnchorId);
  return {
    scrollTop: region.scrollTop,
    readerAnchorId,
    anchorViewportTop: anchor ? blockOffsetTop(quill, anchor) : null,
  };
}

// Strategy: leave the raw scroll offset exactly where it was before the paste.
function settleRawOffset(quill, ctx) {
  scrollRegion(quill).scrollTop = ctx.before.scrollTop;
}

// Strategy: bring the freshly inserted block into view within the region. Uses
// Quill's own line node to locate the insertion inside the editor viewport.
function settleRevealInsertion(quill, ctx) {
  const region = scrollRegion(quill);
  const node = ctx.insertedNode;
  if (!node) return;
  const top = blockOffsetTop(quill, node);
  const regionH = region.clientHeight;
  const nodeH = node.getBoundingClientRect().height;
  const target = region.scrollTop + top - Math.max(0, (regionH - nodeH) / 2);
  region.scrollTop = Math.max(0, target);
}

// Strategy: keep the reading-anchor block at the same viewport position it held
// before the paste, compensating for any layout shift the Quill insertion
// caused.
function settleReanchorReader(quill, ctx) {
  const region = scrollRegion(quill);
  const anchor = blockNode(quill, ctx.before.readerAnchorId);
  if (!anchor || ctx.before.anchorViewportTop == null) {
    region.scrollTop = ctx.before.scrollTop;
    return;
  }
  const nowTop = blockOffsetTop(quill, anchor);
  const delta = nowTop - ctx.before.anchorViewportTop;
  region.scrollTop = Math.max(0, region.scrollTop + delta);
}

const SETTLE = {
  raw: settleRawOffset,
  reveal: settleRevealInsertion,
  reanchor: settleReanchorReader,
};

// Choose how the region settles after a paste. The context carries who authored
// the paste and where that author is currently focused in the shared document,
// but the pipeline currently applies one blanket strategy and ignores both.
export function settleAfterPaste(quill, ctx) {
  const strategy = selectSettleStrategy(ctx);
  (SETTLE[strategy] || SETTLE.raw)(quill, ctx);
  scrollRegion(quill).dataset.settleStrategy = strategy;
}

function selectSettleStrategy(ctx) {
  return 'raw';
}
