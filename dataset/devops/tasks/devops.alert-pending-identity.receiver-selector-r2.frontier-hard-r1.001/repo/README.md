# Alert operations console

The console imports rule definitions, compiles their query and metadata, and
submits the result to the team's evaluator. It shows query series, pending and
firing history, labels, annotations, receiver delivery, and the delivery
journal.

Run `npm run build`. The host supplies the evaluator at launch. Live rules and
captures arrive from that service. Local source contains no incident capture.
Example import shapes are in `src/rules/example.js`.
Replay evaluates the capture from its beginning. Reset also restores the initial
selection. Next evaluation advances logical time without wall-clock waits.
