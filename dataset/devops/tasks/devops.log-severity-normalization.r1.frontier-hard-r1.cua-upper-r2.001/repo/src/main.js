import {start} from './controllers/console.js';
start(document.querySelector('#app')).catch(error=>{document.querySelector('#app').textContent='Receiver unavailable: '+error.message;});
