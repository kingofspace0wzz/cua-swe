import {startSamplerService} from "../repo/verifiers/sampler_service.mjs";
const options={};for(let i=2;i<process.argv.length;i++){if(process.argv[i]==="--port")options.port=Number(process.argv[++i]);else if(process.argv[i]==="--host")options.host=process.argv[++i];else if(process.argv[i]==="--profile")options.profile=process.argv[++i];}
startSamplerService(options).then(({address})=>console.log(`sampler service on ${address.address}:${address.port}`));
