export function compileRuntimeProfile(policy) {
  return {
    context_manager: policy.contextManager,
    async_semantics: "native",
    propagation_strategy: policy.propagationStrategy,
  };
}
