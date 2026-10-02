import {startLogService} from '../repo/verifiers/log_service.mjs';
const options={};for(let i=2;i<process.argv.length;i++)if(process.argv[i].startsWith('--'))options[process.argv[i].slice(2)]=process.argv[++i];startLogService(options).then(({address})=>console.log('log receiver '+address.port));
