export function compileQuery(query) {
  return {metric: query.metric, operator: query.operator, threshold: Number(query.threshold)};
}
