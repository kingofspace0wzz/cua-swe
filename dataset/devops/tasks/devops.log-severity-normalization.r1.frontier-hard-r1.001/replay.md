# Replay

The opening Collector rollout session selects the affected collector receiver and a
failed operation. Stored severity says INFO while its raw received record says
SeverityNumber 19 and SeverityText Error; a routine completed event is incorrectly
ERROR. Click Receiver inventory: the affected receiver originates as JSON but delivers
OTel records; the SDK receiver delivers OTel; the legacy receiver still delivers JSON;
and a fourth receiver, the syslog relay, originates as syslog and delivers OTLP
records whose pipeline preserves the raw PRI severity. Return to Logs and select the
relay receiver: every relay record is stored Unspecified, and the raw detail of the
failed operation shows SeverityNumber 3 with SeverityText err and a `<27>`-prefixed
body line, while healthy relay records show 6/info and 7/debug. The severe filter on
the relay is empty although failed operations were delivered. Primary diagnosis needs
the inventory click plus one relay record selection (four actions including returns);
scenario, filter, retry, reset, and reload checks are additional verification.

Repair the representation used to decode each receiver's delivered severity. The
collector and SDK receivers deliver normalized OTel fields (in-range numeric ranks are
preserved and remain distinct); the legacy receiver's JSON body level remains
accurate; the relay's delivered numbers are raw syslog priorities, so its keyword text
(err, crit, warning, info, debug — spelling and case vary by deployment) selects the
band at the band's base rank, an unrecognized site-specific keyword stays Unspecified,
and syslog has no level below debug. Every record must remain present, with unchanged
body, timestamps, trace/span, resource and delivery identity. ERROR and FATAL are
severe. Retry delivery is idempotent. Reset returns the incident; reload reconstructs
the same accepted records. Hidden profiles vary IDs, spelling, identities, timestamps,
ordering, in-range values, relay keyword vocabulary, facility, and the unmapped token
under the identical contract.

The parent's code-only guess — selecting the decoder by `receiver.output.format` —
now fails: it decodes the relay's raw syslog priorities as OTel ranks (err/3 becomes
TRACE), so failed relay operations still vanish from the severe view. Both preserved
predecessor patches fail for exactly this reason.

Construction certification is not an agent outcome. The constructor dispatches the
matched deterministic gate after seal; the owner audits its saved evidence.
