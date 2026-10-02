# Frontier calibration replay: `web.warehouse-cutoff-frontier-easy.001`

- Seed: `web.warehouse-cutoff-contract.001`
- Level: `easy`
- Controlled knob: human-readable day codes, no closures, and both orders are before cutoff
- Human replay: intentionally deferred for this calibration phase.

## Screenshot-observable contract

- `dispatch.placed_epoch_ms`
- `dispatch.facility_zone`
- `dispatch.day_code_map`
- `dispatch.cutoffs[*].day_code`
- `dispatch.cutoffs[*].minute_of_day`
- `dispatch.closed_dates`
- `dispatch.before_cutoff_policy`
- `dispatch.after_cutoff_policy`
- `dispatch.closed_date_policy`
- `dispatch.date_format`
- `dispatch.display_pattern`

## Deterministic verifier scenarios

- Primary: `ORD-731` -> `Dispatches 2026-10-09`
- Secondary: `ORD-118` -> `Ships · 01/12/2026`

The broken baseline must fail both scenarios. The gold patch must pass both,
and the primary-literal negative patch must fail the secondary scenario.
