// Timing contract is generic; imported exposures are product data.
export function total(settings){return settings.exposures.reduce((s,n,i)=>s+n+settings.holds[i],0);}
export function normalize(frame,length,loop){return loop?((frame%length)+length)%length:Math.max(0,Math.min(length-1,frame));}
export function sample(settings,frame,loop=false){
 const length=total(settings),time=normalize(frame,length,loop);let start=0;
 for(let i=0;i<settings.exposures.length;i++){
  const exposure=settings.exposures[i]+settings.holds[i];
  if(time<start+exposure)return {beat:i,start,end:start+exposure,exposure,time,length};
  start+=exposure;
 }
 throw new Error('Invalid imported timing');
}
export function defaults(clip){return {exposures:[...clip.exposures],holds:[...clip.holds],start:0,rate:1};}
