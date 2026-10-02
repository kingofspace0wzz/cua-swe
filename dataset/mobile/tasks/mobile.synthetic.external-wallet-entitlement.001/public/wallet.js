// Client-side admission interpretation. Provider transport and document rendering
// deliberately live in separate modules.
export function admission(record) {
  const row = record.printedSummary;
  const visits = Math.max(0, Number(row.remainingVisits) || 0);
  return {visits, state:row.state, enabled:row.state === 'active' && visits > 0,
    request:{passId:record.passId, entitlementId:row.entitlementId,
      revision:row.revision, debit:{quantity:1,unit:'visit'}}};
}
