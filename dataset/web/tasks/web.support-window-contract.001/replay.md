# Runtime replay

1. Start the protected service and application.
2. Open `/`. Case `SUP-410` must show `Window unavailable`.
3. Select **Schedule details**. The live response must expose
   `schedule.week_anchor_epoch_ms`, `schedule.selected_slot_ref`,
   `schedule.day_code_map`, `schedule.slots[*].day_code`,
   `schedule.slots[*].start_quanta`, `schedule.quantum_minutes`, and
   `schedule.display_zone`.
4. Apply gold. The primary window is `Oct 8, 2026, 5:00 AM (America/Chicago)`.
5. Open `/?scenario=secondary`. It is `Jan 8, 2027, 8:30 AM (Europe/Berlin)`.

The secondary payload changes opaque day codes, selected slot, quantum, and
timezone. It rejects hardcoding, first-slot selection, Sunday-origin guesses,
fixed 30-minute quanta, and browser-local formatting.

