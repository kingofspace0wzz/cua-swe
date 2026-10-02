import {artworkPolygons,wallPin} from './model.js';
const path=(c,poly)=>{c.beginPath();poly.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();};
export function drawSource(canvas,packet) {
  const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);
  for(const shape of packet.artwork.shapes){path(c,shape.points);c.fillStyle=shape.color;c.fill();}
}
export function drawWall(canvas,packet,mapping,pins,selected) {
  const c=canvas.getContext('2d');c.fillStyle='#edf0f5';c.fillRect(0,0,canvas.width,canvas.height);
  for(const {panel,shapes} of artworkPolygons(packet,mapping)) {
    c.save();path(c,panel.displayPolygon);c.clip();
    // Even-odd subtract holes; this also supports overlapping drawing primitives.
    c.beginPath();for(const poly of [panel.displayPolygon,...panel.obstructions]){poly.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();}c.clip('evenodd');
    for(const shape of shapes)if(shape.points.length){path(c,shape.points);c.fillStyle=shape.color;c.fill();}
    c.restore();
    for(const hole of panel.obstructions){path(c,hole);c.fillStyle='#a7aeb8';c.fill();c.strokeStyle='#525d6a';c.lineWidth=1;c.stroke();}
    path(c,panel.displayPolygon);c.strokeStyle='#263348';c.lineWidth=1.5;c.stroke();
  }
  for(const pin of pins) {
    const wall=wallPin(packet,mapping,pin);if(!wall)continue;
    const [x,y]=wall;
    if(pin.id===selected){c.beginPath();c.arc(x,y,9,0,Math.PI*2);c.strokeStyle='#753fb5';c.lineWidth=2.5;c.stroke();}
    c.beginPath();c.arc(x,y,5,0,Math.PI*2);c.fillStyle='#111827';c.fill();
    c.beginPath();c.arc(x,y,2,0,Math.PI*2);c.fillStyle='#ffffff';c.fill();
  }
}
