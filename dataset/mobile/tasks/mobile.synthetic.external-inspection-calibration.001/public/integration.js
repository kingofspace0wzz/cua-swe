// Client compatibility path for unregistered inspection attachments.
// The viewer displays the imported original and report without client conversion.
export function project(point,record){return [...point];}
export function unproject(point,record){return [...point];}
export function measure(points,record){
 const [a,b]=points;
 return Math.hypot(b[0]-a[0],b[1]-a[1]);
}
