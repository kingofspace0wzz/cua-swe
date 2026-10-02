/**
 * Live center-cargo state supplied by the runtime service.
 * @type {{semanticKey: string, semanticUnits: number, visualUnits: number}}
 */
let centerCargoSnapshot = {
  semanticKey: 'fallback-center',
  semanticUnits: 1,
  visualUnits: 1,
};

/** @type {!Array.<string>} */
let cargoTraceLines = [];

/** @type {boolean} */
let cargoContractReady = false;

/**
 * Flattens an unknown runtime payload for the in-game cargo scanner.
 * @param {*} value
 * @param {string} path
 * @param {!Array.<string>} lines
 */
function flattenCargoTrace(value, path, lines) {
  if (value === null || typeof value !== 'object') {
    lines.push(path + '=' + String(value));
    return;
  }
  const objectValue = /** @type {!Object} */ (value);
  Object.keys(objectValue).forEach((key) => {
    const nextPath = path ? path + '.' + key : key;
    flattenCargoTrace(objectValue[key], nextPath, lines);
  });
}

/**
 * Finds record-shaped branches in an unknown cargo contract.
 * Presentation metadata is intentionally excluded.
 * @param {*} value
 * @param {string} path
 * @param {!Array.<!Object>} records
 */
function collectCargoRecords(value, path, records) {
  if (!value || typeof value !== 'object') {
    return;
  }
  const objectValue = /** @type {!Object} */ (value);
  if (!Array.isArray(objectValue) && path !== 'render') {
    const values = Object.values(objectValue);
    if (values.some((item) => typeof item === 'string') &&
        values.some((item) => typeof item === 'number')) {
      records.push(objectValue);
    }
  }
  Object.keys(objectValue).forEach((key) => {
    collectCargoRecords(
        objectValue[key], path ? path + '.' + key : key, records);
  });
}

/**
 * Uses the legacy first-record fallback for an unknown cargo contract.
 * @param {!Object} payload
 * @return {{semanticKey: string, semanticUnits: number, visualUnits: number}}
 */
function deriveCenterCargo(payload) {
  const records = [];
  collectCargoRecords(payload, '', records);
  const candidate = records[0] || {};
  const candidateValues = Object.values(candidate);
  const semanticKey = String(
      candidateValues.find((value) => typeof value === 'string') ||
      'fallback-center');
  const semanticUnits = Number(
      candidateValues.find((value) => typeof value === 'number') || 1);
  const render = payload['render'] || {};
  const visualUnits = Math.max(1, Number(render['count']) || 1);
  return {semanticKey, semanticUnits, visualUnits};
}

/**
 * Loads the protected cargo contract through the public application.
 * @return {!Promise<void>}
 */
async function loadCargoContract() {
  const scenario = new URLSearchParams(window.location.search).get('scenario') ||
      'primary';
  cargoContractReady = false;
  const response = await fetch(
      '/api/cargo-manifest?scenario=' + encodeURIComponent(scenario));
  if (!response.ok) {
    throw new Error('Cargo contract unavailable');
  }
  const payload = /** @type {!Object} */ (await response.json());
  const lines = [];
  flattenCargoTrace(payload, '', lines);
  cargoTraceLines = lines.slice(0, 40);
  centerCargoSnapshot = deriveCenterCargo(payload);
  cargoContractReady = true;
}
