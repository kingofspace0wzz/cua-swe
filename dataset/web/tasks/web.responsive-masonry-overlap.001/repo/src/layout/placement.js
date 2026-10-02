import { DASHBOARD_GRID } from "./size-service.js";

function nextAvailableX(placedGroups, candidateY, gap) {
  let x = 0;

  for (const group of placedGroups) {
    if (group.height + group.top > candidateY) {
      x += group.width + gap;
    }
  }

  return x;
}

function firstRowCount(groups, availableWidth, gap) {
  let width = 0;
  let count = 0;

  while (width < availableWidth && count < groups.length) {
    width += groups[count].width + gap;
    count += 1;
  }

  width -= gap;
  return Math.max(
    1,
    Math.min(groups.length, width > availableWidth ? count - 1 : count)
  );
}

export function calculateGroupPlacement(
  groups,
  availableWidth,
  grid = DASHBOARD_GRID
) {
  const firstRow = firstRowCount(groups, availableWidth, grid.groupGapX);
  const rowWidth =
    groups
      .slice(0, firstRow)
      .reduce((total, group) => total + group.width, 0) +
    grid.groupGapX * (firstRow - 1);
  const widestGroup = Math.max(...groups.map((group) => group.width));

  let leftPadding = Math.max(0, (availableWidth - rowWidth) / 2);
  if (widestGroup + leftPadding > availableWidth) {
    leftPadding = grid.groupPaddingX;
  }

  const usableWidth = availableWidth - 2 * leftPadding;
  const placedGroups = [];
  let maxY = 0;

  for (const group of groups) {
    let x = 0;
    let y = grid.groupGapY;

    for (let candidateY = 0; candidateY < maxY; candidateY += 1) {
      if (candidateY === maxY - 1) {
        x = 0;
        y = candidateY;
        break;
      }

      const candidateX = nextAvailableX(
        placedGroups,
        candidateY,
        grid.groupGapX
      );
      if (candidateX + group.width <= usableWidth) {
        x = candidateX;
        y += candidateY;
        break;
      }
    }

    const placed = {
      ...group,
      left: leftPadding + x,
      top: y
    };
    placedGroups.push(placed);
    maxY = Math.max(maxY, y + group.height + grid.groupGapY);
  }

  return {
    groups: placedGroups,
    minHeight: maxY + grid.groupGapY
  };
}
