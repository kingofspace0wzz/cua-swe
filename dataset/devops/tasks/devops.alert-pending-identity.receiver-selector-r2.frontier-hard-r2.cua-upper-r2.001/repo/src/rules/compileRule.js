import {compileQuery} from './query.js';

export function compileRule(rule) {
  const labels = {...rule.labels};
  const annotations = {...rule.annotations};
  for (const field of rule.enrichments || []) {
    labels[field.name] = field.template;
  }
  return {
    name: rule.name,
    query: compileQuery(rule.query),
    forSeconds: rule.forSeconds,
    labels,
    annotations,
  };
}
