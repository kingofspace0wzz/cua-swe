import {cp, mkdir} from 'node:fs/promises';
await mkdir('dist',{recursive:true});
await cp('index.html','dist/index.html');
await cp('src','dist/src',{recursive:true});
console.log('log workbench build complete');
