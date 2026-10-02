# Tail Sampling Console

This console deploys the collector configuration and displays the receiver,
sampling decisions, and trace-store inventory. The deployed collector and
telemetry receiver are external services provided by the environment.

`npm run build` creates the browser application. Configuration lives under
`src/config/`; the compiler normalizes deployment settings for the collector
API. Live ingestion and replay use the same production collector settings.

Use incident windows, trace detail, retention buckets and replay to inspect
missing traces. Policy decisions are cached for late spans of the same trace.
The receiver publishes its collector policy profiles (activation epochs and
service levels) on the console's service-levels panel; the active profile
applies to every window and replay. All GUI controls, received telemetry, and
ordinary sampling must remain functional. Collector settings may be changed to
repair the incident.
