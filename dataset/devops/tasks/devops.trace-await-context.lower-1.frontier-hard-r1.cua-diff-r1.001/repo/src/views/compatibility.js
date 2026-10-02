export function renderCompatibility(snapshot) {
  if (!snapshot?.diagnosis) return;

  const diagnosis = snapshot.diagnosis;
  const status = document.querySelector('[data-test="compatibility-status"]');
  status.textContent = diagnosis.status;
  status.dataset.status = diagnosis.status;

  document.querySelector('[data-test="compatibility-manager"]').textContent =
    diagnosis.manager;
  document.querySelector('[data-test="compatibility-async"]').textContent =
    diagnosis.compiledAsyncSemantics;
  document.querySelector('[data-test="compatibility-outcome"]').textContent =
    diagnosis.suspensionOutcome;
  document.querySelector(
    '[data-test="compatibility-recommendation"]',
  ).textContent = diagnosis.recommendation;
}
