# Replay — v3.recharts-responsive-pie.001 (Allocation Ring Studio)

Behavior-derived clean-room reproduction of Recharts responsive-pie sizing
(recharts/recharts#1136): a pie/ring inside a responsive container must size its
radius from the settled measured drawable area, not from a raw parent box, and
must re-settle as the layout changes.

## What the surface shows

A studio with, per board, a **live** allocation ring on the left and the
**approved reference** of the same board on the right. A profile bar
(`Widescreen`, `Sidebar`, `Stacked`, `Compact`) re-lays the card at different
shapes; each profile is fetched fresh from the harness board service and the
ring is re-drawn under a live `ResizeObserver`. A read-out under the live ring
prints its rendered radius, center, the on-screen plot size, and whether the
ring is `within frame` or `overflowing frame`.

## Contract channel (harness-owned, agent-invisible)

`env/service.mjs` serves `/studio/board?profile=…` with the raw layout inputs
for the active board (card size, legend dock side and reserved extent, gutter,
ring scale, hole ratio, slices) and an **approved reference image** it renders
itself from the correct settled geometry (an SVG data URI — pixels only, no
copyable radius/center). It never serves the settled plot box, resolved radius,
or center. Three protected boards (`ledger`, `pension`, `sovereign`) with
heterogeneous card shapes, dock sides, reserves, ring scales, and hole ratios
are exercised, each with four profiles.

The static host (`repo/server.mjs`) forwards `/studio/board` to whatever origin
`CUA_SWE_EXTERNAL_SERVICE_ORIGIN` points at and echoes an opaque `x-board-seal`
token; nothing decodable ships to the browser beyond the board inputs and the
reference pixels.

## Discovery sequence (screenshot-only)

1. Load the studio; note the live ring beside the approved reference.
2. Step through the profiles. On `Sidebar`/`Stacked`/`Compact` the card docks
   its legend and leaves the ring less room.
3. Compare the live ring to the approved reference and read the live read-out:
   in the broken build the live ring is sized for more room than it has and
   `overflowing frame`, while the reference fills the room cleanly.
4. The fix must make the live ring match the reference on every profile of every
   board — i.e. sized to the room actually left on screen.

## Repairs (underdetermined from source)

- **Gold** (`gold.patch`, two files): observe the plot area (not the whole card)
  in `view.js`, and in `ringResolver.js` size the ring straight to that settled
  measured box. Passes all 12 protected payloads.
- **Negative** (`negative.patch`, one file): keep observing the whole card and
  try to account for the chrome by subtracting a fixed header/gutter and the
  legend reserve symmetrically. This over- or under-shrinks depending on the
  dock side and reserve, so it settles correctly on some profiles (e.g. some
  bottom-dock stacked profiles) and mis-sizes the right-dock ones — a genuine
  partial repair that fails the multi-payload verifier.
- **Hard-coded probe** (`_probes/hardcoded.patch`): pins the ring to a fixed
  radius. Passes a couple of individual profiles whose room happens to match but
  fails the multi-payload verifier, proving no single memorized constant works.

## Verifier

`repo/verifiers/browser_check.py` starts each protected board on an ephemeral
port, walks all four profiles, measures the settled `.plot-area` box off the
DOM, reads the live ring's rendered radius/fit, and requires on every profile
that the radius equals the tighter half-extent of the on-screen plot times the
served ring scale and that the ring stays within frame. Every target is
recomputed live from what the board serves; nothing is hard-coded.

## Reproduce

```
cd repo && npm run build          # syntax-checks all modules + host
python3 verifiers/browser_check.py   # broken: fails on docked profiles
git init -q && git add -A && git commit -qm base
git apply ../gold.patch && python3 verifiers/browser_check.py   # passes all
git checkout -- src && git apply ../negative.patch && python3 verifiers/browser_check.py  # fails
```

Or run the full construction gate:

```
python3 _gates/run_gates.py .
```

## Provenance

- upstream: recharts/recharts#1136
- revision: 12bbe4f280df0df33bc30d0488673a965fa17262
- license: MIT
- conversion: behavior-derived clean-room fixture (see runtime-contract.yaml)
