import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const {PNG}=createRequire(import.meta.url)('pngjs');
// Independent PNG decoding (CRC checked by pngjs), then exact Terrarium integers.
export function validateAssets() {
 const evidence=[];
 for(const name of ['plateau',...Array.from({length:41},(_,i)=>2113+i)]) {
  const data=readFileSync(new URL(`../runtime-task/assets/${name}.png`,import.meta.url)), p=PNG.sync.read(data,{checkCRC:true});
  if(p.width!==512||p.height!==512)throw Error('Unexpected DEM extent');
  for(let y=0;y<512;y++)for(let x=0;x<512;x++) {
   const i=(y*512+x)*4, z=p.data[i]*256+p.data[i+1]+p.data[i+2]/256-32768, xx=(Number(name)+x/512)/4096;
   const expected=name==='plateau'?1000:1400-1000*Math.max(0,Math.min(1,(xx-.520782470703125)/.0000152587890625));
   if(z!==expected||p.data[i+3]!==255)throw Error(`Fixture DEM disagreement ${name}/${x}/${y}`);
  }
  evidence.push({name,sha256:createHash('sha256').update(data).digest('hex'),pixels:512*512});
 }
 return {evidence,slopeDEMcells:32,slopeMeshCells:8,meshCell:2**-19};
}
