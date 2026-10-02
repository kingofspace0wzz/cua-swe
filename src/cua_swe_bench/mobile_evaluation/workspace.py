from __future__ import annotations
import base64
import os
import shutil
from pathlib import Path
from .core import Fault, digest, evidence, matches, output_path, relative, sha, tree, write_json


def prepare(task, destination):
    task.validate_inputs()
    root = output_path(destination)
    root.mkdir(parents=True, exist_ok=False)
    for name, ref in task.c['public_files'].items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ref['path'], p)
        p.chmod(0o755 if ref.get('executable') else 0o644)
    shutil.copyfile(task.c['instruction']['path'], root / 'TASK.md')
    for d in task.c['dependencies']:
        (root / d['destination']).mkdir(parents=True, exist_ok=True)
    return tree(root)


def prepare_git_metadata(workspace, destination):
    """Give ordinary Git tools a public-source baseline without submitting .git."""
    import subprocess
    root, metadata = Path(workspace).resolve(), output_path(destination)
    metadata.mkdir(parents=True, exist_ok=False)
    env = {
        'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_AUTHOR_NAME': 'Mobile benchmark', 'GIT_AUTHOR_EMAIL': 'benchmark@invalid',
        'GIT_COMMITTER_NAME': 'Mobile benchmark', 'GIT_COMMITTER_EMAIL': 'benchmark@invalid',
        'GIT_AUTHOR_DATE': '2000-01-01T00:00:00Z',
        'GIT_COMMITTER_DATE': '2000-01-01T00:00:00Z',
    }
    base = ['git', '-c', 'core.hooksPath=/dev/null']
    commands = [
        base + ['-c', 'init.templateDir=', 'init', '--bare', '--quiet', str(metadata)],
        base + ['--git-dir', str(metadata), '--work-tree', str(root),
                'add', '--force', '--all', '--', '.'],
        base + ['--git-dir', str(metadata), '--work-tree', str(root),
                'commit', '--quiet', '--allow-empty', '-m', 'Frozen public baseline'],
        base + ['--git-dir', str(metadata), 'config', 'core.bare', 'false'],
        base + ['--git-dir', str(metadata), 'config', 'core.worktree', '/workspace'],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                text=True, timeout=120)
        if result.returncode:
            raise Fault('source', f'public Git baseline setup failed: {result.stderr}')
    commit = subprocess.run(base + ['--git-dir', str(metadata), '--work-tree', str(root), 'rev-parse', 'HEAD'],
                            env=env, capture_output=True, text=True, timeout=10, check=True)
    (root / '.git').mkdir(exist_ok=False)
    return {'commit': commit.stdout.strip(), 'metadata_path': str(metadata),
            'public_source_only': True, 'submitted': False}


def extract(task, baseline, workspace):
    if not baseline or 'TASK.md' not in baseline:
        raise Fault('baseline', 'missing pre-agent source manifest')
    current = tree(workspace)
    changes = []
    for name in sorted(set(baseline) | set(current)):
        before, after = baseline.get(name), current.get(name)
        if before == after or (before is None and matches(name, task.c.get('scratch', []))):
            continue
        if not matches(name, task.c['editable']):
            raise Fault('scope', f'disallowed edit: {name}')
        changes.append({'path': name, 'before': before, 'after': after,
                        'content_b64': base64.b64encode((Path(workspace) / name).read_bytes()).decode() if after else None})
    return {'schema': 1, 'task_digest': task.id, 'baseline_digest': digest(baseline), 'changes': changes}


def apply(task, baseline, patch, destination):
    if patch.get('task_digest') != task.id or patch.get('baseline_digest') != digest(baseline):
        raise Fault('scope', 'patch identity mismatch')
    # Require exactly clean input; never overlay a running/dirty candidate tree.
    if tree(destination) != baseline:
        raise Fault('baseline', 'patch destination is not clean baseline')
    seen = set()
    for c in patch['changes']:
        name = str(relative(c['path']))
        if name in seen or not matches(name, task.c['editable']) or c['before'] != baseline.get(name):
            raise Fault('scope', f'invalid patch path/preimage: {name}')
        seen.add(name)
        p = Path(destination) / name
        if c['after'] is None:
            if c['before'] is None:
                raise Fault('scope', 'deletion has no preimage')
            p.unlink()
        else:
            raw = base64.b64decode(c['content_b64'], validate=True)
            import hashlib
            if c['after'] != {'sha256': hashlib.sha256(raw).hexdigest(), 'executable': c['after'].get('executable')} or type(c['after']['executable']) is not bool:
                raise Fault('scope', 'invalid patch postimage')
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            p.chmod(0o755 if c['after']['executable'] else 0o644)
    return tree(destination)


def sync(task, baseline, patch, destination):
    """Reset runtime source at every tool boundary, including additions and deletions."""
    root = output_path(destination)
    if root.exists():
        shutil.rmtree(root)
    actual = prepare(task, root)
    if actual != baseline:
        raise Fault('source', 'source changed during attempt')
    apply(task, baseline, patch, root)
