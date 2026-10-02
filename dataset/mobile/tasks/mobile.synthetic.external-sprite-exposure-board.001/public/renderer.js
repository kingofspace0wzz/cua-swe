// The artist atlas is external input. No builtin sprites or fallback performance.
const images=new Map();
export async function loadSheets(edition){await Promise.all(edition.sheets.map(s=>new Promise((resolve,reject)=>{
 const key=edition.id+'/'+s.id;if(images.has(key))return resolve();
 const im=new Image();im.onload=()=>{images.set(key,im);resolve();};im.onerror=reject;im.src=s.image;
})));}
export function drawCel(canvas,edition,pose){
 const c=canvas.getContext('2d'),{width:w,height:h}=edition.stage;
 canvas.width=w*2;canvas.height=h*2;c.scale(2,2);c.clearRect(0,0,w,h);
 const cel=edition.cels.find(x=>x.id===pose.cel),image=cel&&images.get(edition.id+'/'+cel.sheet);
 if(!image)return;
 c.save();if(pose.facing==='left'){c.translate(w,0);c.scale(-1,1);}
 c.drawImage(image,...cel.rect,0,0,w,h);c.restore();
}
