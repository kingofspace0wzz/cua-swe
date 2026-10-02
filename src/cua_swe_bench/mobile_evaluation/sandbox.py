from __future__ import annotations
import json
import os
import secrets
import signal
import subprocess
import time
from pathlib import Path
from .core import Fault, PYTHON, canonical, output_path, tree, write_json

from .settings import BROWSERS, VENV, BWRAP

SAFE_ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp/home', 'LANG': 'C.UTF-8',
            'TMPDIR': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1',
            'PLAYWRIGHT_BROWSERS_PATH': BROWSERS}


def process(argv, *, data=None, timeout=175, cwd=None):
    """Bounded child ownership; never inherit host credentials or detach processes."""
    start = time.monotonic()
    p = subprocess.Popen(argv, cwd=cwd, env=SAFE_ENV, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        out, err = p.communicate(data, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
    finally:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return {'argv': argv, 'returncode': p.returncode, 'stdout': out.decode(errors='replace'),
            'stderr': err.decode(errors='replace'), 'timed_out': timed_out,
            'seconds': time.monotonic() - start}


class Sandbox:
    def __init__(self, workspace, dependencies=(), bwrap=BWRAP, read_only_files=(), git_metadata=None,
                 writable_paths=None):
        self.workspace = Path(workspace).resolve()
        self.dependencies = dependencies
        self.bwrap = bwrap
        self.read_only_files = set(read_only_files) | ({'TASK.md'} if (self.workspace / 'TASK.md').is_file() else set())
        self.git_metadata = Path(git_metadata).resolve() if git_metadata else None
        # Complete permitted paths, including not-yet-created files/directories.
        # Without this information, keep the original per-file mount behavior.
        self.writable_paths = None if writable_paths is None else list(writable_paths)

    def readonly_mounts(self, manifest):
        from .core import relative
        for name in sorted(self.read_only_files):
            relative(name)
            source = self.workspace / name
            if not source.is_file() or source.is_symlink():
                raise Fault('source', f'noneditable public source absent/changed: {name}')
        if self.writable_paths is None:
            return sorted(self.read_only_files)
        writable = [str(relative(n.rstrip('/'))) for n in self.writable_paths]
        directories = {str(p) for n in self.read_only_files for p in Path(n).parents if str(p) != '.'}
        grouped = []
        for directory in sorted(directories, key=lambda n: (n.count('/'), n)):
            if any(directory == g or directory.startswith(g + '/') for g in grouped):
                continue
            if any(directory == w or directory.startswith(w + '/') or w.startswith(directory + '/')
                   for w in writable):
                continue
            descendants = {n for n in manifest if n.startswith(directory + '/')}
            if descendants and descendants <= self.read_only_files:
                grouped.append(directory)
        return sorted(grouped + [n for n in self.read_only_files
                                 if not any(n.startswith(g + '/') for g in grouped)])

    def argv(self, command, mounts=(), readonly=False):
        # Audit before mounting so a candidate cannot replace a dependency mountpoint with a symlink.
        manifest = tree(self.workspace)
        argv = [self.bwrap, '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
                '--ro-bind', '/usr', '/usr']
        for name in ('bin', 'sbin', 'lib', 'lib64'):
            if (Path('/usr') / name).exists():
                argv += ['--symlink', 'usr/' + name, '/' + name]
        argv += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/tmp/home',
                 '--dir', '/etc', '--ro-bind', VENV, VENV,
                 '--ro-bind' if readonly else '--bind', str(self.workspace), '/workspace']
        # Coalesce wholly noneditable subtrees to avoid bwrap's argument-count
        # limit without blocking a permitted new file beneath an editable path.
        for name in self.readonly_mounts(manifest):
            argv += ['--ro-bind', str(self.workspace / name), '/workspace/' + name]
        for dep in self.dependencies:
            dest = self.workspace / dep['destination']
            if not dest.is_dir() or dest.is_symlink():
                raise Fault('scope', 'dependency mountpoint changed')
            argv += ['--ro-bind', dep['path'], '/workspace/' + dep['destination']]
        if self.git_metadata:
            target = self.workspace / '.git'
            if not target.is_dir() or target.is_symlink() or any(target.iterdir()):
                raise Fault('scope', 'Git metadata mountpoint changed')
            argv += ['--bind', str(self.git_metadata), '/workspace/.git']
        for source, dest, writable in mounts:
            argv += ['--bind' if writable else '--ro-bind', str(source), dest]
        for key, value in SAFE_ENV.items():
            argv += ['--setenv', key, value]
        return argv + ['--chdir', '/workspace', '--'] + command

    def shell(self, command, timeout=170, record=None, *, stdin=None):
        if not isinstance(command, str) or not isinstance(timeout, int) or not 1 <= timeout <= 170:
            raise ValueError('command must be text; timeout must be 1..170 seconds')
        if stdin is not None and not isinstance(stdin, str):
            raise ValueError('stdin must be text or None')
        nonce = secrets.token_hex(24)
        argv = self.argv([PYTHON, '-I', '/runner.py'], [(Path(__file__).with_name('shell_worker.py'), '/runner.py', False)])
        outer = process(argv, data=canonical({'command': command, 'timeout': timeout, 'nonce': nonce, 'stdin': stdin}), timeout=timeout + 4)
        if record:
            write_json(record, outer)
        try:
            result = json.loads(outer['stdout'])
            if outer['returncode'] != 0 or outer['timed_out'] or result['nonce'] != nonce or result['completed'] is not True or result['started'] is not True:
                raise ValueError('envelope/exit mismatch')
            if result['net_ns'] == os.readlink('/proc/self/ns/net') or result['pid_ns'] == os.readlink('/proc/self/ns/pid'):
                raise ValueError('namespace isolation absent')
        except (ValueError, KeyError, TypeError) as exc:
            details = {k: outer[k] for k in ('returncode', 'timed_out', 'seconds')}
            details.update(stderr=outer['stderr'][:2000], stdout=outer['stdout'][:1000],
                           argument_count=len(outer['argv']), full_record=str(record) if record else None)
            raise Fault('sandbox', f'no authenticated shell completion: {exc}; outer={details}') from exc
        return result

    def control(self, baseline, record):
        expected = {p: x['sha256'] for p, x in baseline.items()}
        # Read and hash every public source, prove edit persistence and namespace separation.
        script = """import hashlib,json,pathlib,os,socket
expected = EXPECTED
actual = {n:hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest() for n in expected}
assert actual == expected
assert all(not pathlib.Path(p).exists() for p in ['/efs','/home','/root','/protected','/artifacts','/run','/var/run'])
assert not any(k.startswith(('OPENAI_', 'ANTHROPIC_', 'CUA_')) or k.endswith(('_KEY', '_KEY_ID', '_TOKEN', '_SECRET')) for k in os.environ)
assert not pathlib.Path('/etc/environment').exists()
pathlib.Path('.harness-control').write_text('persisted')
try:
 s=socket.create_connection(('169.254.169.254',80),timeout=.2)
 raise AssertionError('metadata network accessible')
except OSError: pass
print(json.dumps({'source_read':actual,'protected_absent':True,'write':True,'network_denied':True}))
""".replace('EXPECTED', repr(expected))
        # A full application manifest exceeds Linux's per-argument size limit.
        # Transport the trusted script over stdin while retaining every source hash.
        r = self.shell(PYTHON + ' -I -', record=record, stdin=script)
        scratch = self.workspace / '.harness-control'
        if r['returncode'] != 0 or r['timed_out'] or not scratch.is_file() or scratch.read_text() != 'persisted':
            raise Fault('sandbox', f'shell health control failed: {r}')
        scratch.unlink()
        try:
            health = json.loads(r['stdout'])
            if health['source_read'] != expected or health['protected_absent'] is not True or health['network_denied'] is not True:
                raise ValueError('bad control assertions')
        except (ValueError, KeyError) as exc:
            raise Fault('sandbox', 'missing health assertions') from exc
        return health
