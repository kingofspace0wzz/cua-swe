from __future__ import annotations

import os
from pathlib import Path


def dotenv_values(start: Path | None = None) -> dict[str, str]:
    current = Path.cwd() if start is None else start
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        env_path = directory / ".env"
        if env_path.exists():
            return parse_dotenv(env_path)
    return {}


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def config_value(name: str, dotenv: dict[str, str]) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    return dotenv.get(name) or None
