#!/usr/bin/env python3
"""Canonical protected Mobile evaluation. One attempt per selected frozen cell."""
from __future__ import annotations
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def worker(packet_path, audit=False):
    from cua_swe_bench.mobile_evaluation.core import Task, digest, evidence, harness_identity
    from cua_swe_bench.mobile_evaluation import final_api, final_cli
    from cua_swe_bench.mobile_evaluation.settings import validate_runtime
    packet = json.loads(Path(packet_path).read_text())
    route = packet['route']
    validate_runtime(route)
    cli = route == 'codex-sol'
    adapter = final_cli if cli else final_api
    protocol = adapter.protocol_class(route)().record()
    harness = digest(harness_identity())
    root = Path(packet['root'])
    if audit:
        from cua_swe_bench.mobile_evaluation.final_attempt_audit import audit_attempt
        expected = json.loads((root / 'expected.json').read_text())
        if expected != {'protocol': protocol, 'harness': harness, 'task': evidence(packet['task'])}:
            raise ValueError('pre-dispatch expectations changed')
        review = audit_attempt(root / 'attempt/attempt.json', root / 'audit',
                               expected['task'], protocol, harness)
        return 0 if review['passed'] else 2
    write(root / 'expected.json', {'protocol': protocol, 'harness': harness, 'task': evidence(packet['task'])})
    task = Task.load(packet['task'])
    task.validate_inputs()
    run = final_cli.run_cli_attempt if cli else final_api.run_api_attempt
    result, ref = run(route, task, root / 'attempt', packet['condition'], 'evaluation', 1,
                      dispatch_approval={'approved': True, 'source': 'explicit canonical run command',
                                         'task_digest': task.id, 'protocol_digest': digest(protocol),
                                         'harness_digest': harness})
    return 0 if result['classification']['scorable'] else 3


def launch(packet, config, python, audit=False):
    argv = [python, str(Path(__file__).resolve()), '--audit-worker' if audit else '--worker', str(packet)]
    # Host-only config and provider keys go solely to the evaluator process. Sandbox,
    # build and CLI namespaces receive explicit clean environments without them.
    env = dict(os.environ)
    env['CUA_MOBILE_CONFIG'] = str(config)
    with packet.with_suffix('.audit.log' if audit else '.log').open('xb') as log:
        return subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=False).returncode


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    p.add_argument('--plan', action='store_true')
    p.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--audit-worker', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--model')
    p.add_argument('--condition', choices=['code-only', 'cua'])
    p.add_argument('--scope', choices=['gate', 'full'], default='full')
    p.add_argument('--output-root', type=Path)
    p.add_argument('--runtime-config', type=Path)
    p.add_argument('--max-workers', type=int, default=1)
    args = p.parse_args(argv)
    if args.runtime_config:
        os.environ['CUA_MOBILE_CONFIG'] = str(args.runtime_config.resolve())
    from cua_swe_bench.mobile_evaluation.release import MODELS, DEFERRED, MANIFEST, load, materialize, validate_release
    if args.worker or args.audit_worker:
        validate_release()
        return worker(args.worker or args.audit_worker, bool(args.audit_worker))
    status = validate_release()
    if args.check:
        print(json.dumps(status, indent=2)); return 0
    if args.model in DEFERRED:
        p.error('Opus 5 Mobile conditions remain user-deferred')
    if args.model not in MODELS or args.condition is None or args.output_root is None:
        p.error('--model, --condition, and --output-root are required')
    if args.model == 'codex-gpt56-sol' and args.condition != 'cua':
        p.error('Codex is evaluated with its native CLI in CUA only')
    if not 1 <= args.max_workers <= 4:
        p.error('--max-workers must be between one and four')
    rows = load(REPO / MANIFEST)['tasks'][:10 if args.scope == 'gate' else 20]
    if args.plan:
        print(json.dumps({'model': args.model, 'condition': args.condition,
                          'task_ids': [r['task_id'] for r in rows], 'attempts_per_cell': 1,
                          'responses': 60, 'active_seconds': 2700, 'output_tokens': 16384,
                          'automatic_retries': 0, 'audit': 'after batch'}, indent=2))
        return 0
    if not args.runtime_config:
        p.error('run requires a private --runtime-config')
    from cua_swe_bench.mobile_evaluation.settings import ROOT, PYTHON, validate_runtime
    validate_runtime(MODELS[args.model])
    output = args.output_root.resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        p.error('output must be a new campaign directory inside configured output_root')
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'selection.json', {'model': args.model, 'condition': args.condition,
                                      'tasks': rows, 'attempts_per_cell': 1})
    packets = []
    for row in rows:
        root = output / f"t{row['ordinal']:02d}"
        root.mkdir()
        task = materialize(row, root / 'inputs')
        packet = root / 'claim.json'
        write(packet, {'root': str(root), 'route': MODELS[args.model], 'model': args.model,
                       'condition': args.condition, 'task': str(task), 'task_id': row['task_id']})
        packets.append(packet)
    done, held, pending = [], False, iter(packets)
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        running = {}
        def fill():
            while not held and len(running) < args.max_workers:
                packet = next(pending, None)
                if packet is None: break
                running[pool.submit(launch, packet, args.runtime_config.resolve(), PYTHON)] = packet
        fill()
        while running:
            completed, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in completed:
                packet = running.pop(future)
                code = future.result()
                done.append(packet)
                held = held or code != 0
            fill()
    # Review the completed batch; do not block between successful dispatches.
    results = []
    for packet in packets:
        claim = load(packet)
        attempt = packet.parent / 'attempt/attempt.json'
        row = {'task_id': claim['task_id'], 'model': args.model, 'condition': args.condition,
               'executed': packet in done, 'scorable': False, 'success': False,
               'disposition': 'held_unexecuted' if packet not in done else 'infrastructure_excluded'}
        if attempt.exists():
            code = launch(packet, args.runtime_config.resolve(), PYTHON, audit=True)
            if code == 0:
                review = load(packet.parent / 'audit/review.json')
                row.update(scorable=review['scorable'], success=review['counted_success'],
                           disposition=review['classification'])
            else:
                row['disposition'] = 'audit_excluded'
        results.append(row)
    write(output / 'summary.json', {'schema_version': 1, 'held': held, 'rows': results,
                                    'failure_attribution': 'Manual attribution follows custody audit; exclusions earn no failure credit.'})
    print(json.dumps({'executed': len(done), 'held': held, 'scorable': sum(r['scorable'] for r in results)}))
    return 3 if held or any(r['executed'] and not r['scorable'] for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
