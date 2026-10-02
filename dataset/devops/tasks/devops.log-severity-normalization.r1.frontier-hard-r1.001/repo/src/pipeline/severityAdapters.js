const bands = ['TRACE','DEBUG','INFO','WARN','ERROR','FATAL'];
const aliases = {TRACE:'TRACE',DEBUG:'DEBUG',INFO:'INFO',INFORMATION:'INFO',INFORMATIONAL:'INFO',NOTICE:'INFO',WARN:'WARN',WARNING:'WARN',ERROR:'ERROR',ERR:'ERROR',FATAL:'FATAL',CRITICAL:'FATAL',CRIT:'FATAL'};
export function fromText(text) {
  const band = aliases[String(text ?? '').trim().toUpperCase()] ?? 'UNSPECIFIED';
  return {band, number:band === 'UNSPECIFIED' ? 0 : bands.indexOf(band)*4+1};
}
export function fromOtel(record) {
  const number = Number(record.severityNumber ?? 0);
  if (Number.isInteger(number) && number >= 1 && number <= 24) return {number,band:bands[Math.floor((number-1)/4)]};
  return fromText(record.severityText);
}
export function fromJson(record) {
  let body = record.body;
  if (typeof body === 'string') {try {body=JSON.parse(body);} catch {body={};}}
  return fromText(body?.level);
}
export const severityAdapters = {otlp:fromOtel,json:fromJson};
