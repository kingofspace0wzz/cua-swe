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
