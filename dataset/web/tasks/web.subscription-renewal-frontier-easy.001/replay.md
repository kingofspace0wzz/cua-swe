# Frontier calibration replay: `web.subscription-renewal-frontier-easy.001`

- Seed: `web.subscription-renewal-contract.002`
- Level: `easy`
- Controlled knob: one interval, no grace application, and one shared value format
- Human replay: intentionally deferred for this calibration phase.

## Screenshot-observable contract

- `cycle.anchor_epoch_ms`
- `cycle.anchor_application`
- `cycle.interval_quanta`
- `cycle.quantum_days`
- `cycle.grace_quanta`
- `cycle.grace_application`
- `cycle.display_zone`
- `cycle.value_format`
- `cycle.display_pattern`

## Deterministic verifier scenarios

- Primary: `SUB-731` -> `Renews 2026-01-29 10:00`
- Secondary: `SUB-118` -> `Next cycle 2026-06-11 09:00`

The broken baseline must fail both scenarios. The gold patch must pass both,
and the primary-literal negative patch must fail the secondary scenario.
