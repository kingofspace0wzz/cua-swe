/** Durable binding to a deployed recording-rule definition.
 * The operator console lists the definitions deployed by the metrics service.
 */
export function queryPolicy() {
  return {
    pipeline: "traffic-window",
    panelScope: "all",
    sampleFilter: "none",
  };
}
