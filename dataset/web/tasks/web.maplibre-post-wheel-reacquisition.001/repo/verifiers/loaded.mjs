// This function executes as protected read-only observation code in the page.
// Inspect actual raw Terrarium bytes, source IDs and renderable mesh IDs; neither
// a production height sampler nor a page's success field establishes coverage.
export function loadedSupport() {
 const t=lab.map.terrain;
 if(!t) return [];
 const tm=t.tileManager, plateau=tm.tileManager._source.maxzoom===0;
 if(t.exaggeration!==1 || t.meshSize!==128) throw Error('Coverage calibration: unexpected mesh');
 const sources=tm.tileManager._inViewTiles.getAllTiles().filter(s=>s.dem);
 const good=[];
 for(const s of sources) {
  const id=s.tileID.canonical, d=s.dem;
  if(d.dim!==512 || d.stride!==514 || (plateau?id.z!==0:id.z!==12)) continue;
  const bytes=new Uint8Array(d.data.buffer,d.data.byteOffset,d.data.byteLength);
  let valid=true;
  // Include the padded samples used at mesh edges. All rows, not a height verdict.
  for(let y=0;y<=512 && valid;y++) for(let x=0;x<=512;x++) {
   const i=((y+1)*514+x+1)*4, z=bytes[i]*256+bytes[i+1]+bytes[i+2]/256-32768;
   const xx=(id.x+x/512)/2**id.z;
   const expected=plateau?1000:1400-1000*Math.max(0,Math.min(1,(xx-.520782470703125)/.0000152587890625));
   if(z!==expected) {valid=false;break;}
  }
  if(valid) good.push({id,wrap:s.tileID.wrap});
 }
 const support=[];
 for(const key of tm._renderableTilesKeys) {
  const tile=tm._tiles[key], id=tile.tileID.canonical, wrap=tile.tileID.wrap;
  if(id.z!==12) continue;
  const n=2**id.z, rect=[id.x/n+wrap,(id.x+1)/n+wrap,id.y/n,(id.y+1)/n];
  // Adjacent DEM padding has already been validated. Only fully covered mesh
  // tiles count. Mesh topology is the fixed NW-SE 128-cell grid inspected in source.
  if(good.some(s=>rect[0]>=s.id.x/2**s.id.z+s.wrap && rect[1]<=(s.id.x+1)/2**s.id.z+s.wrap && rect[2]>=s.id.y/2**s.id.z && rect[3]<=(s.id.y+1)/2**s.id.z)) support.push(rect);
 }
 return support;
}
