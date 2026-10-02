"""Isolated lifecycle regressions; no model calls, browser sessions, or grades."""
import asyncio
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).parent
from cua_swe_bench.mobile_evaluation import native_worker as worker
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a"
    "2ioAAAAASUVORK5CYII="
)


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mobile-reconstruction-js-recovery-")
        self.root = Path(self.temp.name)
        config = {
            "task_digest": "unit-test-only",
            "expected_assertions": ["behavior"],
            "operation": "runtime",
            "source_manifest": {},
            "native": {
                "assets": [], "capture_required": False,
                "scene": {"state_mode": "hooks", "path": "/", "timeout_ms": 1000,
                          "viewport": {"width": 400, "height": 800}},
            },
        }
        self.s = worker.Supervisor(config, self.root)
        self.s.server = SimpleNamespace(root=self.root, unsupported=[], origin="http://unit.invalid")
        self.s.browser = object()
        self.s.context = object()
        self.s.hook = AsyncMock(return_value={})
        self.s.accept_generation = lambda update: self.root
        self.s.ready = True
        self.s.page = SimpleNamespace(
            reload=AsyncMock(), screenshot=AsyncMock(side_effect=self.pixels),
            mouse=SimpleNamespace(click=AsyncMock()),
        )

    def tearDown(self):
        self.s.journal.close()
        self.temp.cleanup()

    async def pixels(self, *, path, **kwargs):
        Path(path).write_bytes(PNG)

    async def page_error(self, **kwargs):
        self.s.record_page_error(TypeError("Cannot read properties of null (reading 'naturalWidth')"))

    def assert_pixels(self, reply):
        self.assertEqual(reply["status"], "pixels")
        self.assertEqual((self.root / reply["frame"]).read_bytes(), PNG)

    async def test_runtime_reload_with_app_error_returns_pixels_and_can_repair(self):
        self.s.page.reload.side_effect = self.page_error
        self.assert_pixels(await self.s.act({"type": "reload"}))
        self.assert_pixels(await self.s.act({"type": "screenshot"}))
        self.s.page.reload.side_effect = None
        await self.s.prepare_sync()
        self.assertEqual(await self.s.rebuild("sync", {}), {"status": "ready"})
        self.assertEqual(self.s.faults, [])
        self.assert_pixels(await self.s.act({"type": "screenshot"}))
        events = [json.loads(x) for x in (self.root / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(x["event"] == "browser_page_error" for x in events))

    async def test_broken_sync_preserves_repair_channel(self):
        self.s.page.reload.side_effect = self.page_error
        await self.s.prepare_sync()
        self.assertEqual(await self.s.rebuild("sync", {}), {"status": "ready"})
        self.assertTrue(self.s.ready)
        self.assert_pixels(await self.s.act({"type": "screenshot"}))
        await self.s.prepare_sync()
        self.s.page.reload.side_effect = None
        self.assertEqual(await self.s.rebuild("sync", {}), {"status": "ready"})

    async def test_error_during_screenshot_is_recoverable(self):
        async def screenshot(**kwargs):
            await self.pixels(**kwargs)
            await self.page_error()
        self.s.page.screenshot.side_effect = screenshot
        self.assert_pixels(await self.s.act({"type": "screenshot"}))
        self.assertTrue(self.s.faults)

    async def test_baseline_start_and_capture_remain_strict(self):
        self.s.page.reload.side_effect = self.page_error
        for operation in ("start", "capture"):
            with self.subTest(operation=operation):
                with self.assertRaises(worker.BrowserDiagnostic):
                    await self.s.rebuild(operation, {})
        with self.assertRaises(worker.BrowserDiagnostic):
            await self.s.capture()

    async def test_grade_does_not_turn_unattributed_page_error_into_failure(self):
        self.s.config["operation"] = "grade"
        self.s.page.reload.side_effect = self.page_error
        outcome = await self.s.rebuild("grade", {})
        self.assertEqual(outcome["execution"], "exception")
        self.assertEqual(outcome["errors"][0]["stage"], "unattributed_application_failure")
        self.assertNotIn("assertions", outcome)
        with self.assertRaises(worker.BrowserDiagnostic):
            await self.s.check_faults(allow_page_errors=True)

    async def test_renderer_and_policy_faults_stay_fatal_even_when_mixed(self):
        for stage in ("page_crash", "navigation", "websocket_unsupported", "callback"):
            with self.subTest(stage=stage):
                self.s.faults = [{"stage": "pageerror", "error": "app"},
                                 {"stage": stage, "error": "infra or policy"}]
                with self.assertRaises(worker.BrowserDiagnostic) as error:
                    await self.s.act({"type": "screenshot"})
                self.assertEqual(error.exception.diagnostics, [{"stage": stage, "error": "infra or policy"}])
        self.s.page.screenshot.assert_not_called()

    async def test_unsupported_server_api_stays_fatal(self):
        self.s.record_page_error("app")
        self.s.server.unsupported = [{"method": "POST", "path": "/unsupported"}]
        with self.assertRaisesRegex(RuntimeError, "unsupported application API"):
            await self.s.act({"type": "screenshot"})
        self.s.page.screenshot.assert_not_called()

    async def test_screenshot_timeout_stays_an_exception(self):
        self.s.record_page_error("app")
        self.s.page.screenshot.side_effect = TimeoutError("renderer did not return pixels")
        with self.assertRaises(TimeoutError):
            await self.s.act({"type": "screenshot"})
        self.assertEqual(list(self.root.glob("pixels-*.png")), [])

    async def test_hook_exception_is_not_suppressed(self):
        self.s.hook.side_effect = TimeoutError("trusted restore hook timeout")
        self.s.sync_pending = True
        with self.assertRaises(TimeoutError):
            await self.s.rebuild("sync", {})
        self.assertFalse(self.s.ready)

    async def test_valid_grade_is_preserved(self):
        self.s.config["operation"] = "grade"
        good = {"execution": "complete", "errors": [], "expected_assertions": ["behavior"],
                "assertions": [{"id": "behavior", "passed": True}]}
        self.s.hook.side_effect = [{}, good]
        self.assertEqual(await self.s.rebuild("grade", {}), good)


if __name__ == "__main__":
    unittest.main(verbosity=2)
