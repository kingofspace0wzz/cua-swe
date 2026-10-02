"""Provider extension of the Web, Game, and DevOps protected TaskBundle runners."""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
from dataclasses import replace
from functools import lru_cache
import re
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
AGENT_LEASE_ENV_NAMES = ('CUA_SWE_PROVIDER_CONFIG', 'CUA_SWE_GATEWAY_TOKEN')


def python_runtime_paths():
    """Standalone Python roots, including aliases targeted by virtualenv symlinks."""
    paths = [Path(sys.base_prefix)]
    executable = Path(sys.executable)
    seen = set()
    while executable.is_symlink() and str(executable) not in seen:
        seen.add(str(executable))
        target = Path(os.readlink(executable))
        executable = target if target.is_absolute() else executable.parent / target
        if executable.parent.name == 'bin':
            paths.append(executable.parent.parent)
    return list(dict.fromkeys(p for p in paths if not p.is_relative_to('/usr') and p.exists()))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_harness(domain):
    if domain == 'web':
        from run_web_clean_ablation import FROZEN_ROOT, validate_frozen_sources
        validate_frozen_sources()
        sys.path[:0] = [str(FROZEN_ROOT / 'scripts'), str(FROZEN_ROOT / 'src')]
        harness = importlib.import_module('run_clean_ablation')
        support = load_module('_public_web_reporting', FROZEN_ROOT / 'runtime_and_reporting.py')
        support.install(harness, json.loads((FROZEN_ROOT / 'runtime-pins.json').read_text()))
        return harness
    return importlib.import_module('run_game_clean_ablation' if domain == 'game' else 'run_clean_ablation')


def terminal_notice_errors(trace, harness):
    """A strace terminal signal notice after exit_group is not another process action."""
    benign = set()
    candidates = {m[1] for error in trace.audit_errors
                  if (m := re.fullmatch(r'PID (\d+) produced events after exit', error))}
    for pid in candidates:
        exited = False
        post_exit = []
        for line in trace.lines:
            if harness._strace_pid(line) != pid:
                continue
            body = harness._strace_body(line)
            if re.match(r'(exit|exit_group)\(-?\d+\)', body) or re.match(r'<\.\.\. (exit|exit_group) resumed>\)\s+=\s+\?', body):
                exited = True
                continue
            if exited and not body.startswith('+++ exited'):
                post_exit.append(body)
        if post_exit and all(re.fullmatch(r'\+\+\+ killed by SIG[A-Z0-9]+(?: \(core dumped\))? \+\+\+', b) for b in post_exit):
            benign.add(f'PID {pid} produced events after exit')
    return tuple(error for error in trace.audit_errors if error not in benign)


def install(harness, plan):
    """Change the agent transport and its identity; retain source isolation and grading."""
    config = plan['provider']
    original_trace = harness._host_trace_attribution
    @lru_cache(maxsize=64)
    def attribution(path):
        trace = original_trace(path)
        return replace(trace, audit_errors=terminal_notice_errors(trace, harness))
    harness._host_trace_attribution = attribution
    original_mounts = harness._bubblewrap_runtime_mounts
    def mounts(*args, **kwargs):
        return list(dict.fromkeys([*original_mounts(*args, **kwargs), *python_runtime_paths()]))
    harness._bubblewrap_runtime_mounts = mounts
    harness.MODELS = [harness.ModelSpec('public-agent', config['model'], 'responses', config['model'])]
    original_names = harness._expected_tool_names

    def names(condition, runtime):
        return list(dict.fromkeys([*original_names(condition, runtime), 'baseline_responses_agent.py', 'provider_client.py']))

    def copy_tools(isolated_root, condition, runtime='responses'):
        scripts = isolated_root / 'tools' / 'scripts'
        scripts.mkdir(parents=True)
        for name in original_names(condition, runtime):
            if name == 'provider_client.py':
                continue
            source = harness.REPO_ROOT / 'scripts' / name
            if name == 'run_responses_agent.py':
                shutil.copy2(source, scripts / 'baseline_responses_agent.py')
                source = ROOT / 'scripts/run_provider_agent.py'
            shutil.copy2(source, scripts / name)
        shutil.copy2(ROOT / 'scripts/provider_client.py', scripts / 'provider_client.py')
        if condition == 'cua':
            shutil.copytree(harness.REPO_ROOT / 'src/cua_swe_bench',
                            isolated_root / 'tools/src/cua_swe_bench',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
        return scripts

    harness._expected_tool_names = names
    # run_evaluation.py holds the credential and a single-route gateway; its lease
    # (agent config + token) leaves this process environment here and reaches only the
    # agent process environment, never a command line or record.
    lease_environment = {name: os.environ.pop(name) for name in AGENT_LEASE_ENV_NAMES
                         if name in os.environ}

    @contextmanager
    def public_lease(runtime, model_id):
        if model_id != config['model']:
            raise RuntimeError('provider configuration error: model differs from the public lease')
        yield dict(lease_environment)

    harness._require_provider_route = lambda runtime: 'responses'
    harness._provider_lease = public_lease
    harness._copy_isolated_tools = copy_tools
    harness._expected_tool_packet_digest.cache_clear()
    base_digest = harness._evaluation_harness_digest()
    effective = hashlib.sha256(json.dumps({'base': base_digest, 'extension': plan['extension']}, sort_keys=True).encode()).hexdigest()
    harness._evaluation_harness_digest = lambda: effective
    return {'base_harness_sha256': base_digest, 'effective_harness_sha256': effective}


def runner_args(plan):
    args = ['public-taskbundle', '--model', 'public-agent', '--attempts', '1',
            '--run-attempt', '1', '--shard-id', 'public-api', '--execution-host', 'local',
            '--max-workers', str(plan['max_workers']), '--python', sys.executable,
            '--output-root', str(Path(plan['output_root']) / 'runner')]
    if plan['domain'] in {'web', 'game'}:
        args.append('--evaluation-matrix')
    args.extend(['--cua-only', '--visual-cua'] if plan['condition'] == 'cua' else ['--code-only-only'])
    for row in plan['tasks']:
        args.extend(['--task-file', str(ROOT / row['task_file'])])
    return args


def main():
    plan = json.loads(Path(sys.argv[1]).read_text())
    harness = load_harness(plan['domain'])
    identity = install(harness, plan)
    (Path(plan['output_root']) / 'harness-extension.json').write_text(json.dumps(identity, indent=2) + '\n')
    sys.argv = runner_args(plan)
    return harness.main()


if __name__ == '__main__':
    raise SystemExit(main())
