# Gauge Relay

Original purpose-built StatsD gauge collector and receipt console. This is not
an upstream StatsD defect reproduction. `npm run build` builds the local UI;
the harness provides a native UDP receiver and receipt sink to `server.mjs`.
The worker consumes the receiver's durable datagram capture in receipt order,
and every captured datagram carries the site relay attribution recorded by the
receiver. Receiver capture, relay attribution and sink history are independent
of the worker decoder and update logic.

The wire format is classic StatsD gauge lines: complete ASCII metric lines
with `|g`, including LF-separated multiline datagrams up to512bytes. Values
are finite decimals in native gauge units, with magnitude at most1000000. No
tags, sample rates, counters, network retries or cross-datagram line fragments
are involved. Numerical comparisons tolerate ordinary floating-point rounding.

Site relays batch the gauge traffic. Every relay opens a session epoch, and
re-announces after each of its internal rollover points, with one atomic
announce batch: a multiline datagram that leads with the relay's own
`<relay>.sync` register line and then restates the authoritative current
reading of every gauge that relay tracks, all as unsigned lines. Announce
readings are authoritative for that moment; announce batches are never split.
Between announces, live-forwarded lines follow the site's provisioned relay
generation: pass-through relays forward each producer update as sent, using a
lexical leading sign for a relative change and an unsigned rebase (for
example an unsigned zero followed by a negative relative change for a
negative target), while folding relays publish each gauge reading directly
and may format a signed quantity with an explicit leading sign. Which
generation a site runs is deployment provisioning; it is not recorded in this
repository and has to be taken from the live traffic, whose announce batches
carry enough evidence to reconcile it within each session epoch.

Keep each confirmed native receipt reflected at the sink within one second;
preserve metric identity, relay attribution and every received update,
including repeated values.

The controlled localhost traffic fixture records actual native receipts.
General UDP does not guarantee delivery, ordering or exactly-once semantics.
Idle and page reload keep gauge state; reset clears a session and replay
begins fresh with the relay announces re-run. Inspect datagrams and gauge
update history through the normal console. Any general decoder or update
implementation honoring this contract is valid.
