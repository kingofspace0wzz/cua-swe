export function contextCompatibilityPolicy(catalog) {
  return Object.freeze({
    profileLabel: catalog.label,
    contextManager: catalog.contextManager,
    asyncSemantics: "native",
    propagationStrategy: "manager",
  });
}
