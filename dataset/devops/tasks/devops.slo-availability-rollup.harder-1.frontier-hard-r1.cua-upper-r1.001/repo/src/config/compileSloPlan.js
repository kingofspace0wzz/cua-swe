function compileRollup(rollup) {
  return {
    mode: "mean_of_slices",
    weight: rollup.weight || null,
    includeIds: rollup.includeIds || null,
    minimumTotal: rollup.minimumTotal || 0,
  };
}

export function compileSloPlan(definition) {
  return {
    availability: compileRollup(definition.availability),
    budget: compileRollup(definition.budget),
  };
}

export function compileDeploymentSchedule(revisions) {
  return revisions.map((entry) => ({
    epoch: entry.epoch,
    windows: Object.fromEntries(
      Object.entries(entry.windows || {}).map(([scope, rollups]) => [
        scope,
        {
          availability: compileRollup(rollups.availability),
          budget: compileRollup(rollups.budget),
        },
      ]),
    ),
  }));
}
