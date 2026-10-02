#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
HTML = ROOT / "index.html"
SOURCE = [
    ROOT / "src" / "input.js",
    ROOT / "src" / "bird.js",
    ROOT / "src" / "pipes.js",
    ROOT / "src" / "renderer.js",
    ROOT / "src" / "game.js",
    ROOT / "src" / "game_api.js",
]


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in [HTML, *SOURCE] if not path.is_file()]
    scripts = re.findall(r'<script src="([^"]+)"></script>', HTML.read_text(encoding="utf-8"))
    expected = [str(path.relative_to(ROOT)) for path in SOURCE]
    result = {
        "missing": missing,
        "script_order_ok": scripts == expected,
        "source_files": expected,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not missing and result["script_order_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
