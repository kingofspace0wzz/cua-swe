# Alert operations console

The console imports rule definitions, compiles their query and metadata, and
submits the result to the team's evaluator. It shows query series, pending and
firing history, labels, annotations, the notification route table, receiver
delivery, and the current routing epoch context.

Run `npm run build`. The host supplies the evaluator at launch. Live rules,
captures, routes, and routing epochs arrive from that service. Local source
contains no incident capture.
Example import shapes are in `src/rules/example.js`.
Routing epoch scopes are declared with short policy class codes; the routing
policy runbook posted in the console is the operations publication where those
classes are defined.
Replay evaluates the capture from its beginning. Reset also restores the initial
selection. Next evaluation advances logical time without wall-clock waits.
