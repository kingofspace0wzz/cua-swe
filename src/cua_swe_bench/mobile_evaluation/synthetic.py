"""Executable local controls. Scripted Responses transport, not a paid model or task certification."""
from __future__ import annotations
import base64
import copy
import json
from pathlib import Path
from .core import Fault, PYTHON, Protocol, Task, digest, evidence, output_path, tree, write_json
from .workspace import prepare, extract

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg=='
# Produce a valid PNG with Pillow in fixture creation; no browser observations are performed.


def fixture(root):
    root = output_path(root); root.mkdir(parents=True, exist_ok=False)
    pub = root / 'public'; pub.mkdir()
    (pub / 'value.txt').write_text('0\n')
    (pub / 'context.txt').write_text('Ordinary public context, retained outside edit boundary.\n')
    (pub / 'instruction.md').write_text('Repair value.txt to contain an integer whose square is 4. Both 2 and -2 are correct. Preserve context.txt.\n')
    private = root / 'protected'; private.mkdir()
    (private / 'grader.py').write_text('''import json,pathlib
root=pathlib.Path('/workspace')
try:
 value=int((root/'value.txt').read_text())
 result={'execution':'complete','errors':[],'expected_assertions':['square','context'],'assertions':[{'id':'square','passed':value*value==4},{'id':'context','passed':(root/'context.txt').read_text().startswith('Ordinary public context')}]}
except ValueError:
 result={'execution':'candidate_error','errors':[],'candidate_error':{'kind':'syntax','evidence':'value.txt is not an integer'}}
except Exception as e:
 result={'execution':'exception','errors':[repr(e)]}
pathlib.Path('/artifacts/result.json').write_text(json.dumps(result))
''')
    (private / 'capture.py').write_text('''import json,pathlib
assert pathlib.Path('/workspace/value.txt').read_text()=='0\\n'
pathlib.Path('/artifacts/baseline.json').write_text(json.dumps({'execution':'complete','errors':[],'state':{'broken_value':0}}))
''')
    adapter = root / 'adapter'; adapter.mkdir()
    from PIL import Image
    Image.new('RGB', (4, 4), 'blue').save(adapter / 'control.png')
    (adapter / 'action.py').write_text('''import json,pathlib,shutil,sys
r=json.load(sys.stdin)
assert r['url']=='http://127.0.0.1:8123/' and r['pixels_only']
shutil.copyfile('/adapter/control.png','/artifacts/current.png')
print(json.dumps({'url':r['url'],'screenshot':'/artifacts/current.png','observation':'pixels'}))
''')
    config = {'task_id': 'synthetic-shell-pixel-control', 'revision': 'synthetic-1', 'release': 'construction-control-only',
              'instruction': evidence(pub / 'instruction.md'),
              'public_files': {'value.txt': evidence(pub / 'value.txt'), 'context.txt': evidence(pub / 'context.txt')},
              'editable': ['value.txt', 'added/', 'remove.txt'], 'scratch': ['dist/'], 'dependencies': [],
              'expected_assertions': ['square', 'context'],
              'backend': {'protected': {'path': str(private), 'sha256': digest(tree(private))},
                          'adapter': {'path': str(adapter), 'sha256': digest(tree(adapter))},
                          'capture': [PYTHON, '-I', '/protected/capture.py'],
                          'grade': [PYTHON, '-I', '/protected/grader.py'],
                          'runtime': {'interface': 'cua-swe-adapter-pixels-v1', 'url': 'http://127.0.0.1:8123/',
                                      'services': [], 'ready': [PYTHON, '-I', '-c', 'print(\'{"ready":true}\')'],
                                      'action': [PYTHON, '-I', '/adapter/action.py']}}}
    task = Task(config)
    baseline = prepare(task, root / 'patch-source')
    for name, val, correct in [('gold', '2', True), ('alternative', '-2', True), ('partial', '1', False)]:
        (root / 'patch-source/value.txt').write_text(val + '\n')
        patch = extract(task, baseline, root / 'patch-source')
        ref = write_json(root / f'{name}.patch.json', patch)
        config.setdefault('controls', {})[name] = {'patch': ref, 'correct': correct}
    write_json(root / 'task.json', config)
    return Task(config)


class ScriptedClient:
    """Deterministic local transport double exercising EXACT agent request/tool/image path."""
    def __init__(self, mode='code-only', failure=None):
        self.mode, self.failure, self.calls = mode, failure, 0
        self.inputs = []
    def create(self, items, previous_response_id=None):
        self.calls += 1; self.inputs.append(copy.deepcopy(items))
        if self.failure == 'provider': raise RuntimeError('injected provider interruption; no retry')
        if self.mode == 'cua' and self.calls == 1:
            call = ('browser', {'action': {'type': 'screenshot'}})
        elif self.mode == 'cua' and self.calls == 2:
            assert any(c.get('type') == 'input_image' for x in items for c in x.get('content', [])), 'missing pixels'
            call = ('shell', {'command': "printf '2\\n' > value.txt"})
        elif self.mode != 'cua' and self.calls == 1:
            call = ('shell', {'command': "printf '2\\n' > value.txt"})
        else:
            call = ('finish', {'summary': 'Synthetic repair submitted.'})
        return {'id': f'synthetic-response-{self.calls}', 'model': 'wrong.model' if self.failure == 'wrong_model' else Protocol().model,
                'status': 'completed', 'usage': {'input_tokens': 0, 'output_tokens': 0, 'synthetic': True},
                'output': [{'type': 'function_call', 'call_id': f'call-{self.calls}', 'name': call[0], 'arguments': json.dumps(call[1])}]}


def preflight(root):
    from .runner import run_attempt
    root = output_path(root); root.mkdir(parents=True, exist_ok=False)
    task = fixture(root / 'fixture')
    results = {}
    for condition in ('code-only', 'cua'):
        client = ScriptedClient(condition)
        result, ref = run_attempt(task, root / condition, condition, 'development', 1,
                                 client_factory=lambda *a: client, synthetic=True)
        ok = result['classification']['classification'] == 'valid_success'
        if condition == 'cua': ok &= result['classification']['cua_used']
        else: ok &= result['classification']['success_without_cua']
        results[condition] = {'passed': bool(ok), 'attempt': ref}
    result = {'classification': 'synthetic_no_paid_model_harness_control_not_admission',
              'passed': all(x['passed'] for x in results.values()), 'controls': results,
              'native_mobile_certified': False, 'provider_called': False}
    write_json(root / 'preflight.json', result)
    return result


def full_preflight(root):
    """CLI preflight includes every regression, plus real isolated synthetic paired trajectories."""
    from concurrent.futures import ThreadPoolExecutor
    from .sandbox import process
    from .core import harness_identity
    result = preflight(root)
    tests = Path(__file__).resolve().parents[3] / 'tests'
    suites = {'shared': tests / 'test_mobile_reconstruction.py',
              'native': tests / 'test_mobile_native_backend.py'}
    regressions = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {name: pool.submit(process, [PYTHON, '-B', '-W', 'error::ResourceWarning', str(path)],
                                 timeout=170) for name, path in suites.items()}
        for name, job in jobs.items():
            run = job.result()
            log = Path(root) / f'{name}-regression-process.json'
            write_json(log, run)
            marker = [line.split('=', 1)[1] for line in run['stdout'].splitlines()
                      if line.startswith('TEST_RESULT_JSON=')]
            try:
                regression = json.loads(Path(marker[-1]).read_text())
                regression_ref = evidence(marker[-1])
                passed = (regression['passed'] is True and regression['tests_run'] >= 26
                          and not regression.get('skipped') and not run['timed_out'] and run['returncode'] == 0)
            except (OSError, IndexError, KeyError, ValueError):
                passed, regression_ref = False, None
            regressions[name] = {'passed': passed, 'result': regression_ref, 'process': evidence(log)}
    result.update(passed=result['passed'] and all(r['passed'] for r in regressions.values()),
                  regressions=regressions, harness_digest=digest(harness_identity()))
    write_json(Path(root) / 'full-preflight.json', result)
    return result
