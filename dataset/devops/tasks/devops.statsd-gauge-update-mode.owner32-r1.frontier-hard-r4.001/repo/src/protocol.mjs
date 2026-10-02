export function decodeDatagram(bytes) {
  const text = Buffer.isBuffer(bytes) ? bytes.toString('ascii') : String(bytes);
  const lines = text.split('\n');
  const measurements = [];
  for (const [lineIndex, line] of lines.entries()) {
    if (!line) continue;
    const match = /^([A-Za-z0-9_.-]+):([+-]?(?:\d+(?:\.\d*)?|\.\d+))\|(g)$/.exec(line);
    if (!match) throw new Error('Invalid gauge line');
    const [, identity, token, metricType] = match;
    const value = Number(token);
    if (!Number.isFinite(value)) throw new Error('Non-finite gauge value');
    measurements.push({identity, token, metricType, value, lineIndex});
  }
  return measurements;
}
