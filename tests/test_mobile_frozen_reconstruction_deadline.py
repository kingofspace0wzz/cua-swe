"""Exercise the actual isolated Agent loop without network or native resources."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import requests
from cua_swe_bench.mobile_evaluation.core import sha

ROOT = Path(__file__).parent
from cua_swe_bench.mobile_evaluation import agent as agent


class DeadlineTests(unittest.TestCase):
    def exercise(self, elapsed_before, duration, error=None, wrapped=False):
        with tempfile.TemporaryDirectory(prefix="mobile-reconstruction-deadline-") as directory:
            root = Path(directory).resolve()
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "TASK.md").write_text("Repair the application.")
            task = SimpleNamespace(
                id="test",
                c={"editable": ["app.mjs"], "instruction": {"sha256": sha(workspace / "TASK.md")}},
            )
            clock = SimpleNamespace(now=0.0)

            class HTTP:
                RequestException = requests.RequestException

                def post(self, url, **kwargs):
                    clock.now += duration
                    if error:
                        raise error
                    return SimpleNamespace(headers={}, status_code=200, text="{}")

            client = SimpleNamespace(trace_http=agent.TraceHTTP(HTTP(), root / "agent"))

            def create(items, previous_response_id=None):
                try:
                    client.trace_http.post(
                        "https://example.invalid/test",
                        data="{}",
                        timeout=client.request_timeout_seconds,
                    )
                except Exception:
                    if wrapped:
                        # The production GPT transport loses the original cause.
                        raise RuntimeError("provider request failed after retries") from None
                    raise
                return {
                    "id": "response-1",
                    "model": run.protocol.model,
                    "status": "completed",
                    "output": [],
                }

            client.create = create

            def factory(protocol, tools, output):
                clock.now = elapsed_before
                return client

            run = agent.Agent(task, {}, SimpleNamespace(workspace=workspace), None,
                              "code-only", root / "agent", client_factory=factory)
            with patch.object(agent.time, "monotonic", side_effect=lambda: clock.now):
                state = run.run()
            return state, {
                p.name: json.loads(p.read_text()) for p in (root / "agent").glob("*.json")
            }

    def test_shortened_read_timeout_at_deadline_is_cap(self):
        state, records = self.exercise(2678.8, 21.14, requests.ReadTimeout("test"))
        self.assertEqual(state["termination"], "time_cap")
        self.assertEqual(state["faults"], [])
        self.assertEqual(state["responses"], 0)
        self.assertEqual(records["001-deadline.json"]["timeout_seconds"], 21)
        self.assertNotIn("001-provider-error.json", records)
        self.assertEqual(records["wire-001-error.json"]["error_type"], "ReadTimeout")

    def test_gpt_wrapped_original_read_timeout_is_cap(self):
        state, _ = self.exercise(2678.8, 21.14, requests.ReadTimeout("test"), wrapped=True)
        self.assertEqual(state["termination"], "time_cap")

    def test_full_request_timeout_is_provider_even_at_deadline(self):
        state, records = self.exercise(2100, 600, requests.ReadTimeout("test"))
        self.assertEqual(state["termination"], "provider")
        self.assertIn("001-provider-error.json", records)

    def test_original_600_second_outage_remains_provider(self):
        state, _ = self.exercise(1744.6, 600, requests.ReadTimeout("test"))
        self.assertEqual(state["termination"], "provider")

    def test_early_shortened_timeout_remains_provider(self):
        state, _ = self.exercise(2678.8, 10, requests.ReadTimeout("test"))
        self.assertEqual(state["termination"], "provider")

    def test_other_errors_at_deadline_remain_provider(self):
        for error in (requests.ConnectTimeout("test"), requests.ConnectionError("test"),
                      requests.HTTPError("401"), RuntimeError("ReadTimeout(fake)")):
            with self.subTest(error=type(error).__name__):
                state, _ = self.exercise(2678.8, 21.14, error)
                self.assertEqual(state["termination"], "provider")

    def test_cap_before_request_has_no_transport(self):
        state, records = self.exercise(2700, 0)
        self.assertEqual(state["termination"], "time_cap")
        self.assertFalse(any(n.startswith("wire-") for n in records))

    def test_successful_shortened_request_is_counted(self):
        state, _ = self.exercise(2678.8, 10)
        self.assertEqual(state["termination"], "submitted")
        self.assertEqual(state["responses"], 1)
        self.assertEqual(state["faults"], [])

    def test_direct_fable_exception_supported(self):
        client = SimpleNamespace()
        self.assertTrue(agent.deadline_read_timeout(
            client, requests.ReadTimeout(), 21, 600, 2699.94, 2700))
        self.assertFalse(agent.deadline_read_timeout(
            client, requests.ConnectTimeout(), 21, 600, 2699.94, 2700))

    def test_rounding_boundary(self):
        for elapsed, expected in ((2698.99, False), (2699, True), (2700, True)):
            self.assertEqual(agent.deadline_read_timeout(
                SimpleNamespace(), requests.ReadTimeout(), 21, 600, elapsed, 2700), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
