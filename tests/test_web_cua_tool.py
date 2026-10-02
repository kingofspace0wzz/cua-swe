from __future__ import annotations

import argparse
from http.server import HTTPServer
import json
from pathlib import Path
import threading
from urllib import error
from urllib import request

import pytest

from scripts import web_cua_tool
from cua_swe_bench.adapters.base import GuiAction, GuiObservation


@pytest.mark.parametrize("value", ["0x720", "1280x0", "3841x720", "1280x2161"])
def test_parse_viewport_rejects_invalid_or_unbounded_dimensions(value: str):
    with pytest.raises(argparse.ArgumentTypeError, match="viewport"):
        web_cua_tool._parse_viewport(value)


def test_act_cli_wires_staged_drag_payload(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    captured: dict[str, object] = {}

    def fake_post(session_file: Path, endpoint: str, payload: dict[str, object]):
        captured.update({"session_file": session_file, "endpoint": endpoint, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(web_cua_tool, "_post", fake_post)
    args = web_cua_tool.build_parser().parse_args(
        [
            "act",
            "--session-file",
            "session.json",
            "--kind",
            "drag_move",
            "--x",
            "320",
            "--y",
            "240",
            "--steps",
            "12",
        ]
    )

    assert args.func(args) == 0
    assert captured["endpoint"] == "/act"
    assert captured["payload"] == {"kind": "drag_move", "x": 320, "y": 240, "steps": 12}
    assert '"ok": true' in capsys.readouterr().out.lower()


def test_act_cli_lists_all_staged_drag_actions():
    parser = web_cua_tool.build_parser()

    for kind in ["drag_start", "drag_move", "drag_end"]:
        args = parser.parse_args(["act", "--session-file", "session.json", "--kind", kind])
        assert args.kind == kind


def test_act_cli_wires_bounded_gameplay_key_hold(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def fake_post(session_file: Path, endpoint: str, payload: dict[str, object]):
        captured.update(
            {"session_file": session_file, "endpoint": endpoint, "payload": payload}
        )
        return {"ok": True}

    monkeypatch.setattr(web_cua_tool, "_post", fake_post)
    args = web_cua_tool.build_parser().parse_args(
        [
            "act",
            "--session-file",
            "session.json",
            "--kind",
            "key_hold",
            "--text",
            "ArrowRight+Shift",
            "--duration-ms",
            "400",
        ]
    )

    assert args.func(args) == 0
    assert captured["payload"] == {
        "kind": "key_hold",
        "text": "ArrowRight+Shift",
        "duration_ms": 400,
    }


def test_visual_observation_exposes_only_screenshot_path():
    observation = GuiObservation(
        url="http://example.test/private-route",
        screenshot_path="/tmp/screenshot-0001.png",
        text="diagnostic body text",
        metadata={
            "viewport": {"width": 1280, "height": 720},
            "elements": [{"text": "Reveal", "center": {"x": 100, "y": 80}}],
        },
    )

    public = web_cua_tool._public_observation_dict(observation, "visual")

    assert public == {
        "screenshot_path": "/tmp/screenshot-0001.png",
        "observation_mode": "visual",
    }
    assert "diagnostic body text" not in json.dumps(public)
    assert "elements" not in public


def test_act_cli_wires_same_page_resize_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    captured: dict[str, object] = {}

    def fake_post(session_file: Path, endpoint: str, payload: dict[str, object]):
        captured.update({"session_file": session_file, "endpoint": endpoint, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(web_cua_tool, "_post", fake_post)
    args = web_cua_tool.build_parser().parse_args(
        [
            "act",
            "--session-file",
            "session.json",
            "--kind",
            "resize",
            "--width",
            "500",
            "--height",
            "900",
        ]
    )

    assert args.func(args) == 0
    assert captured["endpoint"] == "/act"
    assert captured["payload"] == {"kind": "resize", "width": 500, "height": 900}
    assert '"ok": true' in capsys.readouterr().out.lower()


@pytest.mark.parametrize("kind", ["back", "forward"])
def test_act_cli_wires_fieldless_history_actions(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    captured: dict[str, object] = {}

    def fake_post(session_file: Path, endpoint: str, payload: dict[str, object]):
        captured.update({"session_file": session_file, "endpoint": endpoint, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(web_cua_tool, "_post", fake_post)
    args = web_cua_tool.build_parser().parse_args(
        ["act", "--session-file", "session.json", "--kind", kind]
    )

    assert args.func(args) == 0
    assert captured["endpoint"] == "/act"
    assert captured["payload"] == {"kind": kind}
    assert '"ok": true' in capsys.readouterr().out.lower()


def test_server_validates_and_dispatches_staged_drag_action(tmp_path: Path):
    class StubAdapter:
        def __init__(self):
            self.action: GuiAction | None = None

        def act(self, action: GuiAction) -> GuiObservation:
            self.action = action
            return GuiObservation(
                url="http://example.test",
                text="dragging",
                metadata={"drag_active": True},
            )

    adapter = StubAdapter()
    auth_token = "test-cua-token"
    server = HTTPServer(
        ("127.0.0.1", 0),
        web_cua_tool._make_handler(web_cua_tool.CuaServer(adapter, tmp_path), auth_token),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    session_file = tmp_path / "session.json"
    session_file.write_text(
        json.dumps({"host": host, "port": port, "auth_token": auth_token}),
        encoding="utf-8",
    )

    try:
        result = web_cua_tool._post(
            session_file,
            "/act",
            {"kind": "drag_move", "x": 320, "y": 240, "steps": 12},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result["ok"] is True
    assert result["observation"]["metadata"]["drag_active"] is True
    assert adapter.action == GuiAction(kind="drag_move", x=320, y=240, steps=12)
    assert '"event": "act"' in (tmp_path / "trajectory.jsonl").read_text(encoding="utf-8")


def test_server_cancels_active_drag_when_payload_validation_fails(tmp_path: Path):
    class StubAdapter:
        def __init__(self):
            self.cancelled = False

        def cancel_active_drag(self) -> bool:
            self.cancelled = True
            return True

    adapter = StubAdapter()
    auth_token = "test-cua-token"
    server = HTTPServer(
        ("127.0.0.1", 0),
        web_cua_tool._make_handler(web_cua_tool.CuaServer(adapter, tmp_path), auth_token),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    session_file = tmp_path / "session.json"
    session_file.write_text(
        json.dumps({"host": host, "port": port, "auth_token": auth_token}),
        encoding="utf-8",
    )

    try:
        with pytest.raises(RuntimeError, match="HTTP 400.*ValidationError"):
            web_cua_tool._post(
                session_file,
                "/act",
                {"kind": "drag_move", "x": 320},
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert adapter.cancelled is True
    trajectory = (tmp_path / "trajectory.jsonl").read_text(encoding="utf-8")
    assert '"event": "drag_cancel"' in trajectory
    assert "ValidationError" in trajectory


def test_server_rejects_oversized_request_body(tmp_path: Path):
    class StubAdapter:
        def cancel_active_drag(self) -> bool:
            return False

    auth_token = "test-cua-token"
    server = HTTPServer(
        ("127.0.0.1", 0),
        web_cua_tool._make_handler(
            web_cua_tool.CuaServer(StubAdapter(), tmp_path),
            auth_token,
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    session_file = tmp_path / "session.json"
    session_file.write_text(
        json.dumps({"host": host, "port": port, "auth_token": auth_token}),
        encoding="utf-8",
    )

    try:
        with pytest.raises(RuntimeError, match="HTTP 413.*RequestBodyTooLarge"):
            web_cua_tool._post(
                session_file,
                "/act",
                {"kind": "type", "text": "x" * web_cua_tool.MAX_REQUEST_BODY_BYTES},
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)



def test_server_rejects_unauthenticated_loopback_requests(tmp_path: Path):
    class StubAdapter:
        def observe(self) -> GuiObservation:
            raise AssertionError("unauthenticated request reached adapter")

    server = HTTPServer(
        ("127.0.0.1", 0),
        web_cua_tool._make_handler(
            web_cua_tool.CuaServer(StubAdapter(), tmp_path),
            "private-token",
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        unauthenticated = request.Request(
            f"http://{host}:{port}/observe",
            data=b"{}",
            headers={"content-type": "application/json"},
            method="POST",
        )
        with pytest.raises(error.HTTPError) as exc_info:
            request.urlopen(unauthenticated, timeout=2)
        assert exc_info.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
