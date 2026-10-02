import {Session, lanes} from "./session.js";

const canvas = document.querySelector("#game");
const context = canvas.getContext("2d");
const STEP = 1 / 60;
const STARTUP_TIMEOUT_MS = 5000;
let session = null;
let routeCard = null;
let previous = 0;
let accumulator = 0;

const laneNames = {u: "TOP", v: "MIDDLE", w: "BOTTOM"};
const laneColors = {u: "#5be0d2", v: "#f6c95c", w: "#a987ff"};

function roundedRect(x, y, width, height, radius) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
}

function renderStartup(title, detail, failed = false) {
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#0b1822";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#102734";
  roundedRect(28, 150, 944, 330, 24);
  context.fill();
  context.strokeStyle = failed ? "#ff6d8e" : "#285061";
  context.lineWidth = 2;
  context.stroke();
  for (const [slot, y] of Object.entries(lanes)) {
    context.strokeStyle = `${laneColors[slot]}44`;
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(62, y);
    context.lineTo(938, y);
    context.stroke();
  }
  context.fillStyle = failed ? "#ffe6ec" : "#bcffea";
  context.font = "800 28px ui-sans-serif, system-ui";
  context.textAlign = "center";
  context.fillText(title, 500, 292);
  context.fillStyle = "#8db6c2";
  context.font = "600 14px ui-sans-serif, system-ui";
  context.fillText(detail, 500, 328);
  context.textAlign = "start";
}

async function fetchTicket() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), STARTUP_TIMEOUT_MS);
  try {
    const response = await fetch("/runtime/ticket", {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`runtime ticket unavailable: ${response.status}`);
    return response.json();
  } finally {
    clearTimeout(timeout);
  }
}

function loadRouteCard() {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const timeout = setTimeout(
      () => reject(new Error("route card timed out")),
      STARTUP_TIMEOUT_MS,
    );
    image.addEventListener("load", () => {
      clearTimeout(timeout);
      resolve(image);
    }, {once: true});
    image.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error("route card unavailable"));
    }, {once: true});
    image.src = "/runtime/route-card.png";
  });
}

function drawPrism(x, y, collected) {
  context.save();
  context.translate(x, y);
  context.rotate(Math.PI / 4);
  context.fillStyle = collected ? "#263c45" : "#f6d25f";
  context.shadowColor = collected ? "transparent" : "#f6d25f";
  context.shadowBlur = collected ? 0 : 18;
  context.fillRect(-10, -10, 20, 20);
  context.restore();
}

function drawLane(slot, marked, open) {
  const y = lanes[slot];
  context.fillStyle = marked ? "rgba(82,231,199,0.14)" : "rgba(49,82,96,0.08)";
  context.fillRect(520, y - 35, 190, 70);
  context.strokeStyle = marked ? "#65f2cf" : "#35596a";
  context.lineWidth = marked ? 4 : 2;
  context.setLineDash(marked ? [15, 8] : [5, 11]);
  context.beginPath();
  context.moveTo(520, y);
  context.lineTo(710, y);
  context.stroke();
  context.setLineDash([]);
  context.fillStyle = marked ? "#c2ffed" : "#708e9a";
  context.font = "800 12px ui-sans-serif, system-ui";
  context.fillText(marked ? "OPEN" : laneNames[slot], 528, y - 14);

  if (!open) {
    const glow = context.createRadialGradient(655, y, 4, 655, y, 40);
    glow.addColorStop(0, "#fff0f3");
    glow.addColorStop(0.25, "#ff6d8e");
    glow.addColorStop(1, "rgba(255,70,105,0)");
    context.fillStyle = glow;
    context.beginPath();
    context.arc(655, y, 40, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#ff5578";
    context.beginPath();
    context.arc(655, y, 23, 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = "#ffd9e0";
    context.lineWidth = 3;
    context.stroke();
  }
}

function render() {
  if (!session) return;
  const state = session.getState();
  const player = state.game_state.player;
  const checkpoint = state.game_state.checkpoint;
  const triad = state.game_state.triad;

  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#0b1822";
  context.fillRect(0, 0, canvas.width, canvas.height);

  context.fillStyle = "#102734";
  roundedRect(28, 150, 944, 330, 24);
  context.fill();
  context.strokeStyle = "#285061";
  context.lineWidth = 2;
  context.stroke();

  for (const [slot, y] of Object.entries(lanes)) {
    context.strokeStyle = `${laneColors[slot]}33`;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(52, y);
    context.lineTo(952, y);
    context.stroke();
  }

  context.fillStyle = "#12313a";
  context.fillRect(397, 170, 82, 290);
  context.strokeStyle = checkpoint.active ? "#58e8c9" : "#526e79";
  context.lineWidth = checkpoint.active ? 5 : 2;
  context.strokeRect(397, 170, 82, 290);
  context.fillStyle = checkpoint.active ? "rgba(88,232,201,0.16)" : "rgba(82,110,121,0.08)";
  context.fillRect(397, 170, 82, 290);
  context.fillStyle = checkpoint.active ? "#a8ffe6" : "#718d98";
  context.font = "800 12px ui-sans-serif, system-ui";
  context.fillText(checkpoint.active ? "SHELTER ACTIVE" : "MIDPOINT SHELTER", 377, 506);

  for (const slot of Object.keys(lanes)) {
    drawLane(slot, triad.panel_open === slot, triad.field_open === slot);
  }

  drawPrism(300, 385, session.tokens[0]);
  drawPrism(825, 215, session.tokens[1]);

  context.fillStyle = session.tokens.every(Boolean) ? "#63efc4" : "#4a6874";
  roundedRect(930, 185, 22, 230, 9);
  context.fill();
  context.fillStyle = session.tokens.every(Boolean) ? "#d8fff1" : "#78939d";
  context.fillText("EXIT", 916, 442);

  if (checkpoint.active && routeCard.complete) {
    context.drawImage(routeCard, 545, 26, 330, 96);
  } else {
    context.fillStyle = "#6d8a96";
    context.fillText("Activate the midpoint shelter to reveal the handoff card", 552, 82);
  }

  context.save();
  context.translate(player.x, player.y);
  context.fillStyle = player.flash > 0 ? "#ffffff" : "#63c8ff";
  context.shadowColor = player.flash > 0 ? "#ff5578" : "#63c8ff";
  context.shadowBlur = 18;
  roundedRect(-13, -13, 26, 26, 7);
  context.fill();
  context.fillStyle = "#071018";
  context.fillRect(-4, -4, 8, 8);
  context.restore();

  context.fillStyle = "#dceff6";
  context.font = "800 15px ui-sans-serif, system-ui";
  context.fillText(`PRISMS ${state.metrics.tokens}/2`, 52, 104);
  context.fillText(`RETURNS ${state.metrics.deaths}`, 184, 104);
  context.fillStyle = checkpoint.active ? "#65edc9" : "#76929c";
  context.fillText(checkpoint.active ? "MIDPOINT SAVED" : "MIDPOINT INACTIVE", 326, 104);

  if (checkpoint.active) {
    const trail = triad.panel.trail;
    context.font = "800 11px ui-sans-serif, system-ui";
    context.fillStyle = "#7898a5";
    context.fillText("VISIBLE HANDOFF TRAIL", 548, 140);
    trail.forEach((slot, index) => {
      context.fillStyle = laneColors[slot];
      context.beginPath();
      context.arc(706 + index * 42, 136, 10, 0, Math.PI * 2);
      context.fill();
      if (index < trail.length - 1) {
        context.strokeStyle = "#6b8793";
        context.lineWidth = 2;
        context.beginPath();
        context.moveTo(718 + index * 42, 136);
        context.lineTo(733 + index * 42, 136);
        context.stroke();
      }
    });
  }

  if (player.respawning) {
    context.fillStyle = "rgba(3,8,12,0.62)";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#ffe6ec";
    context.font = "800 29px ui-sans-serif, system-ui";
    context.textAlign = "center";
    context.fillText("RETURNING TO SHELTER", 500, 318);
    context.textAlign = "start";
  }

  if (state.terminal.isTerminal) {
    context.fillStyle = "rgba(3,8,12,0.74)";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#bcffea";
    context.font = "800 34px ui-sans-serif, system-ui";
    context.textAlign = "center";
    context.fillText("WEAVE COMPLETE", 500, 300);
    context.font = "600 15px ui-sans-serif, system-ui";
    context.fillStyle = "#8db6c2";
    context.fillText("Press R to restart", 500, 336);
    context.textAlign = "start";
  }
}

function frame(now) {
  if (!session) return;
  if (previous === 0) previous = now;
  accumulator += Math.min(0.1, (now - previous) / 1000);
  previous = now;
  while (accumulator >= STEP) {
    session.update(STEP);
    accumulator -= STEP;
  }
  render();
  requestAnimationFrame(frame);
}

window.addEventListener("keydown", (event) => {
  if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
    event.preventDefault();
  }
  session?.keyDown(event.key);
});
window.addEventListener("keyup", (event) => session?.keyUp(event.key));
window.addEventListener("blur", () => session?.keys.clear());

window.gameBoot = {status: "loading"};
renderStartup("PREPARING TRANSIT", "Loading protected route data through this application…");

try {
  const [ticket, card] = await Promise.all([fetchTicket(), loadRouteCard()]);
  session = new Session(ticket, 2903, 1);
  routeCard = card;
  window.gameAPI = {
    getState: () => session.getState(),
    reset: ({seed = 2903, level = 1} = {}) => {
      session.seed = Number(seed) || 2903;
      session.setLevel(level);
      return session.getState();
    },
    setLevel: (level) => {
      session.setLevel(level);
      return session.getState();
    },
  };
  window.gameBoot.status = "ready";
  render();
  requestAnimationFrame(frame);
} catch (error) {
  window.gameBoot = {
    status: "failed",
    message: error instanceof Error ? error.message : "startup failed",
  };
  renderStartup("TRANSIT UNAVAILABLE", "Protected route data could not be loaded.", true);
}
