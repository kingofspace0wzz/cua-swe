"""Host-only source synchronization and pixel capability for native CLIs."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import threading
import time

from cua_swe_bench.mobile_evaluation.browser import PixelActionError, action_valid
from cua_swe_bench.mobile_evaluation.core import Fault, digest, verify_ref, write_json
from cua_swe_bench.mobile_evaluation.workspace import extract
from .cli_transport import TransportStop


class CliPixels:
    """The CLI supplies actions, never paths, runtime scripts or private reads.

    The attempt controller owns the runtime and must await this callback before
    closing that runtime or inventorying artifacts. Native-runtime failures keep
    their original category; invalid model tool arguments remain tool feedback.
    """
    def __init__(self, task, baseline, source, runtime, root):
        if runtime is None:
            raise Fault("configuration", "CLI CUA requires an initialized pixel runtime")
        self.task, self.baseline, self.source = task, baseline, Path(source)
        self.runtime, self.root = runtime, Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.last_patch = digest({
            "schema": 1, "task_digest": task.id,
            "baseline_digest": digest(baseline), "changes": [],
        })
        self.lock = threading.Lock()
        self.actions, self.syncs, self.seconds = 0, 0, 0.0
        self.images_created = []
        self.image_events = []
        self.closed = False

    def close(self):
        # This is an ownership barrier, not runtime cancellation. The outer
        # controller must account for the bounded in-flight native operation.
        with self.lock:
            self.closed = True

    @staticmethod
    def argument_error(message):
        return {"content": [{"type": "text", "text": json.dumps({
            "tool_argument_error": message,
        })}], "isError": True}

    def __call__(self, body):
        with self.lock:
            if self.closed:
                raise TransportStop("cancelled", "pixel capability closed")
            if not isinstance(body, dict) or set(body) != {"action"} or not action_valid(body["action"]):
                return self.argument_error("browser accepts one valid pixel action")
            started = time.monotonic()
            self.actions += 1
            prefix = self.root / f"{self.actions:04d}"
            write_json(prefix.with_suffix(".action.json"), body)
            try:
                patch = extract(self.task, self.baseline, self.source)
                patch_digest = digest(patch)
                write_json(prefix.with_suffix(".patch.json"), patch)
                if patch_digest != self.last_patch:
                    # The returned runtime diagnostics stay exclusively private.
                    sync = self.runtime.sync(patch)
                    write_json(prefix.with_suffix(".sync.json"), sync)
                    self.last_patch = patch_digest
                    self.syncs += 1
                try:
                    image = self.runtime.act(body["action"])
                except PixelActionError as error:
                    return self.argument_error(str(error))
                except ValueError:
                    # The native API uses ValueError when the edited app is
                    # unavailable. Permit repair without exposing its internals.
                    return self.argument_error("app unavailable; repair source and try again")
                if not isinstance(image, dict):
                    raise Fault("image_delivery", "pixel runtime omitted its image receipt")
                url, ref = image.get("data_url"), image.get("evidence")
                if not isinstance(url, str) or not url.startswith("data:image/png;base64,"):
                    raise Fault("image_delivery", "pixel runtime did not return inline PNG")
                try:
                    encoded = url.split(",", 1)[1]
                    raw = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError) as error:
                    raise Fault("image_delivery", "invalid inline PNG payload") from error
                if (not raw.startswith(b"\x89PNG\r\n\x1a\n") or not verify_ref(ref)
                        or hashlib.sha256(raw).hexdigest() != ref["sha256"]):
                    raise Fault("image_delivery", "pixel payload and immutable receipt differ")
                self.images_created.append(ref)
                event = {"image": ref, "created_monotonic": time.monotonic()}
                self.image_events.append(event)
                write_json(prefix.with_suffix(".image.json"), event)
                return {
                    "content": [
                        {"type": "text", "text": "Current app screenshot."},
                        {"type": "image", "mimeType": "image/png", "data": encoded},
                    ],
                    "isError": False,
                }
            except Fault as error:
                write_json(prefix.with_suffix(".fault.json"), {
                    "category": error.category, "message": str(error),
                })
                raise TransportStop(error.category, "pixel capability stopped: " + error.category) from error
            finally:
                self.seconds += time.monotonic() - started
