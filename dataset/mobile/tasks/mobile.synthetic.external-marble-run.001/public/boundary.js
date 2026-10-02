// Legacy office records: x/right and y/down in board cells, real seconds.
// pace is seconds per cell; a material ratio is a velocity multiplier.
// This adapter isolates the renderer, engine and editor from transport records.
export function importPlan(record) {
  return {
    nodes: record.nodes.map(n => ({id:n.id, x:n.x, y:n.y})),
    speed: 1 / record.launch.pace, release: record.launch.release,
    material: record.launch.material,
    materials: record.materials.map(m => ({id:m.id, factor:m.ratio})),
    events: record.events.map(e => ({...e}))
  };
}
export function exportPlan(record, plan) {
  const next = structuredClone(record);
  next.nodes = record.nodes.map(n => {
    const edit = plan.nodes.find(p => p.id === n.id);
    return {...n, x:edit.x, y:edit.y};
  });
  next.launch = {...record.launch, pace:1 / plan.speed, release:plan.release};
  return next;
}
