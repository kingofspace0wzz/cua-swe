from __future__ import annotations
import json
from pathlib import Path
import uuid
from .admission import append_ledger, classify
from .agent import Agent, responses_client
from .browser import PixelRuntime
from .core import Fault, Protocol, digest, evidence, harness_identity, matches, output_path, tree, write_json
from .grading import controls, grade
from .sandbox import Sandbox
from .workspace import extract, prepare, prepare_git_metadata


def run_attempt(task, root, condition, phase, slot, *, client_factory=responses_client, runtime_factory=PixelRuntime, synthetic=False, ledger=None, dispatch_approval=None):
    from .dispatch import validate_phase
    validate_phase(task, phase, slot)
    if not synthetic and client_factory is responses_client and not dispatch_approval:
        raise Fault('configuration', 'paid dispatch requires reviewed approval via CLI')
    if task.c['backend'].get('native') and runtime_factory is PixelRuntime:
        from .native_backend import NativeRuntime
        runtime_factory = NativeRuntime
    root = output_path(root); root.mkdir(parents=True, exist_ok=False)
    protocol = Protocol().record()
    if dispatch_approval: write_json(root / 'dispatch-approval.json', dispatch_approval)
    write_json(root / 'protocol.json', protocol); write_json(root / 'task.json', task.c)
    code = harness_identity(); write_json(root / 'harness.json', code)
    identity = {**task.identity, 'protocol_digest': digest(protocol), 'harness_digest': digest(code),
                'controls_digest': digest(task.c.get('controls', {}))}
    result = {'schema': 1, 'attempt_id': str(uuid.uuid4()), 'session_id': str(uuid.uuid4()),
              'condition': condition, 'phase': phase, 'slot': slot, 'synthetic': synthetic,
              'purpose': task.c.get('purpose', 'candidate'),
              'identity': identity, 'protocol': protocol, 'health': {}}
    health, faults, agent, grading, runtime = result['health'], [], {}, None, None
    try:
        task.validate_inputs(); health.update(instruction=True, source=True)
        baseline, reference, control_result = controls(task, root / 'controls')
        health.update(grader_controls=True, baseline=True)
        source = root / 'workspace'; prepared = prepare(task, source)
        if baseline != prepared: raise Fault('source', 'source changed since capture')
        write_json(root / 'baseline.json', baseline)
        git_record = prepare_git_metadata(source, root / 'git-metadata')
        write_json(root / 'git-baseline.json', git_record)
        sandbox = Sandbox(source, task.c['dependencies'],
                          read_only_files=[n for n in baseline if not matches(n, task.c['editable'])],
                          git_metadata=root / 'git-metadata',
                          writable_paths=[*task.c['editable'], *task.c.get('scratch', [])])
        sandbox.control(baseline, root / 'shell-before.json'); health['shell_before'] = True
        runtime = runtime_factory(task, root / 'runtime', baseline)
        health['runtime_before'] = True
        worker = Agent(task, baseline, sandbox, runtime, condition, root / 'agent', client_factory)
        agent = worker.run()
        patch = extract(task, baseline, source)
        write_json(root / 'patch.json', patch)
        sandbox.control(tree(source), root / 'shell-after.json'); health['shell_after'] = True
        runtime.close(); runtime = None
        grading = grade(task, baseline, patch, reference, root / 'grading')
    except Fault as exc:
        faults.append({'category': exc.category, 'message': str(exc)})
    except Exception as exc:
        faults.append({'category': 'harness', 'message': repr(exc)})
    finally:
        if runtime:
            try: runtime.close()
            except Exception as exc: faults.append({'category': 'runtime', 'message': repr(exc)})
    result['agent'] = agent; result['grade'] = grading
    result['classification'] = classify(agent, grading, health, faults)
    # Full append-only file inventory; solver source and runtime are not trusted evidence pointers.
    result['artifacts'] = [evidence(p) for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink() and
                           not any(x in ('workspace', 'source', 'git-metadata') for x in p.relative_to(root).parts)]
    ref = write_json(root / 'attempt.json', result)
    if ledger: append_ledger(ledger, ref)
    return result, ref
