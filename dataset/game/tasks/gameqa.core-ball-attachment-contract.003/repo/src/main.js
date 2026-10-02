import {Game} from './game.js';

const canvas = document.querySelector('#game');
const overlay = document.querySelector('#overlay');
const overlayMessage = document.querySelector('#overlay-message');
const startButton = document.querySelector('#start');
const restartButton = document.querySelector('#restart');
const status = document.querySelector('#status');
const remaining = document.querySelector('#remaining');
const pace = document.querySelector('#pace');
const paceFill = document.querySelector('#pace-fill');
const queueCue = document.querySelector('#queue-cue');
const queueState = document.querySelector('#queue-state');

const ui = {
  hideOverlay() {
    overlay.className = 'overlay hidden';
  },
  showReady() {
    overlay.className = 'overlay';
    overlayMessage.textContent = 'Place every pin without touching another.';
    startButton.textContent = 'START ROUND';
    status.textContent = 'Ready';
  },
  showFailure() {
    overlay.className = 'overlay fail';
    overlayMessage.textContent = 'Pins collided. Try the sequence again.';
    startButton.textContent = 'TRY AGAIN';
    status.textContent = 'Attachment collision';
  },
  showPass() {
    overlay.className = 'overlay pass';
    overlayMessage.textContent = 'All pins attached.';
    startButton.textContent = 'PLAY AGAIN';
    status.textContent = 'Round clear';
  },
  setStatus(message) {
    status.textContent = message;
  },
  update(state) {
    remaining.textContent = String(state.round.remaining).padStart(2, '0');
    const progress = state.motion.transition.progress;
    paceFill.style.width = `${12 + progress * 88}%`;
    pace.textContent = state.motion.transition.active ? 'SHIFTING' : progress === 1 ? 'FAST' : 'STEADY';
    const queued = state.shots.waiting === 1;
    queueCue.className = queued ? 'queue-cue loaded' : 'queue-cue';
    queueState.textContent = queued ? 'NEXT PIN READY' : state.shots.active ? 'TAP TO QUEUE' : 'QUEUE OPEN';
  },
};

const game = new Game(canvas, ui);

function restart() {
  game.reset({seed: game.seed, level: game.level, manual: game.manual});
}

canvas.addEventListener('pointerdown', (event) => {
  event.preventDefault();
  game.fire();
});
startButton.addEventListener('click', () => {
  if (game.phase === 'failed' || game.phase === 'passed') restart();
  game.start();
});
restartButton.addEventListener('click', restart);
window.addEventListener('keydown', (event) => {
  if (event.code === 'Space') {
    event.preventDefault();
    game.fire();
  }
  if (event.code === 'KeyR') restart();
});

const replay = (actions) => {
  if (!Array.isArray(actions) || actions.length > 40) throw new Error('Replay is out of bounds');
  const output = [];
  for (const action of actions) {
    if (action.type === 'start') game.start();
    else if (action.type === 'fire') game.fire();
    else if (action.type === 'advance') game.advance(Math.min(30000, Math.max(0, action.ms)));
    else if (action.type === 'reset') game.reset({seed: action.seed, level: action.level, manual: true});
    else throw new Error('Unknown replay action');
    output.push(game.getState());
  }
  return output;
};

window.gameAPI = {
  reset: (options = {}) => game.reset({...options, manual: options.manual !== false}),
  start: () => game.start(),
  advance: (durationMs) => game.advance(durationMs),
  getState: () => game.getState(),
  replay,
};
