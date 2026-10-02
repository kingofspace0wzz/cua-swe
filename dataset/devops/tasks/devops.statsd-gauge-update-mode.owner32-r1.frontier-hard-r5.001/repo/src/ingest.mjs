import {decodeDatagram} from './protocol.mjs';
import {applyGauge} from './update.mjs';
export function ingestCapture(receipt, state) {
  return decodeDatagram(Buffer.from(receipt.base64, 'base64')).map(measurement => {
    const result = applyGauge(state, {...measurement, source: receipt.source});
    return {receipt: receipt.sequence, lineIndex: measurement.lineIndex,
      identity: measurement.identity, source: receipt.source, token: measurement.token,
      metricType: measurement.metricType, parsedValue: measurement.value,
      value: result.value};
  });
}
