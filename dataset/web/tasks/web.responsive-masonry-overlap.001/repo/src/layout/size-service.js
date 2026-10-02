export const DASHBOARD_GRID = Object.freeze({
  unitWidth: 50,
  groupGapX: 7,
  groupGapY: 7,
  groupPaddingX: 6
});

export function groupPixelWidth(columns, grid = DASHBOARD_GRID) {
  return (
    columns * grid.unitWidth +
    2 * grid.groupPaddingX +
    (columns - 1) * grid.groupGapX
  );
}

export function availableLayoutWidth(container) {
  return container.clientWidth;
}
