#!/usr/bin/env python3
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


class ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        values = dict(attrs)
        source = values.get("src")
        if source:
            self.scripts.append(source)


def main() -> int:
    required = [
        ROOT / "RIGHTS.md",
        ROOT / "UPSTREAM.md",
        ROOT / "PROVENANCE-BLOCKER.md",
        ROOT / "index.html",
        ROOT / "server.py",
        ROOT / "game_api.js",
        ROOT / "js" / "Hex.js",
        ROOT / "js" / "checking.js",
        ROOT / "js" / "update.js",
        ROOT / "verifiers" / "browser_check.py",
        ROOT / "verifiers" / "state_verifier.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing required files: " + ", ".join(missing))

    collector = ScriptCollector()
    collector.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    missing_scripts = [
        source for source in collector.scripts if not (ROOT / source).is_file()
    ]
    if missing_scripts:
        raise SystemExit("index references missing scripts: " + ", ".join(missing_scripts))

    python_files = [
        ROOT / "server.py",
        ROOT / "verifiers" / "browser_check.py",
        ROOT / "verifiers" / "state_verifier.py",
    ]
    for python_file in python_files:
        compile(
            python_file.read_text(encoding="utf-8"),
            str(python_file),
            "exec",
        )

    print(
        "static-check: ok; browser execution and gameplay certification were not run",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
