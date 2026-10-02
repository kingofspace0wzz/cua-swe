import {initialize} from './controllers/console.js';
initialize().catch(error=>{document.querySelector('#app').textContent=String(error.message);});
