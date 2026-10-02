"""Private network/PID namespace runtime supervisor. JSON-lines controller, never a solver tool.
The configured CUA-SWE adapter CLI owns browser/profile lifecycle and URL confinement.
No DOM/HTTP/a11y content from it is forwarded: only validated PNG pixels leave the bridge.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

config = json.loads(Path('/runtime.json').read_text())
services = []
logs = []

def stop():
    for p in reversed(services):
        try: os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        p.wait(timeout=5)
    services.clear()
    for f in logs: f.close()
    logs.clear()

def command(argv, request=None):
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = p.communicate(json.dumps(request).encode() if request is not None else None, timeout=150)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        raise RuntimeError('runtime/adapter command timeout')
    finally:
        try: os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    result = {'argv': argv, 'returncode': p.returncode, 'stdout': out.decode(errors='replace'), 'stderr': err.decode(errors='replace')}
    return result

try:
    for line in sys.stdin:
        req = json.loads(line)
        try:
            op = req['op']
            if op in ('start', 'sync'):
                stop()
                build = command(config['build']) if config.get('build') else {'returncode': 0}
                if build['returncode']:
                    # This is not an automatic model failure: final protected grading adjudicates.
                    answer = {'status': 'candidate_build_failed', 'build': build}
                else:
                    for i, argv in enumerate(config.get('services', [])):
                        f = open(f'/artifacts/service-{i}.log', 'ab'); logs.append(f)
                        services.append(subprocess.Popen(argv, stdout=f, stderr=f, start_new_session=True))
                    ready = command(config['ready'])
                    if ready['returncode'] != 0 or json.loads(ready['stdout']).get('ready') is not True:
                        raise RuntimeError('runtime readiness failed: ' + json.dumps(ready))
                    answer = {'status': 'ready', 'build': build, 'readiness': ready}
            elif op == 'act':
                r = command(config['action'], {'url': config['url'], 'action': req['action'], 'output_dir': '/artifacts', 'pixels_only': True})
                if r['returncode']:
                    raise RuntimeError('adapter failed: ' + json.dumps(r))
                answer = {'status': 'pixels', 'adapter': json.loads(r['stdout']), 'receipt': r}
            elif op == 'close':
                print(json.dumps({'status': 'closed'}), flush=True)
                break
            else: raise ValueError('unknown supervisor operation')
        except Exception as exc:
            answer = {'status': 'error', 'error': type(exc).__name__ + ': ' + str(exc)}
        print(json.dumps(answer), flush=True)
finally:
    stop()
