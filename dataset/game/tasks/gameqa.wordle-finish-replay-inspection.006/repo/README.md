# Letter Arc

Letter Arc is a compact five-letter deduction game rebuilt as editable source
for a deterministic software-debugging benchmark. It preserves genuine
gameplay responsibilities: repeated-letter allocation, staggered tile turns,
keyboard precedence, hard guidance, rejection, restart, daily/practice
navigation, result motion, and terminal completion.

After a successful round, the visible **Replay finish** control repeats the
normal completion motion and pauses at an inspection point. **Continue**
finishes playback, and the replay remains available for another viewing.

The benchmark harness supplies the protected daily and practice challenges.
Concrete words and expected observations are intentionally absent from this
source package.

The implementation is licensed under GPL-3.0-only. See `LICENSE`,
`UPSTREAM.md`, and `RIGHTS.md`.

## Run

```bash
npm ci
npm run build
CUA_SWE_EXTERNAL_SERVICE_ORIGIN=http://127.0.0.1:52001 \
  npm run dev -- --host 127.0.0.1 --port 52000
```
