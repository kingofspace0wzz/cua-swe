// Generic received-image viewer. It contains no reference layouts or picture bytes.
export function attachViewer(root) {
  let scale=1, sheet=null, drag=null;
  const port=root.querySelector('.sheet-port'), img=port.querySelector('img');
  const status=root.querySelector('.zoom-status');
  function fit(){scale=1;paint();port.scrollTo(0,0);}
  function paint(){img.style.width=(100*scale)+'%';status.textContent=Math.round(scale*100)+'% of phone fit';}
  root.querySelector('[data-zoom="in"]').onclick=()=>{scale=Math.min(5,scale*1.6);paint();};
  root.querySelector('[data-zoom="out"]').onclick=()=>{scale=Math.max(1,scale/1.6);paint();};
  root.querySelector('[data-zoom="fit"]').onclick=fit;
  port.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,left:port.scrollLeft,top:port.scrollTop};port.setPointerCapture(e.pointerId);});
  port.addEventListener('pointermove',e=>{if(drag){port.scrollLeft=drag.left+drag.x-e.clientX;port.scrollTop=drag.top+drag.y-e.clientY;}});
  for(const name of ['pointerup','pointercancel'])port.addEventListener(name,()=>drag=null);
  img.draggable=false;
  return {show(next){if(sheet!==next){sheet=next;img.src=next.image;img.alt=next.title+' — original maker attachment';fit();}}};
}
