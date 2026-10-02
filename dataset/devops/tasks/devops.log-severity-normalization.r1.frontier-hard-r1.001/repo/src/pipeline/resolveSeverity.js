import {severityAdapters} from './severityAdapters.js';

export function resolveSeverity(record, receiver) {
  const format = receiver.source.format;
  const decode = severityAdapters[format];
  return decode ? decode(record) : {number:0, band:'UNSPECIFIED'};
}
