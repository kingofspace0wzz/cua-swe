# Frontier calibration replay: `web.account-recovery-frontier-easy.001`

- Seed: `web.account-recovery-contract.001`
- Level: `easy`
- Controlled knob: all referenced candidates are allowed; only join, precedence, and presentation remain
- Human replay: intentionally deferred for this calibration phase.

## Screenshot-observable contract

- `risk.selected_band_ref`
- `risk.bands[*].band_ref`
- `risk.bands[*].channel_refs`
- `risk.channel_precedence`
- `risk.channels[*].channel_ref`
- `risk.channels[*].ui_mode`
- `risk.channels[*].display_label`
- `risk.allowed_modes`
- `risk.display_pattern`

## Deterministic verifier scenarios

- Primary: `ACC-731` -> `Continue via Voice recovery`
- Secondary: `ACC-118` -> `Try Passkey recovery`

The broken baseline must fail both scenarios. The gold patch must pass both,
and the primary-literal negative patch must fail the secondary scenario.
