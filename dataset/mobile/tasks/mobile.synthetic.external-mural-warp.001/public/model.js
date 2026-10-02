import {apply,contains,inWindow,clipPolygon,windowPolygon} from './geometry.js';
export function panelMap(mapping,id){return mapping.panels.find(p=>p.id===id);}
export function visible(panel,point){return contains(point,panel.displayPolygon)&&!panel.obstructions.some(h=>contains(point,h));}
export function owner(packet,mapping,wall) {
  for(const id of mapping.priority){
    const p=packet.panels.find(p=>p.id===id),m=panelMap(mapping,id);
    if(visible(p,wall)&&inWindow(apply(m.wallToSource,wall),m.sourceWindow))return id;
  }
  return null;
}
export function wallPin(packet,mapping,pin) {
  const m=panelMap(mapping,pin.panelId),wall=apply(m.sourceToWall,pin.source);
  return inWindow(pin.source,m.sourceWindow)&&owner(packet,mapping,wall)===pin.panelId?wall:null;
}
export function moveFromWall(packet,mapping,pin,wall) {
  if(!wall.every(Number.isFinite))return null;
  const panelId=owner(packet,mapping,wall);if(!panelId)return null;
  return {...pin,panelId,source:apply(panelMap(mapping,panelId).wallToSource,wall)};
}
export function moveFromSource(packet,mapping,pin,source) {
  if(!source.every(Number.isFinite))return null;
  const result={...pin,source};return wallPin(packet,mapping,result)?result:null;
}
export function artworkPolygons(packet,mapping) {
  return packet.panels.map(panel=>{
    const m=panelMap(mapping,panel.id);
    const shapes=packet.artwork.shapes.map(shape=>({color:shape.color,name:shape.name,
      points:clipPolygon(clipPolygon(shape.points,windowPolygon(m.sourceWindow)).map(p=>apply(m.sourceToWall,p)),panel.displayPolygon)}));
    return {panel,shapes};
  });
}
export function serializePins(mapping,pins) {
  return pins.map(pin=>{
    const m=panelMap(mapping,pin.panelId),local=apply(m.sourceToLocal,pin.source),station=apply(m.localToStation,local);
    return {id:pin.id,label:pin.label,panelId:pin.panelId,source:[...pin.source],local,station};
  });
}
