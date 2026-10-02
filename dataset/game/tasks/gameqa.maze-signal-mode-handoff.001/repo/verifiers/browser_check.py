#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import struct
import subprocess
import tempfile
from threading import Thread
import time
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


WALKABLE = [
    [1, 1], [2, 1], [3, 1], [4, 1], [5, 1], [6, 1], [7, 1], [8, 1], [9, 1],
    [1, 2], [2, 2], [3, 2], [4, 2], [5, 2], [6, 2], [7, 2], [8, 2], [9, 2],
    [1, 3], [3, 3], [5, 3], [7, 3], [9, 3],
    [1, 4], [3, 4], [5, 4], [7, 4], [9, 4],
    [1, 5], [2, 5], [3, 5], [4, 5], [5, 5], [6, 5], [7, 5], [8, 5], [9, 5],
]
SCENARIO = {
    "width": 11,
    "height": 7,
    "tickMs": 120,
    "walkable": WALKABLE,
    "playerStart": {"x": 1, "y": 5},
    "pulse": {"x": 3, "y": 5},
    "exit": {"x": 9, "y": 1},
    "phase": {"initial": "corner", "next": "track", "ticks": 5},
    "alertTicks": 8,
    "releaseTicks": 4,
    "rover": {
        "dock": {"x": 5, "y": 3},
        "junction": {"x": 5, "y": 2},
        "cornerStep": {"x": 4, "y": 2},
        "trackStep": {"x": 6, "y": 2},
    },
    "seals": {
        "scenario": "route-seal-kestrel-731",
        "phase": "phase-proof-cedar-284",
        "release": "release-proof-mica-619",
        "branch": "branch-proof-lumen-452",
        "collision": "collision-proof-sable-907",
    },
}


class ScenarioHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True})
            return
        if self.path == "/api/scenario":
            self._json(SCENARIO)
            return
        self.send_error(404)

    def _json(self, value: object) -> None:
        body = json.dumps(value, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CDP:
    def __init__(self, websocket_url: str):
        parsed = urlparse(websocket_url)
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        target = parsed.path
        if parsed.query:
            target += f"?{parsed.query}"
        request = (
            f"GET {target} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode())
        response = self._read_http_headers()
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"websocket upgrade failed: {response!r}")
        self.next_id = 1

    def _read_http_headers(self) -> bytes:
        data = b""
        while b"\r\n\r\n" not in data:
            data += self.socket.recv(4096)
        return data

    def close(self) -> None:
        with suppress(Exception):
            self.socket.close()

    def call(self, method: str, params: dict | None = None) -> dict:
        call_id = self.next_id
        self.next_id += 1
        self._send_json({"id": call_id, "method": method, "params": params or {}})
        while True:
            message = self._recv_json()
            if message.get("id") != call_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method} failed: {message['error']}")
            return message.get("result", {})

    def _send_json(self, value: object) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode()
        first = bytes([0x81])
        length = len(payload)
        mask = secrets.token_bytes(4)
        if length < 126:
            header = first + bytes([0x80 | length])
        elif length < 65536:
            header = first + bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header = first + bytes([0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.socket.sendall(header + mask + masked)

    def _recv_exact(self, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining:
            chunk = self.socket.recv(remaining)
            if not chunk:
                raise ConnectionError("websocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_json(self) -> dict:
        while True:
            first, second = self._recv_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length)
            if masked:
                payload = bytes(
                    byte ^ mask[index % 4] for index, byte in enumerate(payload)
                )
            if opcode == 8:
                raise ConnectionError("websocket close frame")
            if opcode == 9:
                continue
            if opcode != 1:
                continue
            return json.loads(payload.decode())


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_url(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.4) as response:
                if response.status < 500:
                    return
        except (OSError, URLError):
            time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {url}")


def wait_devtools_page(
    profile: Path,
    process: subprocess.Popen,
    timeout: float = 10.0,
) -> str:
    active_port_file = profile / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    latest_error = "DevToolsActivePort was not created"
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"Chromium exited before DevTools became ready (exit code {exit_code})"
            )
        try:
            lines = active_port_file.read_text(encoding="utf-8").splitlines()
            port = int(lines[0])
            if len(lines) < 2 or not lines[1].startswith("/devtools/browser/"):
                raise ValueError("invalid browser websocket path")
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=0.4) as response:
                targets = json.load(response)
            for target in targets:
                websocket_url = target.get("webSocketDebuggerUrl")
                if target.get("type") == "page" and websocket_url:
                    return str(websocket_url)
            latest_error = "DevTools target list contained no page"
        except (OSError, URLError, ValueError, IndexError, json.JSONDecodeError) as exc:
            latest_error = str(exc)
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for Chromium DevTools page: {latest_error}")


def wait_game_bridge(cdp: CDP, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    latest_error = "window.gameAPI is not ready"
    while time.monotonic() < deadline:
        try:
            result = cdp.call("Runtime.evaluate", {
                "expression": "Boolean(window.gameAPI && window.gameAPI.getState)",
                "returnByValue": True,
            })
            if result.get("result", {}).get("value") is True:
                return
            latest_error = "window.gameAPI is not ready"
        except (ConnectionError, RuntimeError) as exc:
            latest_error = str(exc)
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for game bridge: {latest_error}")


def verifier_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("_cua_verifier", secrets.token_hex(8)))
    return urlunparse(parsed._replace(query=urlencode(query)))


def chromium_executable() -> str:
    def is_executable_file(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    configured = os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE")
    if configured and is_executable_file(Path(configured)):
        return configured
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found and is_executable_file(Path(found)):
            return found
    cache_roots = []
    playwright_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if playwright_browsers_path:
        cache_roots.append(Path(playwright_browsers_path))
    home_cache = Path.home() / ".cache" / "ms-playwright"
    if home_cache not in cache_roots:
        cache_roots.append(home_cache)
    for cache in cache_roots:
        for pattern in (
            "chromium_headless_shell-*/chrome-headless-shell*/chrome-headless-shell",
            "chromium-*/chrome-linux*/chrome",
        ):
            for match in sorted(cache.glob(pattern), reverse=True):
                if is_executable_file(match):
                    return str(match)
    raise FileNotFoundError("no Chromium executable found")


@contextmanager
def browser_session(url: str):
    profile = tempfile.TemporaryDirectory(prefix="signal-maze-chromium-")
    cdp = None
    process = subprocess.Popen(
        [
            chromium_executable(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--no-first-run",
            "--allow-file-access-from-files",
            "--window-size=1280,720",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile.name}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        websocket_url = wait_devtools_page(Path(profile.name), process)
        cdp = CDP(websocket_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.call("Network.clearBrowserCache")
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 1280,
            "height": 720,
            "deviceScaleFactor": 1,
            "mobile": False,
        })
        cdp.call("Page.navigate", {"url": verifier_url(url)})
        wait_game_bridge(cdp)
        yield cdp
    finally:
        if cdp is not None:
            with suppress(Exception):
                cdp.close()
        with suppress(ProcessLookupError):
            process.terminate()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        if process.poll() is None:
            with suppress(ProcessLookupError):
                process.kill()
        profile.cleanup()


def evaluate(cdp: CDP, expression: str):
    result = cdp.call("Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True,
    })
    if "exceptionDetails" in result:
        raise RuntimeError(result["exceptionDetails"])
    return result.get("result", {}).get("value")


def state(cdp: CDP) -> dict:
    raw = evaluate(cdp, "JSON.stringify(window.gameAPI.getState())")
    return json.loads(raw)


def wait_state(cdp: CDP, predicate, timeout: float, description: str) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = state(cdp)
        if predicate(latest):
            return latest
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {description}: {latest}")


def key_event(cdp: CDP, event_type: str, key: str) -> None:
    code_by_key = {
        "ArrowRight": 39,
        "ArrowUp": 38,
        "ArrowLeft": 37,
        "ArrowDown": 40,
    }
    cdp.call("Input.dispatchKeyEvent", {
        "type": event_type,
        "key": key,
        "code": key,
        "windowsVirtualKeyCode": code_by_key[key],
        "nativeVirtualKeyCode": code_by_key[key],
    })


def hold_until(cdp: CDP, key: str, predicate, description: str) -> dict:
    key_event(cdp, "keyDown", key)
    try:
        return wait_state(cdp, predicate, 4.0, description)
    finally:
        key_event(cdp, "keyUp", key)


def screenshot(cdp: CDP, path: Path) -> None:
    result = cdp.call("Page.captureScreenshot", {
        "format": "png",
        "captureBeyondViewport": False,
    })
    path.write_bytes(base64.b64decode(result["data"]))


def replay(cdp: CDP, evidence_dir: Path) -> dict:
    wait_state(
        cdp,
        lambda value: value.get("scenarioSeal") == "route-seal-kestrel-731",
        5.0,
        "game bridge",
    )
    evaluate(cdp, "window.gameAPI.reset()")
    initial = state(cdp)
    screenshot(cdp, evidence_dir / "initial.png")
    evaluate(cdp, "window.gameAPI.reset()")
    initial = state(cdp)
    if initial["phase"]["mode"] != "corner" or initial["player"]["lives"] != 3:
        raise AssertionError(f"invalid initial state: {initial}")

    after_right = hold_until(
        cdp,
        "ArrowRight",
        lambda value: value["player"]["position"] == {"x": 3, "y": 5},
        "upper approach column",
    )
    if not after_right["alert"]["active"] or not after_right["metrics"]["pulseCollected"]:
        raise AssertionError(f"warning was not reached by ordinary input: {after_right}")

    hold_until(
        cdp,
        "ArrowUp",
        lambda value: value["player"]["position"] == {"x": 3, "y": 2},
        "junction row",
    )
    at_junction_row = hold_until(
        cdp,
        "ArrowRight",
        lambda value: value["player"]["position"] == {"x": 6, "y": 2},
        "junction waiting tile",
    )
    screenshot(cdp, evidence_dir / "warning-dock.png")
    if (
        not at_junction_row["alert"]["active"]
        or at_junction_row["rover"]["state"] != "junction"
        or at_junction_row["rover"]["appearance"] != "warning"
        or at_junction_row["rover"]["hazard"]
    ):
        raise AssertionError(f"dock release checkpoint was not reached: {at_junction_row}")

    pre_handoff = wait_state(
        cdp,
        lambda value: value["alert"]["active"] and value["alert"]["remaining"] <= 1,
        3.0,
        "pre-handoff warning frame",
    )
    screenshot(cdp, evidence_dir / "pre-handoff.png")

    post_handoff = wait_state(
        cdp,
        lambda value: not value["alert"]["active"] and value["rover"]["branch"] is not None,
        3.0,
        "post-handoff branch",
    )
    screenshot(cdp, evidence_dir / "post-handoff.png")
    checkpoint = {
        "initial": initial,
        "after_right": after_right,
        "at_junction_row": at_junction_row,
        "pre_handoff": pre_handoff,
        "post_handoff": post_handoff,
    }
    (evidence_dir / "state-replay.json").write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if post_handoff["phase"]["mode"] != "corner":
        raise AssertionError(
            "the route phase did not resume from the pre-warning owner: "
            + json.dumps(post_handoff, sort_keys=True)
        )
    if (
        post_handoff["rover"]["branch"] != "left"
        or post_handoff["rover"]["position"] != {"x": 4, "y": 2}
    ):
        raise AssertionError(
            "the first post-warning junction route disagreed with the indicator: "
            + json.dumps(post_handoff, sort_keys=True)
        )
    if (
        post_handoff["rover"]["appearance"] == "warning"
        or not post_handoff["rover"]["hazard"]
    ):
        raise AssertionError(
            "the visible and collision handoff did not clear together: "
            + json.dumps(post_handoff, sort_keys=True)
        )
    if post_handoff["metrics"]["contacts"] != 0 or post_handoff["player"]["lives"] != 3:
        raise AssertionError(
            "the player was hit by the wrong resumed route: "
            + json.dumps(post_handoff, sort_keys=True)
        )

    hold_until(
        cdp,
        "ArrowRight",
        lambda value: value["player"]["position"] == {"x": 9, "y": 2},
        "exit column",
    )
    final = hold_until(
        cdp,
        "ArrowUp",
        lambda value: value["terminal"]["isTerminal"],
        "terminal exit",
    )
    screenshot(cdp, evidence_dir / "final.png")
    if final["terminal"]["outcome"] != "success" or final["player"]["lives"] != 3:
        raise AssertionError(f"exit did not complete cleanly: {final}")
    checkpoint["final"] = final
    (evidence_dir / "state-replay.json").write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return checkpoint


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:51000/")
    parser.add_argument("--service-port", type=int, default=51001)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("verifier-artifacts"),
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    parsed_url = urlparse(args.url)
    service = None
    thread = None
    scenario_file = None
    try:
        if parsed_url.scheme == "file":
            scenario_file = Path(parsed_url.path).parent / "scenario.json"
            scenario_file.write_text(
                json.dumps(SCENARIO, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            service = ThreadingHTTPServer(
                ("127.0.0.1", args.service_port),
                ScenarioHandler,
            )
            thread = Thread(target=service.serve_forever, daemon=True)
            thread.start()
            wait_url(f"http://127.0.0.1:{args.service_port}/health")
            wait_url(args.url)
        with browser_session(args.url) as cdp:
            result = replay(cdp, args.evidence_dir)
    finally:
        if service is not None:
            service.shutdown()
            service.server_close()
        if thread is not None:
            thread.join(timeout=2)
        if scenario_file is not None:
            scenario_file.unlink(missing_ok=True)

    print(json.dumps({
        "status": "pass",
        "phase": result["post_handoff"]["phase"]["mode"],
        "branch": result["post_handoff"]["rover"]["branch"],
        "contacts": result["post_handoff"]["metrics"]["contacts"],
        "terminal": result["final"]["terminal"]["outcome"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
