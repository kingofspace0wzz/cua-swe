// Mapping adapter for imported panel placement records.
export function toSheet(panel,u,v) {
  return {x:panel.placement.sheetOrigin.x+u,y:panel.placement.sheetOrigin.y+v};
}
export function toPanel(panel,x,y) {
  return {u:x-panel.placement.sheetOrigin.x,v:y-panel.placement.sheetOrigin.y};
}
export function sheetHeading(panel,heading) { return heading; }
export function reviewKey(proof,panel) { return panel.id; }
