# Replay: react-datepicker mask-clear blur

## Layout

- `repo/` — agent-visible broken product (appointment booking form) with the
  editable date-input state machine (`src/DatePickerField.jsx`), app entry
  (`src/index.jsx`), static server (`server.mjs`), and the deterministic
  behavioral verifier (`verifiers/verify.py`).
- `env/` — evaluator-owned runtime: the input-mask runtime (`service.mjs`)
  and the protected behavioral contract (`contract.json`). Never copied into or
  served from the agent workspace.

## Bring up (matches task.yaml setup.launch)

```bash
cd repo
npm install
npm run build
node ../env/service.mjs --host 127.0.0.1 --port 5175 &
CUA_SWE_EXTERNAL_SERVICE_ORIGIN=http://127.0.0.1:5175 \
  node server.mjs --host 127.0.0.1 --port 4173 &
# open http://127.0.0.1:4173
```

## Symptom (broken)

1. The field shows `12/25/2024` and the readout shows `12/25/2024`.
2. Select all in the field and delete. The mask surfaces its cleared
   placeholder (e.g. `__/__/____`).
3. Click away (blur). The field SNAPS BACK to `12/25/2024` instead of staying
   cleared. The readout still shows `12/25/2024`.

## Required behavior (gold)

- Clearing the field and blurring leaves the field empty and the readout `None`.
- Typing a merely-invalid non-empty date (`13/40/2024`) and blurring KEEPS the
  previous selection (`12/25/2024`).
- Typing a valid new date updates the selection.
- The cleared-mask rule must be GENERIC: several mask libraries surface
  different cleared patterns (`__/__/____`, `--/--/----`, spaces); all must
  clear the selection.

## Verify

```bash
cd repo
python3 verifiers/verify.py   # exit 0 iff all 5 protected payloads pass
```

## Gates (see _probes/run_gates.sh)

| state | verifier |
| --- | --- |
| broken baseline | FAIL (2/5) |
| gold.patch | PASS (5/5) |
| negative.patch | FAIL (4/5, clears on any non-parse) |
| source-only analogue (literal `__/__/____`) | FAIL (3/5, other patterns unmatched) |

## Upstream

Hacker0x01/react-datepicker#6180 (issue #5814), base
`0231bbd7e707d87397e1486d0f2b453cf7f50367`, merge
`d4625d425ae31b15ed13de98446ffb6431f82659`. Broken behavior was confirmed
against the real `react-datepicker@9.0.0` (see `_rdp6180_probe/`).
