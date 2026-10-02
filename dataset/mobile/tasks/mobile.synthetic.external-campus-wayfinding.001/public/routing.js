// Schematic connector projection and shortest trip.
export function route(campus, origin, destination, stepFree) {
  const vertices = new Map(campus.stops.map(stop => [stop.id, []]));
  for (const link of campus.walk_links) {
    if (stepFree && link.kind === 'stairs') continue;
    if (!vertices.has(link.from_stop) || !vertices.has(link.to_stop)) continue;
    const distance = Number(link.plan_m);
    if (!Number.isFinite(distance) || distance < 0) continue;
    vertices.get(link.from_stop).push({to:link.to_stop, link, distance});
    vertices.get(link.to_stop).push({to:link.from_stop, link, distance});
  }
  if (!vertices.has(origin) || !vertices.has(destination)) return null;
  const costs = new Map([[origin, 0]]), previous = new Map(), pending = new Set(vertices.keys());
  while (pending.size) {
    let current;
    for (const id of pending) if (costs.has(id) && (current === undefined || costs.get(id) < costs.get(current))) current = id;
    if (current === undefined) break;
    pending.delete(current);
    if (current === destination) break;
    for (const arc of vertices.get(current)) {
      const candidate = costs.get(current) + arc.distance;
      if (candidate < (costs.get(arc.to) ?? Infinity)) {
        costs.set(arc.to, candidate);
        previous.set(arc.to, {from:current, to:arc.to, link:arc.link, distance:arc.distance});
      }
    }
  }
  if (!costs.has(destination)) return null;
  const legs = [];
  for (let cursor = destination; cursor !== origin;) {
    const leg = previous.get(cursor);
    if (!leg) return null;
    legs.unshift(leg); cursor = leg.from;
  }
  return {distance:costs.get(destination), stops:[origin, ...legs.map(leg => leg.to)], legs};
}
