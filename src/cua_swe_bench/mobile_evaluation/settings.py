"""Trusted host configuration. Never mounted in the agent/build namespace."""
from pathlib import Path
import json
import os
import sys

REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = os.environ.get('CUA_MOBILE_CONFIG')
CONFIG = json.loads(Path(CONFIG_PATH).read_text()) if CONFIG_PATH else {}
ROOT = Path(CONFIG.get('output_root', '/tmp/mobile-reconstruction-offline')).resolve()
PYTHON = CONFIG.get('python', '/runtime/venv/bin/python')
VENV = CONFIG.get('venv', '/runtime/venv')
BROWSERS = CONFIG.get('browsers', '/runtime/browsers')
BWRAP = CONFIG.get('bwrap', '/usr/bin/bwrap')
BROWSER_BWRAP = CONFIG.get('browser_bwrap', '/runtime/browser-bwrap')
PROFILE = CONFIG.get('apparmor_profile')
REQUIREMENTS = str(REPO / 'dataset/mobile/evaluation/requirements.lock')
CLIENT = Path(__file__).with_name('responses_client.py')
TOOLCHAIN = Path(CONFIG.get('cli_toolchain', '/runtime/cli'))
CATALOG = REPO / 'dataset/mobile/evaluation/model-catalog.json'


PROVIDER_FIELDS = {'base_url', 'api_key_env'}


def provider_config(route, protocol, model):
    """Routed endpoint for one Mobile route; the wire protocol is fixed by the route.

    CONFIG['providers'][route] = {"base_url": ..., "api_key_env": ...}. Without an
    entry, the central layer's routing (CUA_SWE_PROVIDER_ROUTES or public defaults)
    applies. Keys are read from the host environment only.
    """
    from cua_swe_bench.provider_layer import load
    providers = CONFIG.get('providers', {})
    if not isinstance(providers, dict):
        raise ValueError('runtime configuration providers must be an object')
    entry = providers.get(route)
    if entry is None:
        return load().route_config(protocol, model)
    if not isinstance(entry, dict) or set(entry) - PROVIDER_FIELDS:
        raise ValueError(f'provider route {route} accepts only {sorted(PROVIDER_FIELDS)}')
    return load().ProviderConfig(provider=protocol, model=model, **entry)


def provider_transport(route, protocol, model):
    """Host-only transport. The key never enters the agent or build namespace."""
    from cua_swe_bench.provider_layer import load
    return load().ProviderTransport(provider_config(route, protocol, model))


def validate_runtime(route):
    import hashlib
    if sys.platform != 'linux' or not CONFIG_PATH:
        raise ValueError('Mobile execution requires Linux and a private --runtime-config')
    for name in ('output_root', 'python', 'venv', 'browsers', 'bwrap', 'browser_bwrap'):
        value = CONFIG.get(name)
        if not value or not Path(value).is_absolute():
            raise ValueError(f'runtime configuration requires absolute {name}')
    if not Path(PYTHON).is_relative_to(VENV):
        raise ValueError('Python must be inside the mounted virtual environment')
    from importlib.metadata import version
    for requirement in Path(REQUIREMENTS).read_text().splitlines():
        package, expected_version = requirement.split('==', 1)
        if version(package) != expected_version:
            raise ValueError(f'Python dependency differs from the evaluated lock: {package}')
    entry = CONFIG.get('providers', {}).get(route)
    if not isinstance(entry, dict) or set(entry) != PROVIDER_FIELDS:
        raise ValueError(f'runtime configuration requires providers.{route} with {sorted(PROVIDER_FIELDS)}')
    if entry['api_key_env'] != 'NONE' and not os.environ.get(entry['api_key_env']):
        raise ValueError(f"host environment lacks the key named by providers.{route}.api_key_env")
    expected = '499886cb0faa11dd765bff7e4241327df290a59c29877271a2847e68cd203fd5'
    for path in (BWRAP, BROWSER_BWRAP):
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('bubblewrap binary differs from the evaluated version')
