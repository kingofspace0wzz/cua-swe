# Replay

The opening Collector rollout session selects the affected collector receiver and a
failed operation. Stored severity says INFO while its raw received record says
SeverityNumber 19 and SeverityText Error; a routine completed event is incorrectly
ERROR. Click Receiver inventory: the affected receiver originates as JSON but delivers
OTel records; the SDK receiver delivers OTel; the legacy receiver still delivers JSON;
and a fourth receiver, the syslog relay, originates as syslog and delivers OTLP
records whose pipeline reads "syslog 5424 + app forwarder agents → OTLP relay
(producer severities preserved)". Return to Logs and select the relay receiver: every
relay record is stored Unspecified, and the severe filter is empty although failed
operations were delivered.

The relay carries two producer provenances, distinguishable in every raw detail. The
gateway daemon's lines are PRI-prefixed (`<25>gw-01.west …` on the terminated worker,
SeverityNumber 1, SeverityText alert; `<28>` warning; `<31>` debug; a non-PRI
`[audit]` line stays opaque). The application forwarder fleet's lines read
`fwd-3.west payments-gateway agent/<version>: level=<keyword> …` and the fleet is
mid-upgrade: in the same incident epoch the two failed "Payment operation failed"
records share SeverityText error but carry SeverityNumber 0 (agent/1.9.4) and 40
(agent/2.3.0), and the healthy and recovery epochs repeat the pattern (info as 2 and
20, warn as 1, verbose as 4 and 10, an unmapped `level=metric` line as 6). So the
delivered relay numbers are producer-internal scales — raw syslog priorities on the
gateway, per-agent-version level codes on the forwarders — while each producer's
keyword vocabulary is stable across epochs. Primary diagnosis needs the inventory
click plus the relay selection and three relay record selections (six actions
including returns); scenario, filter, retry, reset, and reload checks are additional
verification.

Repair the representation used to decode each receiver's delivered severity. The
collector and SDK receivers deliver normalized OTel fields (in-range numeric ranks
are preserved and remain distinct); the legacy receiver's JSON body level remains
accurate; the relay must be decoded from the union of the keyword vocabularies its
two producers demonstrate on screen — err/error to ERROR, alert to FATAL,
warning/warn to WARN, info to INFO, verbose/debug to DEBUG (spelling and case vary
by deployment) — each at the band's base rank, ignoring the delivered
producer-internal numbers. Unrecognized site-specific tokens (the gateway's audit
line and the forwarders' metric line) stay Unspecified, and neither producer emits a
level below debug. Every record must remain present, with unchanged body,
timestamps, trace/span, resource and delivery identity. ERROR and FATAL are severe.
Retry delivery is idempotent. Reset returns the incident; reload reconstructs the
same accepted records. Hidden profiles vary IDs, spelling, identities, timestamps,
ordering, in-range values, keyword case within the demonstrated stems, facility,
producer hosts, forwarder agent versions and their internal number scales, and the
unmapped tokens under the identical contract.

Both preserved predecessor lower-anchor CUA patches — which decode the relay's
SeverityNumber as a syslog priority table first — now fail: they classify the
forwarder's error/0 record as FATAL, its info/2 record as FATAL, its warn/1 record
as FATAL, and leave verbose unmapped, so the severe view over-fills with routine
forwarder traffic while diagnostics vanish. Single-provenance repairs (gateway-only
or forwarder-only vocabularies), the parent's shared-alias keyword decode (misses
alert and verbose), and number-scale transcriptions fitted to the visible agent
versions all fail for the recorded reasons.

Construction certification is not an agent outcome. The constructor dispatches the
matched deterministic gate after seal; the owner audits its saved evidence.
