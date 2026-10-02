// Local imported-provider transport. The isolated demo receives its inbox from
// runtime setup. No demo payload is bundled. This is response replay, not a real
// network or cryptographic validator. Matching is generic; content is external.
const KEY = 'civic-gate-import';
export function readInbox() {
  const raw = localStorage.getItem(KEY);
  return raw ? JSON.parse(raw) : null;
}
export function saveInbox(inbox) { localStorage.setItem(KEY, JSON.stringify(inbox)); }
function same(a,b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(k => Object.hasOwn(b,k) && same(a[k],b[k]));
}
export function validate(inbox, pass, request) {
  const envelopes = pass.provider.exchanges;
  const next = envelopes[0];
  let receipt;
  if (next && same(next.request,request)) {
    const response = envelopes.shift().response;
    receipt = structuredClone(response.receipt);
    if (response.record) pass.issuerRecord = structuredClone(response.record);
  } else {
    receipt = {...structuredClone(pass.provider.refusal), request:structuredClone(request)};
  }
  pass.receipts.unshift(receipt);
  saveInbox(inbox);
  return receipt;
}
