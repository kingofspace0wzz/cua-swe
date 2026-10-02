from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from .settings import ROOT, PYTHON, BROWSERS, CLIENT, BWRAP, BROWSER_BWRAP, REQUIREMENTS, PROFILE
CLIENT_SHA = 'ab510c98cf49f5f2d7b4728b9800e8929171790b6b3771b13bd2420e0c8464c5'

class Fault(Exception):
    def __init__(self, category, message):
        self.category = category
        super().__init__(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(path):
    path = Path(path).absolute()
    return {'path': str(path), 'sha256': sha(path)}


def verify_ref(ref):
    try:
        return Path(ref['path']).is_file() and sha(ref['path']) == ref['sha256']
    except (KeyError, OSError, TypeError):
        return False


def output_path(path):
    p = Path(path).absolute()
    resolved = p.resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    allowed = resolved.is_relative_to(ROOT) or (resolved.is_relative_to(temporary) and
               resolved != temporary and resolved.relative_to(temporary).parts[0].startswith('mobile-reconstruction-'))
    if not allowed or p != resolved:
        raise Fault('configuration', f'unsafe output path: {p}')
    return p


def write_json(path, value):
    p = output_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
    return evidence(p)


def relative(name):
    p = PurePosixPath(name)
    if not isinstance(name, str) or not name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise Fault('scope', f'unsafe relative path: {name!r}')
    if any(x in {'.git', '.env', 'environment.json', '.aws', '.ssh'} for x in p.parts):
        raise Fault('scope', f'forbidden path: {name}')
    return p


def matches(name, allowed):
    return any(name == p or (p.endswith('/') and name.startswith(p)) for p in allowed)


def tree(root, *, dependency=False):
    """Content+mode manifest. Never follows links; dependency links must stay inside mount."""
    root = Path(root).resolve(strict=True)
    rows = {}
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root).as_posix()
        # A solver Git repository is mounted separately at this empty directory.
        # Its generated metadata never enters the submitted source tree.
        if not dependency and rel == '.git' and p.is_dir() and not p.is_symlink() and not any(p.iterdir()):
            continue
        relative(rel)
        if p.is_symlink():
            target = os.readlink(p)
            if not dependency or Path(target).is_absolute() or not p.resolve().is_relative_to(root) or not p.resolve().exists():
                raise Fault('scope', f'unsafe symlink: {p} -> {target}')
            rows[rel] = {'link': target}
        elif p.is_file():
            if p.stat().st_nlink != 1:
                raise Fault('scope', f'hardlink rejected: {p}')
            rows[rel] = {'sha256': sha(p), 'executable': bool(p.stat().st_mode & 0o111)}
        elif not p.is_dir():
            raise Fault('scope', f'special file: {p}')
    return rows


@dataclass(frozen=True)
class Protocol:
    schema: int = 1
    name: str = 'mobile-reconstruction-v1'
    model: str = 'gpt-6-astra'
    provider: str = 'responses'
    responses: int = 60
    active_seconds: int = 2700
    reasoning: str = 'high'
    max_output_tokens: int = 16384
    transport_attempts: int = 1
    request_timeout_seconds: int = 600
    sampling: str = 'provider defaults; temperature/top_p/seed omitted, not guaranteed or supported'
    client_sha256: str = CLIENT_SHA
    def record(self):
        return asdict(self)


def toolchain_identity():
    import shutil
    paths = [Path(PYTHON).resolve(), Path(shutil.which('node') or '/usr/bin/node').resolve(),
             Path(BWRAP), Path(BROWSER_BWRAP), Path(REQUIREMENTS)]
    if PROFILE:
        paths.append(Path(PROFILE))
    fonts = [p for root in ('/usr/share/fonts', '/etc/fonts')
             for p in Path(root).rglob('*') if p.is_file()]
    return {'binaries_and_lock': {str(p): sha(p) for p in paths},
            'fonts_and_config': {str(p): sha(p) for p in sorted(fonts)}}


def harness_identity():
    implementation = Path(__file__).resolve().parents[3]
    return {'package': {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
            'entrypoint': sha(implementation / 'scripts/run_mobile_evaluation.py'),
            'provider_layer': sha(implementation / 'scripts/provider_client.py'),
            'regression_tests': {p.name: sha(p) for p in sorted((implementation / 'tests').glob('test_mobile*reconstruction*.py'))},
            'native_regression_tests': {p.name: sha(p) for p in sorted((implementation / 'tests').glob('test_mobile_frozen_native*.py'))},
            'toolchain': toolchain_identity()}


class Task:
    """Explicit, hash-pinned public file map: full ordinary source, never a recursive private bundle."""
    def __init__(self, config):
        self.c = config
        for key in ('task_id', 'revision', 'release', 'public_files', 'editable', 'instruction',
                    'dependencies', 'backend', 'expected_assertions'):
            if key not in config:
                raise Fault('configuration', f'missing config field {key}')
        if not config['expected_assertions'] or len(set(config['expected_assertions'])) != len(config['expected_assertions']):
            raise Fault('configuration', 'expected assertion IDs must be nonempty and unique')
        for name in config['public_files']:
            relative(name)
        for name in config.get('scratch', []):
            relative(name.rstrip('/'))
            if name == 'TASK.md' or any(matches(n, [name]) for n in config['public_files']):
                raise Fault('configuration', 'scratch overlaps public source')
        for name in config['editable']:
            relative(name.rstrip('/'))
        if matches('TASK.md', config['editable']):
            raise Fault('configuration', 'TASK.md is not editable')
        if 'TASK.md' in config['public_files']:
            raise Fault('configuration', 'TASK.md supplied only by instruction')
        if not 1 <= config['backend'].get('timeout_seconds', 170) <= 170:
            raise Fault('configuration', 'backend timeout must be 1..170')
        self.id = digest({k: v for k, v in config.items() if k != 'controls'})

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def validate_inputs(self):
        if not verify_ref(self.c['instruction']):
            raise Fault('missing_instruction', 'instruction absent or digest mismatch')
        if not Path(self.c['instruction']['path']).read_text().strip():
            raise Fault('missing_instruction', 'empty instruction')
        for name, ref in self.c['public_files'].items():
            p = Path(ref['path'])
            if p.is_symlink() or not verify_ref(ref):
                raise Fault('source', f'public source missing/changed: {name}')
        for dep in self.c['dependencies']:
            dest = str(relative(dep['destination']))
            if any(n == dest or n.startswith(dest + '/') for n in self.c['public_files']) or matches(dest, self.c['editable']):
                raise Fault('configuration', 'dependency overlaps public/edit boundary')
            if digest(tree(dep['path'], dependency=True)) != dep['sha256']:
                raise Fault('source', f'dependency digest mismatch: {dest}')
        for key in ('protected', 'adapter'):
            ref = self.c['backend'].get(key)
            if ref and digest(tree(ref['path'], dependency=True)) != ref['sha256']:
                raise Fault('configuration', f'{key} digest mismatch')
        if self.c['backend'].get('browser_runtime'):
            if digest(tree(BROWSERS, dependency=True)) != self.c['backend'].get('browser_sha256'):
                raise Fault('configuration', 'browser installation not hash pinned')
        if '153' in self.c['task_id'] and not self.c['backend'].get('capture'):
            raise Fault('baseline', '153 requires pre-agent reference capture')

    @property
    def identity(self):
        return {'task_id': self.c['task_id'], 'revision': self.c['revision'], 'release': self.c['release'],
                'task_digest': self.id, 'runtime_digest': digest(self.c['backend']),
                'source_digest': digest(self.c['public_files']), 'instruction_sha256': self.c['instruction']['sha256']}
