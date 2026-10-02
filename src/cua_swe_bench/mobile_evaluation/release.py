"""Manifest-only selection, immutable input verification, and portable relocation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MANIFEST = 'dataset/mobile/manifest.json'
RELEASE = 'dataset/mobile/releases/mobile20-20260922'
MODELS = {
    'api-gpt56-sol': 'gpt56-sol', 'api-gpt56-luna': 'gpt56-luna',
    'api-gpt56-terra': 'gpt56-terra', 'api-gpt6-astra': 'gpt6-astra',
    'api-opus48': 'claude-opus48', 'api-sonnet5': 'claude-sonnet5',
    'api-fable5': 'claude-fable5', 'api-grok46': 'grok46', 'codex-gpt56-sol': 'codex-sol',
}
DEFERRED = {'api-opus5', 'claude-code-opus5'}


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contained(root, name):
    root = Path(root).resolve()
    p = root / name
    if Path(name).is_absolute() or '..' in Path(name).parts or p.is_symlink() or not p.resolve().is_relative_to(root):
        raise ValueError('input reference escapes its frozen bundle')
    return p


def validate_release(repo=REPO):
    repo = Path(repo)
    manifest = load(repo / MANIFEST)
    lineage = load(repo / RELEASE / 'task-lineage.json')
    rows, records = manifest['tasks'], lineage['tasks']
    if len(rows) != 20 or len(records) != 20 or [r['task_id'] for r in rows] != [r['task_id'] for r in records]:
        raise ValueError('Mobile release must bind exactly twenty ordered tasks')
    files = 0
    for row, record in zip(rows, records):
        spec_path = contained(repo, row['task_file'])
        if sha(spec_path) != record['canonical_task_spec_sha256'] or load(spec_path) != record['canonical_spec']:
            raise ValueError(f"task specification changed: {row['task_id']}")
        if row['evaluated_task_digest'] != record['evaluated_task_digest']:
            raise ValueError('evaluated task lineage mismatch')
        for ref in record['files']:
            name, expected = ref['path'], ref['sha256']
            path = contained(spec_path.parent, name)
            if sha(path) != expected:
                raise ValueError(f"frozen task input changed: {row['task_id']}/{name}")
            files += 1
    summary = load(repo / RELEASE / 'evaluation-summary.json')
    expected_cells = {(r['task_id'], m, c) for r in rows for m in (*MODELS, *DEFERRED)
                      for c in (['cua'] if m in {'codex-gpt56-sol', 'claude-code-opus5'} else ['code-only', 'cua'])}
    cells = summary['rows']
    if len(cells) != 400 or {(r['task_id'], r['model_key'], r['condition']) for r in cells} != expected_cells:
        raise ValueError('reviewed evaluation matrix differs from the release')
    ids = {r['task_id']: r['evaluated_task_digest'] for r in rows}
    for cell in cells:
        if cell['task_digest'] != ids[cell['task_id']]:
            raise ValueError('evaluation cell belongs to a different revision')
        if cell['success'] and not cell['scorable']:
            raise ValueError('excluded cell cannot earn success')
        if cell['capability_failure_credit'] and (not cell['scorable'] or cell['success']):
            raise ValueError('invalid behavioral failure credit')
    totals = {'executed': sum(r['executed'] for r in cells), 'scorable': sum(r['scorable'] for r in cells),
              'successes': sum(r['success'] is True for r in cells),
              'behavioral_failures': sum(r['capability_failure_credit'] for r in cells),
              'excluded': sum(r['executed'] and not r['scorable'] for r in cells),
              'user_deferred': sum(not r['executed'] for r in cells)}
    if any(summary[k] != v for k, v in totals.items()):
        raise ValueError('reviewed result totals do not reconcile')
    pins = load(repo / 'dataset/mobile/evaluation/runtime-manifest.json')
    for name, expected in pins['files'].items():
        if sha(contained(repo, name)) != expected:
            raise ValueError(f'protected evaluator changed: {name}')
    return {'valid': True, 'task_count': 20, 'frozen_files': files, **totals}


def materialize(row, destination, repo=REPO):
    """Rebind paths and control identity only; never regenerate task content."""
    from .core import Task, digest
    spec_path = contained(repo, row['task_file'])
    source = load(spec_path)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)

    def resolve(value):
        if isinstance(value, dict):
            return {k: str(contained(spec_path.parent, v).resolve()) if k == 'path' and isinstance(v, str)
                    and not v.startswith('/') else resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    config = resolve(deepcopy(source))
    task = Task(config)
    rebounds = {}
    for name, control in config['controls'].items():
        original = load(control['patch']['path'])
        if original['task_digest'] != row['evaluated_task_digest']:
            raise ValueError('control is not bound to the evaluated task')
        patch = {**original, 'task_digest': task.id}
        path = destination / f'{name}.json'
        path.write_text(json.dumps(patch, indent=2) + '\n')
        control['patch'] = {'path': str(path.resolve()), 'sha256': sha(path)}
        rebounds[name] = {'original_sha256': digest(original), 'runtime_sha256': digest(patch)}
    path = destination / 'task.json'
    path.write_text(json.dumps(config, indent=2) + '\n')
    (destination / 'lineage.json').write_text(json.dumps({
        'evaluated_task_digest': row['evaluated_task_digest'], 'runtime_task_digest': task.id,
        'canonical_task_spec_sha256': sha(spec_path), 'controls': rebounds,
    }, indent=2) + '\n')
    return path
