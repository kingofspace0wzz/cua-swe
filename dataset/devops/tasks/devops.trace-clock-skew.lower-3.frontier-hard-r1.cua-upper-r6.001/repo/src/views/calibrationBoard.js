const SHEET_COUNT = 3;
let sheet = 1;

function apply() {
  const image = document.querySelector('[data-test="calibration-board"]');
  image.src = `${image.dataset.boardSource}?sheet=${sheet}`;
  document.querySelector('[data-test="board-sheet"]').textContent = `Sheet ${sheet} of ${SHEET_COUNT}`;
}

export function initCalibrationBoard() {
  document.querySelector('[data-test="board-prev"]').addEventListener("click", () => {
    sheet = sheet === 1 ? SHEET_COUNT : sheet - 1;
    apply();
  });
  document.querySelector('[data-test="board-next"]').addEventListener("click", () => {
    sheet = sheet === SHEET_COUNT ? 1 : sheet + 1;
    apply();
  });
  apply();
}
