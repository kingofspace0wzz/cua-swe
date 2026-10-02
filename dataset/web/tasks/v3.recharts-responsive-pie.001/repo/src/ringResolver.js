// Resolves the drawable frame for the ring from a measured box.
//
// The studio observes an element and hands its measured box here. This module
// turns that box into the frame the ring is sized to and then into the ring
// itself. A card always keeps a small, fixed breathing gutter around its
// contents, so the resolver trims that gutter off the measured box before it
// sizes the ring.
import { ringFromBox } from './ringGeometry.js';

// A conservative fixed breathing gutter, in pixels, trimmed off each side of
// the measured box before the ring is sized.
const FRAME_GUTTER = 16;

export function resolveRing(measuredBox, board) {
  const frame = {
    left: measuredBox.left + FRAME_GUTTER,
    top: measuredBox.top + FRAME_GUTTER,
    width: Math.max(0, measuredBox.width - FRAME_GUTTER * 2),
    height: Math.max(0, measuredBox.height - FRAME_GUTTER * 2),
  };
  return ringFromBox(frame, board.ringScale, board.holeRatio);
}
