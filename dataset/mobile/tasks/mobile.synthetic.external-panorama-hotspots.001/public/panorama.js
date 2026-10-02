import {unproject,wrap} from './geometry.js';
const images=new Map();
export async function loadPanorama(record) {
  const url=record.panorama.dataUrl;
  if(!images.has(url)) images.set(url,new Promise((resolve,reject)=>{
    const image=new Image();
    image.onload=()=>{
      const c=document.createElement('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;
      const g=c.getContext('2d',{willReadFrequently:true});g.drawImage(image,0,0);
      resolve({pixels:g.getImageData(0,0,c.width,c.height).data,width:c.width,height:c.height});
    };
    image.onerror=()=>reject(new Error('Imported panorama could not be decoded'));
    image.src=url;
  }));
  return images.get(url);
}
function sample(source,output,i,yaw,pitch) {
  const x=Math.floor(wrap(yaw)/360*source.width)%source.width;
  const y=Math.max(0,Math.min(source.height-1,Math.floor((90-pitch)/180*source.height)));
  const j=(y*source.width+x)*4;
  output[i]=source.pixels[j];output[i+1]=source.pixels[j+1];output[i+2]=source.pixels[j+2];output[i+3]=255;
}
export function renderWindow(canvas,source,view) {
  const w=canvas.width,h=canvas.height,g=canvas.getContext('2d');
  const result=g.createImageData(w,h);
  for(let y=0;y<h;y++) for(let x=0;x<w;x++) {
    const point=unproject(x+.5,y+.5,view,w,h);
    sample(source,result.data,(y*w+x)*4,point.yaw,point.pitch);
  }
  g.putImageData(result,0,0);
}
// Original attachment magnifier: a flat, wrapped strip, deliberately NOT a tour projection.
export function renderOriginalStrip(canvas,source,heading) {
  const w=canvas.width,h=canvas.height,g=canvas.getContext('2d'),out=g.createImageData(w,h);
  for(let y=0;y<h;y++) for(let x=0;x<w;x++)
    sample(source,out.data,(y*w+x)*4,heading+(x+.5-w/2)/4,(h/2-y-.5)/4);
  g.putImageData(out,0,0);
}
