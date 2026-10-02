from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"


def test_mcp_returns_screenshot_as_image_content_without_metadata(tmp_path: Path):
    rollout = tmp_path / "rollout"
    rollout.mkdir()
    launcher = tmp_path / "fake_launcher.py"
    launcher.write_text(
        """#!/usr/bin/env python3
import json
from pathlib import Path
import sys

verb = sys.argv[1]
if verb in {"observe", "act"}:
    session = Path(sys.argv[sys.argv.index("--session-file") + 1])
    screenshot = session.parent / "cua-adapter" / "screenshot-0001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"fake-png-pixels")
    print(json.dumps({"ok": True, "observation": {
        "screenshot_path": str(screenshot), "observation_mode": "visual"
    }}))
else:
    print(json.dumps({"ok": True}))
""",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "start", "arguments": {}},
        },
    ]
    completed = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS_ROOT / "web_cua_mcp.py")],
        cwd=tmp_path,
        env={
            **os.environ,
            "CUA_SWE_WEB_CUA_LAUNCHER": str(launcher),
            "CUA_SWE_WEB_CUA_SESSION": str(rollout / "session.json"),
            "CUA_SWE_AGENT_ROLLOUT_DIR": str(rollout),
            "CUA_SWE_WEB_URL": "http://127.0.0.1:47000",
            "CUA_SWE_WEB_VIEWPORT": "1280x720",
        },
        input="\n".join(json.dumps(item) for item in requests) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    content = responses[2]["result"]["content"]
    assert [item["type"] for item in content] == ["text", "image"]
    assert content[1]["data"]
    serialized = json.dumps(responses[2])
    for forbidden in ("body text", "elements", "viewport", "screenshot_path"):
        assert forbidden not in serialized
    trajectory = (rollout / "visual-mcp-trajectory.jsonl").read_text(encoding="utf-8")
    assert '"delivery": "mcp_image_content"' in trajectory


def test_mcp_normalizes_kind_specific_action_fields(tmp_path: Path):
    rollout = tmp_path / "rollout"
    rollout.mkdir()
    invocations = tmp_path / "invocations.jsonl"
    launcher = tmp_path / "fake_launcher.py"
    launcher.write_text(
        f'''#!/usr/bin/env python3
import json
from pathlib import Path
import sys

with Path({str(invocations)!r}).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
verb = sys.argv[1]
if verb in {{"observe", "act"}}:
    session = Path(sys.argv[sys.argv.index("--session-file") + 1])
    screenshot = session.parent / "cua-adapter" / "screenshot.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"pixels")
    print(json.dumps({{"ok": True, "observation": {{
        "screenshot_path": str(screenshot), "observation_mode": "visual"
    }}}}))
else:
    print(json.dumps({{"ok": True}}))
''',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    requests = [
        {"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "act",
                "arguments": {
                    "kind": "scroll",
                    "x": 640,
                    "y": 600,
                    "delta_y": 500,
                    "steps": 10,
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "act", "arguments": {"kind": "wait", "steps": 5}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "act",
                "arguments": {"kind": "drag_move", "x": 20, "y": 30, "steps": 5},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "act",
                "arguments": {
                    "kind": "key_hold",
                    "text": "ArrowRight+Shift",
                    "duration_ms": 400,
                },
            },
        },
    ]
    completed = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS_ROOT / "web_cua_mcp.py")],
        cwd=tmp_path,
        env={
            **os.environ,
            "CUA_SWE_WEB_CUA_LAUNCHER": str(launcher),
            "CUA_SWE_WEB_CUA_SESSION": str(rollout / "session.json"),
            "CUA_SWE_AGENT_ROLLOUT_DIR": str(rollout),
            "CUA_SWE_WEB_URL": "http://127.0.0.1:47000",
            "CUA_SWE_WEB_VIEWPORT": "1280x720",
        },
        input="\n".join(json.dumps(item) for item in requests) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    act_schema = next(tool for tool in responses[0]["result"]["tools"] if tool["name"] == "act")
    assert "press" in act_schema["inputSchema"]["properties"]["kind"]["enum"]
    assert "key_hold" in act_schema["inputSchema"]["properties"]["kind"]["enum"]
    calls = [json.loads(line) for line in invocations.read_text(encoding="utf-8").splitlines()]
    action_calls = [call for call in calls if call[0] == "act"]
    assert "--steps" not in action_calls[0]
    assert "--steps" not in action_calls[1]
    assert action_calls[2][action_calls[2].index("--steps") + 1] == "5"
    assert action_calls[3][action_calls[3].index("--duration-ms") + 1] == "400"
