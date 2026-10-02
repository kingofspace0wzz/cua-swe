export function inhibitionScopePolicy(catalog) {
  return Object.freeze({
    profileLabel: catalog.label,
    scopeDimensions: catalog.equalDimensions,
    dimensionRegistry: catalog.dimensions.map((dimension) =>
      Object.freeze({ ...dimension }),
    ),
    sourceClass: catalog.sourceClass,
    targetClass: catalog.targetClass,
  });
}
