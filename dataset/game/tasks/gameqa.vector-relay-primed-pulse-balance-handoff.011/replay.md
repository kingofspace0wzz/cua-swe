# Vector Relay primed Pulse Balance replay

Run the normal runtime on construction port 53500 at
`http://127.0.0.1:53500/?challenge=relay-circuit` with a 1280×720 viewport.
Use the ordinary four-action route: Space, R, Space, Left.

1. Reset with seed 73 and level 3. Confirm the relay is primed, the orb is
   attached, and the Pulse Balance is empty.
2. Press Space once and wait for RETURN REACHED. The balance shows one open
   cyan ring.
3. Press R once and wait beyond the captured first due time. The exact repair
   leaves the relay armed and shows a blue folded mark without red.
4. Press Space once and wait for the second RETURN REACHED. Let the orb fall
   out naturally. The replacement docks while the cyan ring remains visible.
5. Press Left exactly once. The attached orb and receiver shift west while the
   cyan ring remains visible.
6. Wait for settlement. The repaired build completes for +500 and adds one
   gold diamond without a red fragment.
7. Reset and confirm the primed state and empty balance return.

The real-browser verifier remains the byte-identical `.005` protected file. It
checks the original state contract, including selective-retirement accounting,
two contacts and commits, zero broken outcomes, westward transfer, exactly 500
points, and reset behavior. It does not inspect the observer.

The retained deterministic matrix covers baseline, exact gold, both Branch B
near-fixes, exact `.006`, exact `.003`, same-port, and contact-epoch inputs in
fresh git copies. Every case is also replayed with the canvas observer
neutralized; application state is identical. Those non-browser results are not
a substitute for outer-host Chromium screenshots and verifier reports.
