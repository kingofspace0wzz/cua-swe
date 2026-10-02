# Gauge Relay

Original purpose-built StatsD gauge collector and receipt console. This is not
an upstream StatsD defect reproduction. `npm run build` builds the local UI;
the harness provides a native UDP receiver and receipt sink to `server.mjs`.
The worker consumes the receiver's durable datagram capture in receipt order.
The site fleet's producer endpoints send the gauge traffic; receiver capture,
producer attribution and sink history are independent of the worker decoder
and update logic.

The wire format is statsd/statsd v0.9.0 gauge lines: complete ASCII metric
lines with `|g`, including LF-separated multiline datagrams up to512bytes.
Values are finite decimals in native gauge units, with magnitude at most1000000.
Gauge traffic arrives from more than one fleet endpoint, and endpoints do not
all publish the same way. Delta-capable statsd relays use a lexical leading
sign for a relative update and represent a negative absolute target as an
unsigned zero followed by the negative delta. Snapshot-style publishers report
each reading directly and may format signed quantities with an explicit
leading sign. Which endpoints currently publish which way is site
provisioning; it is not encoded in this repository, and the fleet inventory
names channels without describing their update semantics. Endpoints
demonstrate their currently active conventions at runtime, and a reprovisioned
endpoint demonstrates its new convention in the epoch that activates the
change; the operator console's provisioning bulletin explains what to watch.
Keep each confirmed native receipt reflected at the sink within
one second; preserve metric identity, producer attribution and every received
update, including repeated values. No tags, sample rates, counters, network
retries or cross-datagram line fragments are involved. Numerical comparisons
tolerate ordinary floating-point rounding.

The controlled localhost traffic fixture records actual native receipts.
General UDP does not guarantee delivery, ordering or exactly-once semantics.
Idle and page reload keep gauge state; reset clears a session and replay begins
fresh. Inspect datagrams, the fleet inventory and gauge update history through
the normal console. Any general decoder or update implementation honoring this
contract is valid.
