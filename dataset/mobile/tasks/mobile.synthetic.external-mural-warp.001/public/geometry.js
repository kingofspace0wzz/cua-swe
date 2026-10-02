// Complete dependency-free planar geometry. Coordinates are mathematical inputs,
// not provider-specific fields. Homographies are row-major 3x3 matrices.
export const I = [1,0,0,0,1,0,0,0,1];
export function multiply(a,b) {
  return Array.from({length:9},(_,i)=>[0,1,2].reduce((s,k)=>s+a[3*Math.floor(i/3)+k]*b[3*k+i%3],0));
}
export function apply(h,[x,y]) {
  const d=h[6]*x+h[7]*y+h[8];
  if(Math.abs(d)<1e-12) throw Error('Point at projective infinity');
  return [(h[0]*x+h[1]*y+h[2])/d,(h[3]*x+h[4]*y+h[5])/d];
}
export function invert(m) {
  const [a,b,c,d,e,f,g,h,i]=m;
  const r=[e*i-f*h,c*h-b*i,b*f-c*e,f*g-d*i,a*i-c*g,c*d-a*f,d*h-e*g,b*g-a*h,a*e-b*d];
  const det=a*r[0]+b*r[3]+c*r[6];
  if(Math.abs(det)<1e-12) throw Error('Singular mapping');
  return r.map(v=>v/det);
}
export function solveLinear(rows,values) {
  const a=rows.map((r,i)=>[...r,values[i]]),n=a.length;
  for(let i=0;i<n;i++) {
    let pivot=i;for(let j=i+1;j<n;j++)if(Math.abs(a[j][i])>Math.abs(a[pivot][i]))pivot=j;
    [a[i],a[pivot]]=[a[pivot],a[i]];
    const d=a[i][i];if(Math.abs(d)<1e-12)throw Error('Degenerate control points');
    a[i]=a[i].map(v=>v/d);
    for(let j=0;j<n;j++)if(i!==j){const k=a[j][i];a[j]=a[j].map((v,c)=>v-k*a[i][c]);}
  }
  return a.map(r=>r[n]);
}
export function homography(source,destination) {
  if(source.length!==4||destination.length!==4)throw Error('Four paired controls required');
  const rows=[],values=[];
  source.forEach(([x,y],i)=>{const [u,v]=destination[i];rows.push([x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]);values.push(u,v);});
  return [...solveLinear(rows,values),1];
}
export function normalizeWindow([x,y,w,h]) {return [1/w,0,-x/w,0,1/h,-y/h,0,0,1];}
export function orientation(turns,reflectU) {
  let m=reflectU?[-1,0,1,0,1,0,0,0,1]:[...I];
  for(let i=0;i<((turns%4)+4)%4;i++)m=multiply([0,-1,1,1,0,0,0,0,1],m);
  return m;
}
export function inWindow([x,y],[a,b,w,h]) {return x>=a-1e-7&&x<=a+w+1e-7&&y>=b-1e-7&&y<=b+h+1e-7;}
export function contains([x,y],poly) {
  let inside=false;
  for(let i=0,j=poly.length-1;i<poly.length;j=i++) {
    const [ax,ay]=poly[j],[bx,by]=poly[i],cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax);
    if(Math.abs(cross)<1e-6&&x>=Math.min(ax,bx)-1e-7&&x<=Math.max(ax,bx)+1e-7&&y>=Math.min(ay,by)-1e-7&&y<=Math.max(ay,by)+1e-7)return true;
    if((ay>y)!==(by>y)&&x<(bx-ax)*(y-ay)/(by-ay)+ax)inside=!inside;
  }
  return inside;
}
export function clipPolygon(subject,clip) {
  let area=0;clip.forEach((p,i)=>{const q=clip[(i+1)%clip.length];area+=p[0]*q[1]-q[0]*p[1];});
  const sign=area>=0?1:-1;
  for(let i=0;i<clip.length&&subject.length;i++) {
    const a=clip[i],b=clip[(i+1)%clip.length];
    const side=p=>sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]));
    const out=[];
    for(let k=0;k<subject.length;k++) {
      const s=subject[(k+subject.length-1)%subject.length],e=subject[k],ds=side(s),de=side(e);
      if((ds>=0)!==(de>=0)){const t=ds/(ds-de);out.push([s[0]+t*(e[0]-s[0]),s[1]+t*(e[1]-s[1])]);}
      if(de>=0)out.push(e);
    }
    subject=out;
  }
  return subject;
}
export function windowPolygon([x,y,w,h]) {return [[x,y],[x+w,y],[x+w,y+h],[x,y+h]];}
