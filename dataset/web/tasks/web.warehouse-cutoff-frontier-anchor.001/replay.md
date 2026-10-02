# Frontier calibration replay: `web.warehouse-cutoff-frontier-anchor.001`

- Level: `anchor`
- Controlled knob: use one date grammar across payloads; retain timezone and cutoff selection
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

- Primary: `ORD-244` -> `Dispatches 2026-10-09`
- Secondary: `ORD-688` -> `Ships · 2026-12-01`

Broken must fail, gold must pass both payloads, and the literal negative must fail.
