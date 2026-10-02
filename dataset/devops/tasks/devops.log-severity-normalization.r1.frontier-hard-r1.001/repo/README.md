# Log operations workbench

An operator console for an existing mixed receiver fleet. The external receiver service supplies delivery batches and receiver inventory; this checkout contains the ingestion bridge and views, not a local substitute for the deployed telemetry.

`npm run build` builds the static console. `node server.mjs --host 127.0.0.1 --port 55300` serves it. The assigned live session connects it to the receiver service.

The bridge accepts each delivery once, keeps the original log record and correlation fields intact, and stores the normalized severity with each record. Severe means ERROR or FATAL; the All records view retains every severity. JSON application logs and OTel log records are supported. OTel severities use the full six four-value ranges; zero is unspecified and may fall back to severity text. Unknown levels stay unspecified. Repair incorrect behavior while preserving these capabilities, receiver controls, record detail, and delivery retry/reset behavior.

Build, server, proxy and verifier infrastructure are protected. Product source under src/pipeline, src/views, src/controllers and src/state may be repaired. The live service is accessible only through the assigned operator browser channel.
