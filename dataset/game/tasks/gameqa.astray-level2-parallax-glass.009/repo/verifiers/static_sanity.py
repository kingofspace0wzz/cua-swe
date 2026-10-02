#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "Box2dWeb.min.js",
    "Three.js",
    "game_api.js",
    "index.html",
    "jquery.js",
    "keyboard.js",
    "maze.js",
    "serve.py",
    "PROVENANCE.md",
    "README.md",
    "RIGHTS.md",
    "THIRD_PARTY_NOTICES.md",
    "verifiers/replay_state.py",
    "verifiers/static_sanity.py",
}
FROZEN_HASHES = {
    "Box2dWeb.min.js": "161c240927acb1f66059684b5feb7c0e9fe17823a32f39a65cc575aacaae8df2",
    "Three.js": "893df945a44244160c3f4b024e989d686c073a77110188c4116d39d84dc6353b",
    "jquery.js": "47b68dce8cb6805ad5b3ea4d27af92a241f4e29a5c12a274c852e4346a0500b4",
    "keyboard.js": "e485352c260762d19f222f33290d07d30d4a8ec023325fb1d8d121c4d1bda884",
    "maze.js": "7ba75832a61268f7b990a37dbde32333792f1fbafca7dcedaf3dfd165192e9a1",
    "serve.py": "1cb32e2c2f28f65238e58a4bb3ed9789cf8a846cee1608e4008f3e27a71e4e84",
    "README.md": "b01625591f4048b1aec81a8acb53980b690c6f775957dd01512369d2fb293705",
    "RIGHTS.md": "b3420a8594a46121aa0fd8c033d15b3e3895d27b8f86b481ca288201e009a00d",
    "THIRD_PARTY_NOTICES.md": "4ec9c57668ac22f8743c927e2deca15070b0521f6741d116db578f78f6c5cd9a",
}
FORBIDDEN_MEDIA = {"ball.png", "brick.png", "concrete.png"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_node(path: Path) -> None:
    subprocess.run(["node", "--check", str(path)], check=True)


def check_python(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def main() -> int:
    missing = sorted(name for name in REQUIRED if not (ROOT / name).is_file())
    if missing:
        raise AssertionError(f"missing required files: {missing}")

    for name, expected in FROZEN_HASHES.items():
        actual = digest(ROOT / name)
        if actual != expected:
            raise AssertionError(f"frozen file changed: {name}: {actual} != {expected}")

    present_media = sorted(name for name in FORBIDDEN_MEDIA if (ROOT / name).exists())
    if present_media:
        raise AssertionError(f"undocumented media must stay excluded: {present_media}")

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    for name in FORBIDDEN_MEDIA:
        if name in html:
            raise AssertionError(f"index.html references excluded asset {name}")
    for script_name in (
        "Box2dWeb.min.js",
        "Three.js",
        "keyboard.js",
        "jquery.js",
        "maze.js",
        "game_api.js",
    ):
        if not re.search(
            rf"<script[^>]+src=['\"]{re.escape(script_name)}['\"]",
            html,
        ):
            raise AssertionError(f"index.html does not load {script_name}")

    inline_scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    if len(inline_scripts) != 2:
        raise AssertionError(f"expected two inline scripts, found {len(inline_scripts)}")
    with tempfile.TemporaryDirectory(prefix="astray-static-") as temp_dir:
        temp_root = Path(temp_dir)
        for index, script in enumerate(inline_scripts, start=1):
            script_path = temp_root / f"inline-{index}.js"
            script_path.write_text(script, encoding="utf-8")
            check_node(script_path)

    for name in ("game_api.js", "keyboard.js", "maze.js"):
        check_node(ROOT / name)
    for name in ("serve.py", "verifiers/replay_state.py", "verifiers/static_sanity.py"):
        check_python(ROOT / name)

    serve = (ROOT / "serve.py").read_text(encoding="utf-8")
    if 'add_argument("--port", type=int, required=True)' not in serve:
        raise AssertionError("serve.py lost its required --port contract")

    api = (ROOT / "game_api.js").read_text(encoding="utf-8")
    for public_contract in (
        "window.gameAPI = {",
        "init: async function init(config)",
        "getState: function getState()",
        "reset: async function reset(options)",
        "supports_level_select: true",
        "supports_inplace_reset: true",
    ):
        if public_contract not in api:
            raise AssertionError(f"public gameAPI contract missing: {public_contract}")

    provenance = (ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
    if "55322928fa8bd51cb1719bd3807a32634aa5d3cb" not in provenance:
        raise AssertionError("provenance lost the discovery revision")

    print("self-contained Astray runtime syntax and packaging checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
