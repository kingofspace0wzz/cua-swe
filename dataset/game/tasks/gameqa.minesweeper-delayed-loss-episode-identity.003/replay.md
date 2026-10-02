# Timing-diagnostic delayed loss replay

1. Reset to a protected seed and click a safe center cell to place mines.
2. Expose a mine directly. The exploded board remains visibly pending, then the face commits to loss after the evaluator-owned handoff shown in the Episode integrity panel.
3. Repeat, but click the face or call `window.gameAPI.reset({seed})` while the panel still says `PENDING`. The new board must remain fresh after the old handoff time passes.
4. Repeat the loss through a count-valid chord with an incorrect flag placement.
5. Confirm first-click safety, flag → question → unknown counter behavior, adjacency rendering, deterministic seeds, and both reset routes.

The protected runtime contract supplies the exact same-episode handoff duration only to the CUA browser panel. The source-only arm receives no evaluator service. The incomplete negative restores the handoff duration but leaves the callback unowned, so a prior episode can still kill the fresh board.

Revision 002 changes only the evaluator-owned visual treatment. It adds live elapsed-versus-target timing classification and explicitly states that a clean repair must address both handoff duration and episode ownership. The source, mutation, gold patch, negative patches, protected verifier, seeds, loss paths, and reset routes are unchanged.

Revision 003 keeps the sequence-2 timing-plus-ownership mechanism and visual
diagnostic, while retargeting both the broken source delay and the protected
handoff. This invalidates verbatim sequence-2 timing patches and tests whether
live game observation remains causally useful under a fresh calibration.
