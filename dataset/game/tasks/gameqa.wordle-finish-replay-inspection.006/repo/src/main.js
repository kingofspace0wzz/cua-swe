import { BoardView } from "./board-view.js";
import { LetterGame } from "./game.js";

const view = new BoardView();
let game = null;
let currentMode = new URLSearchParams(window.location.search).get("mode") || "daily";
if (!["daily", "practice"].includes(currentMode)) currentMode = "daily";

async function fetchChallenge(mode) {
  const response = await fetch(`/api/challenge?mode=${encodeURIComponent(mode)}`, {
    cache: "no-store"
  });
  if (!response.ok) throw new Error(`challenge request failed: ${response.status}`);
  return response.json();
}

async function loadMode(mode) {
  const challenge = await fetchChallenge(mode);
  currentMode = mode;
  const nextUrl = new URL(window.location.href);
  nextUrl.searchParams.set("mode", mode);
  window.history.replaceState(null, "", nextUrl);
  view.motion.reset(view.boardElement);
  game = new LetterGame(challenge, (state, animation) => view.render(state, animation));
  return game.snapshot();
}

function handleKey(value) {
  if (!game) return;
  if (value === "enter") game.submit();
  else if (value === "erase") game.erase();
  else game.inputLetter(value);
}

view.setHandlers({
  key: handleKey,
  restart: () => game?.restart(),
  mode: (mode) => loadMode(mode),
  hard: (enabled) => game?.setHardMode(enabled)
});

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (/^[a-z]$/i.test(event.key)) {
    event.preventDefault();
    handleKey(event.key.toLowerCase());
  } else if (event.key === "Backspace") {
    event.preventDefault();
    handleKey("erase");
  } else if (event.key === "Enter") {
    event.preventDefault();
    handleKey("enter");
  }
});

window.gameAPI = {
  getState: () => {
    if (!game) return { status: "loading", is_actionable: false };
    return {
      ...game.snapshot(),
      presentation: view.snapshot()
    };
  },
  reset: async (options = {}) => {
    const mode = options.mode || currentMode;
    if (mode !== currentMode) {
      await loadMode(mode);
    } else {
      game.restart();
    }
    return {
      applied: {
        seed: game.challenge.seed,
        level: game.challenge.level,
        mode: game.challenge.mode
      }
    };
  },
  getCapabilities: () => ({
    supports_seed: true,
    supports_level_select: true,
    supports_inplace_reset: true,
    provides_actionable_flag: true,
    supports_mode_select: true
  })
};

loadMode(currentMode).catch((error) => {
  document.querySelector("#notice").textContent = `Unable to start: ${error.message}`;
  document.querySelector("#notice").dataset.kind = "error";
  console.error(error);
});
