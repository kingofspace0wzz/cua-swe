from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import socket

import pytest

from scripts import web_cua_broker, web_cua_client


SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"


def test_broker_validates_bounded_same_page_resize(tmp_path: Path):
    rollout = tmp_path / "rollout"
    rollout.mkdir()
    args = type(
        "Args",
        (),
        {
            "rollout_root": rollout,
            "expected_url": "http://127.0.0.1:47000",
        },
    )()
    session = rollout / "session.json"

    assert web_cua_broker._validate_request(
        [
            "act",
            "--session-file",
            str(session),
            "--kind",
            "resize",
            "--width",
            "500",
            "--height",
            "900",
        ],
        args,
    ) == "act"

    for dimensions in (("0", "900"), ("3841", "900"), ("500", "2161")):
        with pytest.raises(ValueError, match="resize dimensions"):
            web_cua_broker._validate_request(
                [
                    "act",
                    "--session-file",
                    str(session),
                    "--kind",
                    "resize",
                    "--width",
                    dimensions[0],
                    "--height",
                    dimensions[1],
                ],
                args,
            )


def test_broker_accepts_visual_observation_mode_on_start(tmp_path: Path):
    rollout = tmp_path / "rollout"
    rollout.mkdir()
    args = type(
        "Args",
        (),
        {
            "rollout_root": rollout,
            "expected_url": "http://127.0.0.1:47000",
        },
    )()

    assert web_cua_broker._validate_request(
        [
            "start",
            "--url",
            "http://127.0.0.1:47000",
            "--artifacts-dir",
            str(rollout / "cua-adapter"),
            "--session-file",
            str(rollout / "session.json"),
            "--observation-mode",
            "visual",
        ],
        args,
    ) == "start"


def test_broker_accepts_gameplay_key_hold_duration(tmp_path: Path):
    rollout = tmp_path / "rollout"
    rollout.mkdir()
    args = type(
        "Args",
        (),
        {
            "rollout_root": rollout,
            "expected_url": "http://127.0.0.1:47000",
        },
    )()

    assert web_cua_broker._validate_request(
        [
            "act",
            "--session-file",
            str(rollout / "session.json"),
            "--kind",
            "key_hold",
            "--text",
            "ArrowRight+Shift",
            "--duration-ms",
            "400",
        ],
        args,
    ) == "act"


def test_broker_translates_private_screenshot_into_client_attachment(tmp_path: Path):
    private_root = tmp_path / "private"
    private_artifacts = private_root / "artifacts"
    private_artifacts.mkdir(parents=True)
    screenshot = private_artifacts / "screenshot-0001.png"
    screenshot.write_bytes(b"private-browser-image")
    public_artifacts = tmp_path / "rollout" / "cua-adapter"
    session = web_cua_broker.BrokerSession(
        public_artifacts=str(public_artifacts),
        private_root=private_root,
        private_session=private_root / "session.json",
        private_artifacts=private_artifacts,
    )

    stdout, files = web_cua_broker._translated_output(
        json.dumps(
            {
                "ok": True,
                "observation": {"screenshot_path": str(screenshot)},
            }
        ),
        session,
    )

    assert json.loads(stdout)["observation"]["screenshot_path"] == str(
        public_artifacts / screenshot.name
    )
    assert [item["path"] for item in files] == [str(public_artifacts / screenshot.name)]
    web_cua_client._write_files(files)
    assert (public_artifacts / screenshot.name).read_bytes() == b"private-browser-image"


def test_broker_request_reader_has_an_overall_deadline(monkeypatch):
    server, client = socket.socketpair()
    monkeypatch.setattr(web_cua_broker, "MAX_REQUEST_SECONDS", 0.05)
    try:
        with pytest.raises(TimeoutError, match="timed out"):
            web_cua_broker._recv_line(server)
    finally:
        server.close()
        client.close()


def _wait_for_socket(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.is_socket():
            return
        if process.poll() is not None:
            raise AssertionError(f"broker exited early: {process.stderr.read()}")
        time.sleep(0.02)
    raise AssertionError("broker did not create its socket")


def test_host_broker_executes_validated_request_and_records_peer_pid(tmp_path: Path):
    workspace = tmp_path / "workspace"
    rollout = tmp_path / "rollout"
    home = tmp_path / "home"
    workspace.mkdir()
    rollout.mkdir()
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (rollout / "escape").symlink_to(outside, target_is_directory=True)
    session = rollout / "escape" / "session.json"
    fake_tool = tmp_path / "fake_tool.py"
    fake_tool.write_text(
        "import json, sys\nprint(json.dumps({'argv': sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    socket_path = Path("/tmp") / (
        "cua-broker-test-" + hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16] + ".sock"
    )
    socket_path.unlink(missing_ok=True)
    audit_path = tmp_path / "broker-audit.jsonl"
    token = "broker-test-token"
    broker = subprocess.Popen(
        [
            sys.executable,
            "-I",
            str(SCRIPTS_ROOT / "web_cua_broker.py"),
            "--socket",
            str(socket_path),
            "--token",
            token,
            "--admin-token",
            "broker-admin-test-token",
            "--audit-log",
            str(audit_path),
            "--state-root",
            str(tmp_path / "broker-state"),
            "--python",
            sys.executable,
            "--tool",
            str(fake_tool),
            "--workspace",
            str(workspace),
            "--rollout-root",
            str(rollout),
            "--expected-url",
            "http://127.0.0.1:47000",
            "--home",
            str(home),
            "--cache-home",
            str(home / ".cache"),
            "--playwright-browsers",
            str(tmp_path / "browser-runtime"),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_socket(socket_path, broker)
        start = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPTS_ROOT / "web_cua_client.py"),
                "--socket",
                str(socket_path),
                "--token",
                token,
                "--",
                "start",
                "--url",
                "http://127.0.0.1:47000",
                "--artifacts-dir",
                str(rollout / "escape" / "artifacts"),
                "--session-file",
                str(session),
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        assert start.returncode == 0, start.stderr
        assert not session.exists()
        assert list(outside.iterdir()) == []
        client = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPTS_ROOT / "web_cua_client.py"),
                "--socket",
                str(socket_path),
                "--token",
                token,
                "--",
                "observe",
                "--session-file",
                str(session),
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        assert client.returncode == 0, client.stderr
        assert json.loads(client.stdout)["argv"] == [
            "observe",
            "--session-file",
            str(session),
        ]
        records = [json.loads(line) for line in audit_path.read_text().splitlines()]
        assert len(records) == 2
        assert [record["verb"] for record in records] == ["start", "observe"]
        assert all(record["exit_code"] == 0 for record in records)
        assert all(record["peer_pid"] > 0 for record in records)

        duplicate = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPTS_ROOT / "web_cua_client.py"),
                "--socket",
                str(socket_path),
                "--token",
                token,
                "--",
                "start",
                "--url",
                "http://127.0.0.1:47000",
                "--artifacts-dir",
                str(rollout / "escape" / "artifacts"),
                "--session-file",
                str(session),
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        assert duplicate.returncode == 126
        assert "already active" in duplicate.stderr

        escaped = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPTS_ROOT / "web_cua_client.py"),
                "--socket",
                str(socket_path),
                "--token",
                token,
                "--",
                "observe",
                "--session-file",
                str(tmp_path / "outside.json"),
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        assert escaped.returncode == 126
        assert "escaped the rollout root" in escaped.stderr
    finally:
        broker.terminate()
        broker.wait(timeout=5)
        socket_path.unlink(missing_ok=True)
    assert not socket_path.exists()
    assert list(outside.iterdir()) == []
    assert os.stat(audit_path).st_mode & 0o077 == 0
