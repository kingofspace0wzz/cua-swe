"""Load the repository's central provider layer, scripts/provider_client.py.

Standalone agent scripts import provider_client directly; package code loads the same
file by path so every model call shares one routing and authentication implementation.
"""
from __future__ import annotations

from functools import cache
import importlib.util
from pathlib import Path
import sys

MODULE_NAME = "cua_swe_bench_provider_client"


def provider_client_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "provider_client.py"
        if (parent / "pyproject.toml").is_file() and candidate.is_file():
            return candidate
    raise RuntimeError("scripts/provider_client.py was not found above the cua_swe_bench package")


@cache
def load():
    path = provider_client_path()
    spec = importlib.util.spec_from_file_location(MODULE_NAME, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module
