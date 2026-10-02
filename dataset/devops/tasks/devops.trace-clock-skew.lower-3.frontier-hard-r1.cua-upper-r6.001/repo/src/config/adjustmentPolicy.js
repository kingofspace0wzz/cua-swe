export function adjustmentPolicy(catalog) {
  return Object.freeze({
    crossHostMode: "observe",
    maxAdjustmentMs: catalog.maxAdjustmentMs,
  });
}
