export function selectRecords(records,receiverId,filter) {
  return records.filter(record=>record.receiverId===receiverId && (filter==='all' || ['ERROR','FATAL'].includes(record.severity.band)));
}
