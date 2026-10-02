# Repair the pass wallet

The wallet's availability and validation action disagree with imported issuer records and validation receipts. Repair this workflow so each selected pass shows the availability the issuer permits, offers validation only when permitted, and validates one complete visit with the correct resulting balance. The same integration must work for other imports under the issuer's contract, not just the first pass.

In the prepared app, select a pass, open **Issuer details** to inspect the issuer's reading guide and record, and open **Receipts** for its validation history. These are product evidence surfaces, accessible before any repair. Preserve them. Also preserve confirmation/cancel without unintended validation, the selected pass, independent saved pass notes, and navigation back to the wallet. Accepted validation results and notes must survive ordinary reload; refusals must not consume a visit.

This is an original standalone mobile-web issuer sandbox, not a live ticketing service. The prepared browser imports external issuer packets and replays their validation responses locally. All ordinary client source and build inputs are included here. The external packets are product inputs supplied only to the isolated app, not source files. Outside the prepared runtime the inbox is intentionally empty. An ordinary reload retains imported records and user data. Rebuild explicitly resets to the imported starting scene.

You may edit all ordinary client files. `build.sh` is the protected copy-to-dist/syntax-check wrapper; run `sh build.sh` to build. No network dependencies are needed. Target the 400×800 CSS-pixel mobile web viewport.
