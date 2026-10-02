"""Public API extension of the Mobile native runtime and verifier."""
from __future__ import annotations
from dataclasses import replace
import json
import os
import shutil
from pathlib import Path
import sys
from provider_client import ProviderClient, ProviderConfig


def configure(plan):
    path = Path(plan['runtime_config'])
    config = json.loads(path.read_text())
    for key in ('output_root', 'python', 'venv', 'browsers', 'bwrap', 'browser_bwrap'):
        if key not in config or not Path(config[key]).is_absolute():
            raise ValueError(f'Mobile runtime requires an absolute {key}')
    if not Path(plan['output_root']).resolve().is_relative_to(Path(config['output_root']).resolve()):
        raise ValueError('--output-root must be inside runtime-config output_root')
    if Path(config['python']).absolute() != Path(sys.executable).absolute():
        raise ValueError('run with the Python executable selected in runtime-config')
    if not Path(config['python']).absolute().is_relative_to(Path(config['venv']).absolute()):
        raise ValueError('runtime Python must be inside its virtual environment')
    for key in ('python', 'bwrap', 'browser_bwrap'):
        if not Path(config[key]).is_file():
            raise ValueError(f'Mobile runtime executable missing: {key}')
    os.environ['CUA_MOBILE_CONFIG'] = str(path.resolve())


def materialize_task(row, destination, browser_digest):
    from cua_swe_bench.mobile_evaluation import release, core
    path = release.materialize(row, destination)
    config = json.loads(path.read_text())
    original_browser = config['backend'].get('browser_sha256')
    config['backend']['browser_sha256'] = browser_digest
    task = core.Task(config)
    # Controls identify the relocated task, including this run's browser identity.
    for control in config['controls'].values():
        patch_path = Path(control['patch']['path'])
        patch = json.loads(patch_path.read_text())
        patch['task_digest'] = task.id
        patch_path.write_text(json.dumps(patch, indent=2) + '\n')
        control['patch']['sha256'] = core.sha(patch_path)
    path.write_text(json.dumps(config, indent=2) + '\n')
    lineage_path = path.parent / 'lineage.json'
    lineage = json.loads(lineage_path.read_text())
    lineage.update(runtime_task_digest=task.id, paper_browser_sha256=original_browser,
                   runtime_browser_sha256=browser_digest,
                   controls={name: {'runtime_sha256': core.digest(json.loads(Path(ref['patch']['path']).read_text()))}
                             for name, ref in config['controls'].items()})
    lineage_path.write_text(json.dumps(lineage, indent=2) + '\n')
    return core.Task(config)


def install(plan):
    from cua_swe_bench.mobile_evaluation import agent, admission, core, runner
    config = ProviderConfig(**plan['provider'])
    from cua_swe_bench.mobile_evaluation import native_worker, sandbox, settings
    from public_taskbundle import python_runtime_paths
    # Native supervisors use host runtime paths. The source namespace keeps /home
    # absent and mounts an equivalent Python environment under /runtime instead.
    bindings = [item for root in python_runtime_paths() for item in ('--ro-bind', str(root.resolve()), str(root))]
    original_namespace = native_worker.namespace_base
    native_worker.namespace_base = lambda **kw: original_namespace(**kw) + bindings
    runtime_view = Path(plan['output_root']) / 'source-runtime'
    (runtime_view / 'bin').mkdir(parents=True)
    python_version = f'python{sys.version_info.major}.{sys.version_info.minor}'
    site_relative = Path('lib') / python_version / 'site-packages'
    (runtime_view / site_relative).mkdir(parents=True)
    shutil.copy2(Path(sys.executable).resolve(), runtime_view / 'bin/python')
    (runtime_view / 'pyvenv.cfg').write_text('home = /runtime/python/bin\ninclude-system-site-packages = false\n')
    sandbox.PYTHON = '/runtime/venv/bin/python'
    original_argv = sandbox.Sandbox.argv
    def argv(self, *args, **kwargs):
        values = original_argv(self, *args, **kwargs)
        index = next(i for i in range(len(values) - 2)
                     if values[i:i+3] == ['--ro-bind', settings.VENV, settings.VENV])
        values[index:index+3] = [
            '--ro-bind', str(Path(sys.base_prefix).resolve()), '/runtime/python',
            '--ro-bind', str(runtime_view), '/runtime/venv',
            '--ro-bind', str(Path(settings.VENV) / site_relative), str(Path('/runtime/venv') / site_relative)]
        return values
    sandbox.Sandbox.argv = argv
    protocol = replace(core.Protocol(), name='cua-swe-public-api-mobile-v1',
                       model=config.model, provider=config.provider,
                       reasoning='provider-default', sampling='provider defaults',
                       max_output_tokens=config.max_output_tokens, request_timeout_seconds=config.timeout,
                       client_sha256=plan['extension']['files']['provider_client.py'])
    agent.Protocol = admission.Protocol = runner.Protocol = lambda: protocol
    base_identity = runner.harness_identity
    runner.harness_identity = lambda: {**base_identity(), 'public_extension': plan['extension']}
    token = os.environ.pop('CUA_SWE_PROVIDER_TOKEN', '')
    return lambda protocol, tools, root: ProviderClient(config, tools, token=token, trace_dir=Path(root) / 'provider')


def main():
    plan = json.loads(Path(sys.argv[1]).read_text())
    configure(plan)  # settings are read once when the evaluator package is imported
    from cua_swe_bench.mobile_evaluation import release, core, runner, admission
    release.validate_release()
    browser_digest = core.digest(core.tree(core.BROWSERS, dependency=True))
    factory = install(plan)
    output = Path(plan['output_root'])
    rows = []
    for index, row in enumerate(plan['tasks']):
        task = materialize_task(row, output / 'inputs' / row['task_id'], browser_digest)
        task.validate_inputs()
        result, ref = runner.run_attempt(task, output / 'attempts' / row['task_id'],
                                        plan['condition'], 'evaluation', 1, client_factory=factory)
        classification = result['classification']
        valid = classification['scorable'] and admission.validate_evidence(result)
        rows.append({'task_id': row['task_id'], 'attempt': ref, 'scorable': valid,
                     'success': classification['software_correct'] if valid else None,
                     'classification': classification, 'evidence_valid': valid})
        print(json.dumps(rows[-1]), flush=True)
    scorable = sum(r['scorable'] for r in rows)
    successes = sum(r['success'] is True for r in rows)
    summary = {'domain': 'mobile', 'condition': plan['condition'], 'provider': plan['provider'],
               'selected': len(rows), 'scorable': scorable, 'successes': successes,
               'excluded': len(rows) - scorable, 'success_rate': successes / scorable if scorable else None,
               'rows': rows}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if scorable == len(rows) else 2


if __name__ == '__main__':
    raise SystemExit(main())
