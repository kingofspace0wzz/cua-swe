export function applyPinnedGeometry(element, workspaceLayout) {
  // Regression: the pinned data column ignores the selection rail.
  element.style.setProperty('--pinned-name-offset', '0px');
}
