export function compileInhibitionRule(catalog, policy) {
  return {
    source_matchers: [
      {
        label: "alertname",
        operator: "=",
        value: policy.sourceClass,
      },
    ],
    target_matchers: [
      {
        label: "alertname",
        operator: "=~",
        value: ".*",
      },
    ],
    equal: [...catalog.equalDimensions],
    required_source_labels: [],
    required_target_labels: [],
  };
}
