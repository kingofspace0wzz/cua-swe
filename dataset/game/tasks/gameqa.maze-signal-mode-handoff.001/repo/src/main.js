import {SignalMaze} from './game.js';

const root = document.querySelector('#maze');
const message = document.querySelector('#message');

try {
  const scenarioUrl = window.location.protocol === 'file:' ?
      './scenario.json' : '/api/scenario';
  const response = await fetch(scenarioUrl, {cache: 'no-store'});
  if (!response.ok) throw new Error(`scenario request failed: ${response.status}`);
  const config = await response.json();
  const game = new SignalMaze(root, config);
  window.gameAPI = Object.freeze({
    getState: () => game.getState(),
    reset: () => game.reset(),
  });
} catch (error) {
  message.textContent = `Unable to load route: ${error.message}`;
  message.className = 'message hit';
}
