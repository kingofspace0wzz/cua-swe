// Rectilinear spherical camera. All angles here are in the panorama's own grid.
export const wrap = n => ((n % 360) + 360) % 360;
const rad = n => n * Math.PI / 180;
const deg = n => n * 180 / Math.PI;
export const HORIZONTAL_FOV = 72;
export function basis(view) {
  const y=rad(view.heading), p=rad(view.elevation);
  return {
    right:[Math.cos(y),0,-Math.sin(y)],
    up:[-Math.sin(y)*Math.sin(p),Math.cos(p),-Math.cos(y)*Math.sin(p)],
    forward:[Math.sin(y)*Math.cos(p),Math.sin(p),Math.cos(y)*Math.cos(p)]
  };
}
const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
export function direction(point) {
  const y=rad(point.yaw),p=rad(point.pitch);
  return [Math.sin(y)*Math.cos(p),Math.sin(p),Math.cos(y)*Math.cos(p)];
}
export function project(point,view,width,height) {
  const b=basis(view),v=direction(point),z=dot(v,b.forward);
  if(z<=0) return null;
  const f=width/(2*Math.tan(rad(HORIZONTAL_FOV/2)));
  const x=width/2+f*dot(v,b.right)/z, y=height/2-f*dot(v,b.up)/z;
  return x>=0 && x<=width && y>=0 && y<=height ? {x,y} : null;
}
export function unproject(x,y,view,width,height) {
  const b=basis(view),f=width/(2*Math.tan(rad(HORIZONTAL_FOV/2)));
  const rx=(x-width/2)/f,ry=(height/2-y)/f;
  const v=b.forward.map((n,i)=>n+rx*b.right[i]+ry*b.up[i]);
  return {yaw:wrap(deg(Math.atan2(v[0],v[2]))),pitch:deg(Math.atan2(v[1],Math.hypot(v[0],v[2])))};
}
