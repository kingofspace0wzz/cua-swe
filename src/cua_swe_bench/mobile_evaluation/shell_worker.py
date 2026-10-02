"""Isolated trusted envelope. Not an agent; contains no private paths or secrets."""
import json
import os
import signal
import subprocess
import sys
import time

request = json.load(sys.stdin)
start = time.monotonic()
p = subprocess.Popen(['/bin/sh', '-c', request['command']], cwd='/workspace',
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                     close_fds=True)
timed_out = False
try:
    payload = request.get('stdin')
    stdout, stderr = p.communicate(input=payload.encode() if payload is not None else None,
                                  timeout=request['timeout'])
except subprocess.TimeoutExpired:
    timed_out = True
    os.killpg(p.pid, signal.SIGKILL)
    stdout, stderr = p.communicate()
finally:
    # Also reap shell-background children; the PID namespace dies with this worker.
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
print(json.dumps({'schema': 1, 'nonce': request['nonce'], 'started': True, 'completed': True,
                  'returncode': p.returncode, 'timed_out': timed_out,
                  'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace'),
                  'seconds': time.monotonic() - start,
                  'net_ns': os.readlink('/proc/self/ns/net'), 'pid_ns': os.readlink('/proc/self/ns/pid')}))
