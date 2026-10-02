import {resolveSeverity} from './resolveSeverity.js';
export function createIngestor(receivers) {
  const inventory = new Map(receivers.map(receiver=>[receiver.id,receiver]));
  const seen = new Set();
  const records = [];
  return {
    accept(batch) {
      if(seen.has(batch.deliveryId)) return false;
      const receiver=inventory.get(batch.receiverId);
      if(!receiver) throw new Error('Unknown receiver');
      for(const record of batch.records) records.push({
        deliveryId:batch.deliveryId, receiverId:batch.receiverId,
        raw:structuredClone(record), severity:resolveSeverity(record,receiver),
      });
      seen.add(batch.deliveryId);
      return true;
    },
    snapshot() {return {records:structuredClone(records),accepted:[...seen]};},
  };
}
