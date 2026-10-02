from __future__ import annotations
import json
from pathlib import Path
from .core import Fault, PYTHON, digest, evidence, output_path, tree, write_json
from .sandbox import Sandbox, process
from .workspace import prepare, apply


def interpret(raw, expected):
    """Assertion truth, completeness, evaluator health and candidate errors are distinct."""
    if not isinstance(raw, dict) or raw.get('errors') != []:
        raise Fault('grader', 'missing/raised evaluator errors')
    if raw.get('execution') == 'candidate_error':
        err = raw.get('candidate_error', {})
        if err.get('kind') not in ('syntax', 'app_crash', 'behavioral_timeout') or not err.get('evidence'):
            raise Fault('grader', 'unattributed candidate error')
        return {'correct': False, 'candidate_error': err}
    if raw.get('execution') != 'complete' or raw.get('expected_assertions') != expected:
        raise Fault('grader', 'execution/assertion manifest mismatch')
    assertions = raw.get('assertions', [])
    if not isinstance(assertions, list) or len(assertions) != len(expected):
        raise Fault('grader', 'incomplete assertions')
    if {a.get('id') for a in assertions} != set(expected) or any(type(a.get('passed')) is not bool for a in assertions):
        raise Fault('grader', 'duplicate, absent, or non-boolean assertions')
    return {'correct': all(a['passed'] for a in assertions), 'assertions': assertions}


def protected_command(task, workspace, root, command, baseline=None):
    root = output_path(root)
    root.mkdir(parents=True, exist_ok=False)
    mounts = [(root, '/artifacts', True)]
    for key in ('protected', 'adapter'):
        if task.c['backend'].get(key):
            mounts.append((task.c['backend'][key]['path'], '/' + key, False))
    if baseline:
        mounts.append((baseline, '/baseline', False))
    # Commands are trusted config, candidate scripts still have zero host credentials/network.
    sb = Sandbox(workspace, task.c['dependencies'])
    extra = task.c['backend'].get('browser_runtime', False)
    if extra:
        from .core import BROWSERS
        mounts.append((BROWSERS, BROWSERS, False))
    argv = sb.argv(command, mounts)
    result = process(argv, timeout=task.c['backend'].get('timeout_seconds', 170))
    write_json(root / 'process.json', result)
    if result['timed_out']:
        raise Fault('grader', 'protected command timeout, not a model score')
    return result


def capture(task, root):
    """Must run before exposing candidate workspace, not after candidate changes (153)."""
    root = output_path(root)
    root.mkdir(parents=True, exist_ok=False)
    baseline = prepare(task, root / 'source')
    write_json(root / 'source-manifest.json', baseline)
    command = task.c['backend'].get('capture')
    native = bool(task.c['backend'].get('native'))
    if native or command:
        if native:
            from .native_backend import native_operation
            p = native_operation(task, root / 'source', root / 'reference', 'capture')
        else:
            p = protected_command(task, root / 'source', root / 'reference', command)
        path = root / 'reference' / 'baseline.json'
        try:
            raw = json.loads(path.read_text())
            if p['returncode'] != 0 or raw.get('execution') != 'complete' or raw.get('errors') != [] or not raw.get('state'):
                raise ValueError('invalid baseline capture')
            if native:
                required_kind = ('native_hook_pre_edit' if task.c['backend']['native']['capture_required']
                                 else 'source_only_explicit_backend')
                if raw.get('task_digest') != task.id or raw.get('capture_kind') != required_kind:
                    raise ValueError('native baseline identity/capture kind mismatch')
        except (OSError, ValueError) as exc:
            raise Fault('baseline', 'missing/invalid pre-agent reference state') from exc
        # Keep full images and reference data manifest outside the solver.
        # Native references include only trusted capture data and its artifacts.
        # Build scratch/output never becomes the verifier's reference material.
        if native:
            captured = {'baseline': evidence(path), 'artifacts': tree(root / 'reference' / 'artifacts')}
        else:
            captured = tree(root / 'reference')
        write_json(root / 'reference-manifest.json', captured)
    else:
        (root / 'reference').mkdir()
        write_json(root / 'reference' / 'baseline.json', {'execution': 'complete', 'errors': [],
                    'state': {'source_digest': digest(baseline)}, 'capture_kind': 'source_only_explicit_backend'})
    return baseline, root / 'reference'


def grade_once(task, baseline, patch, reference, root):
    root = output_path(root)
    root.mkdir(parents=True, exist_ok=False)
    clean = prepare(task, root / 'source')
    if clean != baseline or not (Path(reference) / 'baseline.json').is_file():
        raise Fault('baseline', 'clean baseline/source reference missing or changed')
    apply(task, baseline, patch, root / 'source')
    command = task.c['backend'].get('grade')
    if task.c['backend'].get('native'):
        from .native_backend import native_operation
        result = native_operation(task, root / 'source', root / 'verifier', 'grade', baseline=reference)
    else:
        if not isinstance(command, list) or not command:
            raise Fault('configuration', 'backend.grade argv required')
        result = protected_command(task, root / 'source', root / 'verifier', command, reference)
    path = root / 'verifier' / 'result.json'
    try:
        raw = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise Fault('grader', 'missing/invalid structured verifier JSON') from exc
    verdict = interpret(raw, task.c['expected_assertions'])
    if 'candidate_error' not in verdict and any(marker in (result['stdout'] + result['stderr']) for marker in ('Traceback (most recent call last):', 'UnhandledPromiseRejection', 'UNHANDLED_EVALUATOR_EXCEPTION')):
        raise Fault('grader', 'unhandled evaluator exception in process log despite structured result')
    # Nonzero is not itself a failed repair. Explicit assertion failure may legitimately exit 1.
    if result['returncode'] not in (0, 1) or (result['returncode'] != 0 and verdict['correct']):
        raise Fault('grader', 'verifier process/JSON mismatch')
    verdict['result'] = evidence(path)
    return verdict


def grade(task, baseline, patch, reference, root):
    one = grade_once(task, baseline, patch, reference, Path(root) / 'first')
    if not one['correct']:
        two = grade_once(task, baseline, patch, reference, Path(root) / 'replay')
        comparable = lambda v: {k: v[k] for k in ('correct', 'assertions', 'candidate_error') if k in v}
        if comparable(one) != comparable(two):
            raise Fault('grader', 'failure not reproducible in pristine replay')
        one['replay'] = two
    write_json(Path(root) / 'grade.json', one)
    return one


def controls(task, root):
    baseline, reference = capture(task, Path(root) / 'baseline')
    empty = {'schema': 1, 'task_digest': task.id, 'baseline_digest': digest(baseline), 'changes': []}
    cases = {'broken': (empty, False)}
    for name, row in task.c.get('controls', {}).items():
        from .core import verify_ref
        if not verify_ref(row['patch']):
            raise Fault('configuration', f'control patch absent/changed: {name}')
        cases[name] = (json.loads(Path(row['patch']['path']).read_text()), row['correct'])
    if not {'gold', 'alternative', 'partial'} <= set(cases):
        raise Fault('configuration', 'controls require gold, alternative and partial patches')
    outcomes = {}
    for name, (patch, correct) in cases.items():
        verdict = grade(task, baseline, patch, reference, Path(root) / name)
        if type(correct) is not bool or verdict['correct'] is not correct:
            raise Fault('grader', f'control mismatch: {name}')
        outcomes[name] = verdict
    result = {'passed': True, 'task_digest': task.id, 'outcomes': outcomes,
              'baseline_manifest': evidence(Path(root) / 'baseline/source-manifest.json')}
    write_json(Path(root) / 'controls.json', result)
    return baseline, reference, result
