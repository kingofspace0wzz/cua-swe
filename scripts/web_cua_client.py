#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from typing import Any


MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def _recv_line(connection: socket.socket) -> bytes:
    data = bytearray()
    while True:
        chunk = connection.recv(65536)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_RESPONSE_BYTES:
            raise RuntimeError("CUA broker response exceeded the size limit")
        if data.endswith(b"\n"):
            break
    return bytes(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def _write_files(files: Any) -> None:
    if not isinstance(files, list):
        raise RuntimeError("CUA broker returned an invalid file attachment list")
    for attachment in files:
        if not isinstance(attachment, dict):
            raise RuntimeError("CUA broker returned an invalid file attachment")
        path = Path(str(attachment.get("path") or ""))
        if not path.is_absolute():
            raise RuntimeError("CUA broker attachment path is not absolute")
        try:
            data = base64.b64decode(str(attachment["data_base64"]), validate=True)
        except (KeyError, ValueError) as exc:
            raise RuntimeError("CUA broker attachment is not valid base64") from exc
        if hashlib.sha256(data).hexdigest() != attachment.get("sha256"):
            raise RuntimeError("CUA broker attachment digest mismatch")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".cua-screenshot-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def main() -> int:
    if not sys.flags.isolated:
        raise SystemExit("web_cua_client.py must run with Python isolated mode (-I)")
    args = build_parser().parse_args()
    forwarded = list(args.arguments)
    if forwarded and forwarded[0] == "--":
        forwarded.pop(0)
    if not forwarded:
        raise SystemExit("a CUA adapter command is required")
    request: dict[str, Any] = {
        "token": args.token,
        "argv": forwarded,
        "cwd": os.getcwd(),
        "pid": os.getpid(),
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(60)
        connection.connect(args.socket)
        connection.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        response = json.loads(_recv_line(connection).decode("utf-8"))
    _write_files(response.get("files", []))
    stdout = str(response.get("stdout") or "")
    stderr = str(response.get("stderr") or "")
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    return int(response.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
