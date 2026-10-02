// Projection Office v1 inline placement adapter. The v1 exporter supplied crop
// in artwork pixels, and placement as the corresponding wall TL/TR/BR/BL corners.
// Local coordinates were normalized crop coordinates; station units equaled wall
// units. Array order broke shared-edge ties. The rest of the app consumes matrices
// and domains, so forward rendering and inverse edits share this boundary.
import {homography,normalizeWindow,multiply,invert,I} from './geometry.js';
export function importMapping(packet) {
  const panels=packet.panels.map(p=>{
    const sourceWindow=p.crop,sourceToLocal=normalizeWindow(sourceWindow);
    const localToStation=homography([[0,0],[1,0],[1,1],[0,1]],p.placement);
    const stationToWall=[...I],sourceToWall=multiply(localToStation,sourceToLocal);
    return {id:p.id,sourceWindow,sourceToLocal,localToStation,stationToWall,sourceToWall,wallToSource:invert(sourceToWall)};
  });
  return {panels,priority:packet.panels.map(p=>p.id)};
}
