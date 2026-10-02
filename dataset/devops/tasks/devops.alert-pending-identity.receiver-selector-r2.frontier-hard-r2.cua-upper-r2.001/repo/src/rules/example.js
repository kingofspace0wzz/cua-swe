// Illustrative import shape; live rules are supplied by the evaluator.
export const example = {
  name: 'QueueBacklog',
  family: 'standby',
  query: {metric: 'queue_depth', operator: '>', threshold: 40},
  forSeconds: 180,
  labels: {severity: 'warning'},
  annotations: {summary: 'Queue backlog on {{ $labels.instance }}'},
  enrichments: [
    {name: 'team', template: 'fulfillment'},
    {name: 'relay_bay', template: '{{ $route.bay }}'},
  ],
};
