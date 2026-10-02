"""Read-only launcher inside a source sandbox; host controller owns the budget."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    config = json.load(sys.stdin)
    if set(config) != {"route", "prompt"} or config["route"] not in {"codex-sol", "claude-opus5"}:
        raise ValueError("unselected CLI session configuration")
    if not isinstance(config["prompt"], str):
        raise ValueError("prompt must be text")
    bridge = load("mobile_cli_client", "/bridge/client.py")
    commands = load("mobile_cli_commands", "/bridge/commands.py")
    Path("/cli-home/.codex").mkdir(parents=True, exist_ok=True)
    server, thread = bridge.proxy("/cap.sock")
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        argv, env = commands.command(config["route"], base, config["prompt"])
        child = subprocess.Popen(
            argv, env=env, stdin=subprocess.DEVNULL,
            stdout=sys.stdout, stderr=sys.stderr,
        )
        code = child.wait()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    # Exiting the owned PID namespace also terminates any detached CLI children.
    return code


if __name__ == "__main__":
    raise SystemExit(main())
