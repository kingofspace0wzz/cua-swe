"""Host bridge for the sibling-sandbox native backend. No browser or model starts at import."""
from __future__ import annotations

import base64
import copy
import io
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import time
import uuid
from zoneinfo import ZoneInfo

from .browser import PixelActionError, action_valid
from .core import BROWSERS, PYTHON, Fault, digest, evidence, output_path, relative, sha, tree, write_json
from .workspace import apply, extract, prepare
from .native_worker import outer_argv, build_argv, audit_output

ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp/home', 'LANG': 'C.UTF-8',
       'TMPDIR': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1', 'PLAYWRIGHT_BROWSERS_PATH': BROWSERS}


def _require(ok, message):
    if not ok:
        raise Fault('configuration', message)


def _keys(obj, required, optional=()):
    _require(isinstance(obj, dict) and set(required) <= set(obj) <= set(required) | set(optional),
             f'native config keys: required={required}, optional={optional}')


def _ref(ref, directory=False):
    _keys(ref, ('path', 'sha256'))
    p = Path(ref['path'])
    _require(p.is_absolute() and p == p.resolve() and not p.is_symlink(), 'reference must be normalized absolute path')
    # Do not open credential-like input names, even in a nominally public tree.
    relative('/'.join(p.parts[1:]))
    actual = digest(tree(p, dependency=True)) if directory else sha(p)
    _require(actual == ref['sha256'], f'native input digest mismatch: {p}')
    return p


def validate_native(task):
    """Strict schema, independent of Task.id; all hashes are ordinary input hashes."""
    task.validate_inputs()
    c = copy.deepcopy(task.c['backend'].get('native'))
    _keys(c, ('schema', 'build', 'scene', 'setup', 'verifier', 'capture_required', 'assets'), ('fixture', 'static_api_fallbacks'))
    _require(c['schema'] == 1 and type(c['capture_required']) is bool, 'native schema/capture_required invalid')
    _require(task.c['backend'].get('browser_runtime') is True, 'native requires pinned browser_runtime')
    _require(not any(task.c['backend'].get(k) for k in ('runtime', 'adapter', 'protected')), 'do not combine native and legacy runtime/adapter/protected mounts')
    _require(task.c['backend'].get('capture') == 'native' if c['capture_required'] else not task.c['backend'].get('capture'),
             'capture must be "native" exactly when capture_required=true')
    _require(task.c['backend'].get('grade') == 'native', 'backend.grade must be "native" (requires coordinator dispatch)')
    for key in ('setup', 'verifier'):
        _ref(c[key])
    if 'fixture' in c:
        p = _ref(c['fixture'])
        _require(isinstance(json.loads(p.read_text()), (dict, list)), 'fixture must be JSON object/list')
    b = c['build']
    _keys(b, ('argv', 'out_dir', 'timeout_seconds', 'env', 'required_files'))
    _require(isinstance(b['argv'], list) and b['argv'] and all(isinstance(x, str) and x and '\0' not in x for x in b['argv']), 'build argv must be nonempty text array')
    relative(b['out_dir'])
    _require('/' not in b['out_dir'] and b['out_dir'] != 'TASK.md', 'build out_dir must be single directory name')
    _require(type(b['timeout_seconds']) is int and 1 <= b['timeout_seconds'] <= 150, 'build timeout must be 1..150')
    # Explicit public compile-time flags only, not a credential/environment passthrough.
    _require(isinstance(b['env'], dict) and set(b['env']) <= {'NODE_ENV', 'VITE_BASE'}, 'unsupported build environment key')
    _require(all(isinstance(v, str) and '\0' not in v for v in b['env'].values()), 'invalid build environment value')
    _require(b['env'].get('VITE_BASE', '/') == '/', 'native serves root VITE_BASE=/ only')
    _require(isinstance(b['required_files'], list) and 'index.html' in b['required_files'], 'required_files must include index.html')
    for name in b['required_files']:
        relative(name)
    fallbacks = c.get('static_api_fallbacks', {})
    _require(isinstance(fallbacks, dict) and all(k == '/api/sdcard' and v == 'sdcard/manifest.json' and v in b['required_files'] for k, v in fallbacks.items()), 'only source-backed sdcard manifest fallback is supported; require emitted file')
    s = c['scene']
    _keys(s, ('path', 'viewport', 'timezone', 'locale', 'device_scale_factor', 'state_mode', 'frame_paths', 'timeout_ms'))
    _require(isinstance(s['frame_paths'], list), 'frame_paths must be an explicit list')
    for path in [s['path'], *s['frame_paths']]:
        _require(isinstance(path, str) and path.startswith('/') and not path.startswith('//') and not any(x in path for x in ('\\', '\0', '?', '#', '%', '..')), 'scene/frame paths must be plain same-app paths')
    _keys(s['viewport'], ('width', 'height'))
    _require(all(type(v) is int and 1 <= v <= 4096 for v in s['viewport'].values()), 'invalid viewport')
    _require(s['state_mode'] in ('reset_to_scene', 'hooks'), 'explicit state_mode required')
    _require(type(s['timeout_ms']) is int and 1 <= s['timeout_ms'] <= 30000, 'scene timeout must be 1..30000ms')
    _require(type(s['device_scale_factor']) in (int, float) and 0.5 <= s['device_scale_factor'] <= 4, 'invalid device scale')
    _require(isinstance(s['locale'], str) and s['locale'], 'locale required')
    try:
        ZoneInfo(s['timezone'])
    except Exception as exc:
        raise Fault('configuration', 'unknown timezone') from exc
    _require(isinstance(c['assets'], list), 'assets must be explicit list, even if empty')
    destinations = [d['destination'] for d in task.c['dependencies']]
    prefixes = []
    for asset in c['assets']:
        _keys(asset, ('path', 'sha256', 'destination', 'serve_prefix'))
        _ref({k: asset[k] for k in ('path', 'sha256')}, directory=True)
        relative(asset['destination'])
        destinations.append(asset['destination'])
        prefix = asset['serve_prefix']
        _require(prefix is None or prefix == '/cdn/', 'only explicit /cdn/ serving is supported')
        if prefix:
            prefixes.append(prefix)
    _require(len(prefixes) == len(set(prefixes)), 'duplicate served asset prefix')
    for dest in destinations + [b['out_dir']]:
        _require(not any(n == dest or n.startswith(dest + '/') or dest.startswith(n + '/') for n in task.c['public_files']), 'build/asset/dependency mount overlaps source')
        _require(dest != 'TASK.md', 'mount overlaps instruction')
        _require(not any(dest == e.rstrip('/') or dest.startswith(e.rstrip('/') + '/') or e.rstrip('/').startswith(dest + '/') for e in task.c['editable']), 'mount overlaps editable boundary')
    all_dest = destinations + [b['out_dir']]
    _require(not any(a == b or a.startswith(b + '/') or b.startswith(a + '/') for i, a in enumerate(all_dest) for b in all_dest[i + 1:]), 'overlapping build mounts')
    return c


def stage_patch(task, baseline, patch, workspace, stage, previous):
    """Use core preimages and a pristine stage; preserve the RO bind's root inode."""
    if any(Path(workspace).joinpath(*Path(name).parts[:i]).is_symlink() for name in previous | {r['path'] for r in patch['changes']} for i in range(1, len(Path(name).parts) + 1)):
        raise Fault('scope', 'native workspace path became a symlink')
    if prepare(task, stage) != baseline:
        raise Fault('source', 'native baseline changed')
    apply(task, baseline, patch, stage)
    current = {row['path'] for row in patch['changes']}
    for name in sorted(previous | current):
        src, dst = Path(stage) / name, Path(workspace) / name
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif dst.exists():
            dst.unlink()
    return current


def freeze_png(host, destination):
    from PIL import Image
    raw = Path(host).read_bytes()
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'PNG' or not (1 <= image.width <= 10000 and 1 <= image.height <= 10000):
            raise Fault('image_delivery', 'invalid native screenshot format/dimensions')
        image.load()  # Actually decode pixel data, not just PNG headers.
    with Path(destination).open('xb') as f:
        f.write(raw)
    Path(destination).chmod(0o444)
    return {'evidence': evidence(destination), 'data_url': 'data:image/png;base64,' + base64.b64encode(raw).decode()}


def _reap(process):
    # bwrap owns a PID namespace: its exit tears down even detached descendants.
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=8)


class SiblingBuilds:
    """Host coordinator only. Publish nothing until namespace teardown + audit.

    Source snapshots and unfinished outputs are never mounted in the supervisor.
    Publication is one atomic directory rename into its read-only generation root.
    """
    def __init__(self, root, task, c):
        self.root, self.task, self.c = Path(root), task, c
        self.index = 0
        for name in ('build-work', 'build-receipts', 'generations'):
            (self.root / name).mkdir()

    def run(self, source):
        self.index += 1
        number = f'{self.index:08}'
        work = self.root / 'build-work' / number
        work.mkdir()
        scratch, output = work / 'source', work / 'output'
        logs = [self.root / 'build-receipts' / f'{number}.{ext}' for ext in ('stdout', 'stderr')]
        process = None
        start = time.monotonic()
        receipt = {'generation': number, 'stage': 'build', 'infrastructure': False}
        try:
            source_manifest = tree(source)  # Reject credential-like paths/links before copy.
            shutil.copytree(source, scratch)
            if tree(scratch) != source_manifest:
                raise Fault('source', 'public build snapshot mismatch')
            output.mkdir()
            config = {'native': self.c, 'dependencies': self.task.c['dependencies']}
            argv = build_argv(config, scratch, output)
            receipt.update(argv=argv, source_manifest=source_manifest, timed_out=False)
            with logs[0].open('xb') as out, logs[1].open('xb') as err:
                process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                           env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, start_new_session=True)
                try:
                    process.wait(timeout=self.c['build']['timeout_seconds'])
                except subprocess.TimeoutExpired:
                    receipt['timed_out'] = True
                finally:
                    _reap(process)
            receipt.update(returncode=process.returncode, cleanup_complete=True,
                           logs=[evidence(p) for p in logs],
                           stdout_tail=logs[0].read_bytes()[-16000:].decode(errors='replace'),
                           stderr_tail=logs[1].read_bytes()[-16000:].decode(errors='replace'))
            if receipt['timed_out'] or process.returncode < 0 or process.returncode in (125, 126, 127) or 'bwrap:' in receipt['stderr_tail']:
                receipt['infrastructure'] = True
                raise Fault('build', 'build timeout/sandbox/tool failure; attribution unknown')
            if process.returncode:
                return {'diagnostic': receipt}
            try:
                manifest = audit_output(output, self.c['build']['required_files'])
            except ValueError as exc:
                receipt.update(stage='build_output', error=repr(exc))
                return {'diagnostic': receipt}
            # Candidate wrote only output, never this trusted manifest/tree. Copy
            # after complete cleanup, audit again and freeze before atomic publish.
            sealed = work / 'sealed'
            sealed.mkdir()
            shutil.copytree(output, sealed / 'app')
            if audit_output(sealed / 'app', self.c['build']['required_files']) != manifest:
                raise Fault('build', 'output changed after process cleanup')
            write_json(sealed / 'manifest.json', {'schema': 1, 'generation': number,
                       'task_digest': self.task.id, 'source_manifest': source_manifest, 'output': manifest})
            for base, dirs, files in os.walk(sealed, topdown=False):
                for name in files:
                    (Path(base) / name).chmod(0o444)
                # Keep the container movable; its children/manifest are frozen.
                # The supervisor has a RO bind; only host can rename generations.
                Path(base).chmod(0o755 if Path(base) == sealed else 0o555)
            manifest_sha = sha(sealed / 'manifest.json')
            sealed.rename(self.root / 'generations' / number)
            receipt.update(published=True, manifest_sha256=manifest_sha)
            return {'generation': number, 'manifest_sha256': manifest_sha}
        except BaseException as exc:
            receipt.update(infrastructure=True, error=repr(exc))
            raise
        finally:
            try:
                if process is not None:
                    _reap(process)
                    receipt.update(returncode=process.returncode, cleanup_complete=True)
                receipt['logs'] = [evidence(p) for p in logs if p.exists()]
                receipt['seconds'] = time.monotonic() - start
                write_json(self.root / 'build-receipts' / f'{number}.json', receipt)
            finally:
                # Only private per-build copies; source and published generations survive.
                work.chmod(0o700)
                for base, dirs, files in os.walk(work, topdown=True, followlinks=False):
                    for name in dirs:
                        child = Path(base) / name
                        if not child.is_symlink():
                            child.chmod(0o700)
                shutil.rmtree(work)


class _Session:
    def __init__(self, task, root, source, c, operation, reference=None):
        self.root, self.task, self.config = root, task, c
        self.source = source
        self.closed = False
        self.p = self.log = None
        self.index = 0
        self.buffer = b''
        try:
            for name in ('artifacts', 'inputs'):
                (root / name).mkdir()
            self.artifacts = root / 'artifacts'
            self.builds = SiblingBuilds(root, task, c)
            # Freeze modules/config, do not mount live constructor hook source paths.
            for name in ('setup', 'verifier', 'fixture'):
                if name in c and (name != 'verifier' or operation == 'grade'):
                    src = _ref(c[name])
                    dst = root / 'inputs' / (name + ('.json' if name == 'fixture' else '.py'))
                    shutil.copyfile(src, dst)
                    _require(sha(dst) == c[name]['sha256'], 'hook changed during snapshot')
                    dst.chmod(0o444)
            worker = root / 'inputs' / 'worker.py'
            shutil.copyfile(Path(__file__).with_name('native_worker.py'), worker)
            worker.chmod(0o444)
            if reference is not None:
                ref = Path(reference).resolve(strict=True)
                # Copy only trusted reference receipts/images, never build scratch
                # or other untrusted byproducts into the verifier reference mount.
                tree(ref / 'artifacts')
                (root / 'reference').mkdir()
                if (ref / 'baseline.json').is_symlink():
                    raise Fault('baseline', 'linked baseline JSON rejected')
                shutil.copyfile(ref / 'baseline.json', root / 'reference/baseline.json')
                shutil.copytree(ref / 'artifacts', root / 'reference/artifacts')
                raw = json.loads((root / 'reference' / 'baseline.json').read_text())
                _require(raw.get('task_digest') == task.id and raw.get('execution') == 'complete' and raw.get('errors') == [] and raw.get('state'), 'reference missing/invalid or from another task')
                if c['capture_required']:
                    _require(raw.get('capture_kind') == 'native_hook_pre_edit', 'real pre-edit capture required')
                reference = root / 'reference'
            elif operation == 'grade' and c['capture_required']:
                raise Fault('baseline', 'native grade requires pre-edit captured reference')
            supervisor_c = copy.deepcopy(c)
            supervisor_c['build'] = {'required_files': c['build']['required_files']}
            config = {'native': supervisor_c, 'operation': operation, 'task_digest': task.id,
                      'expected_assertions': task.c['expected_assertions'],
                      'source_manifest': tree(source), 'has_reference': reference is not None,
                      'rpc_timeout': task.c['backend'].get('timeout_seconds', 170)}
            write_json(root / 'config.json', config)
            (root / 'config.json').chmod(0o444)
            self.argv = outer_argv(root, None, [], c['assets'], BROWSERS, PYTHON, reference, operation)
            write_json(root / 'launch.json', {'argv': self.argv, 'environment': ENV, 'worker_sha256': sha(worker)})
        except BaseException:
            self.close()
            raise

    def _launch(self):
        if self.p is None:
            self.log = (self.root / 'supervisor.stderr').open('xb')
            self.p = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                      env=ENV, start_new_session=True)

    def request(self, req):
        try:
            if req['op'] in ('start', 'sync', 'capture', 'grade'):
                if req['op'] == 'sync':
                    prepared = self._rpc({'op': 'prepare_sync'})
                    if prepared.get('status') != 'build_prepared':
                        raise Fault('runtime', 'state was not saved before sibling build')
                update = self.builds.run(self.source)
                self._launch()  # Even initial browser startup follows completed build.
                return self._rpc({**req, **update})
            return self._rpc(req)
        except BaseException:
            self.close()
            raise

    def _rpc(self, req):
        self.index += 1
        index = self.index
        start = time.monotonic()
        try:
            write_json(self.root / f'{index:04}-request.json', req)
            self.p.stdin.write(json.dumps(req).encode() + b'\n')
            self.p.stdin.flush()
            deadline = start + self.task.c['backend'].get('timeout_seconds', 170) + 10
            while b'\n' not in self.buffer:
                left = deadline - time.monotonic()
                if left <= 0 or not select.select([self.p.stdout], [], [], max(0, left))[0]:
                    raise TimeoutError('native supervisor RPC timeout; attribution unknown')
                block = os.read(self.p.stdout.fileno(), 65536)
                if not block:
                    raise RuntimeError(f'native supervisor EOF (exit={self.p.poll()}); see supervisor.stderr')
                self.buffer += block
                if len(self.buffer) > 16 * 1024 * 1024:
                    raise RuntimeError('oversized native envelope')
            line, self.buffer = self.buffer.split(b'\n', 1)
            result = json.loads(line)
            if not isinstance(result, dict):
                raise ValueError('invalid native envelope')
            write_json(self.root / f'{index:04}-response.json', {'seconds': time.monotonic() - start, 'response': result})
            if result.get('status') == 'error':
                raise Fault('runtime', result.get('error', 'native supervisor error'))
            return result
        except BaseException as exc:
            try:
                write_json(self.root / f'{index:04}-failure.json', {'seconds': time.monotonic() - start, 'error': repr(exc)})
            finally:
                self.close()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise Fault('runtime', 'native bridge failure; inspect private request/failure receipts') from exc

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.p:
            try:
                if self.p.stdin:
                    self.p.stdin.close()
                self.p.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.p.wait(timeout=8)
            finally:
                # Also cover an abnormal bwrap exit with surviving group members.
                try:
                    os.killpg(self.p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if self.p.stdout:
                    self.p.stdout.close()
        if self.log:
            self.log.close()


class NativeRuntime:
    def __init__(self, task, root, baseline):
        self.session = None
        self.available = False
        self.task, self.baseline, self.previous = task, baseline, set()
        self.root = output_path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        try:
            c = validate_native(task)
            self.workspace = self.root / 'source'
            if prepare(task, self.workspace) != baseline:
                raise Fault('source', 'native runtime baseline mismatch')
            self.session = _Session(task, self.root, self.workspace, c, 'runtime')
            result = self.session.request({'op': 'start'})
            if result.get('status') != 'ready':
                raise Fault('runtime', 'baseline native readiness failed; private receipts contain diagnostics')
            self.available = True
            self.control_image = self.act({'type': 'screenshot'})
        except BaseException:
            self.close()
            raise

    def sync(self, patch):
        if not self.session or self.session.closed:
            raise Fault('runtime', 'native runtime closed')
        stage = self.root / ('stage-' + uuid.uuid4().hex)
        try:
            self.previous = stage_patch(self.task, self.baseline, patch, self.workspace, stage, self.previous)
            result = self.session.request({'op': 'sync'})
            self.available = result.get('status') == 'ready'
        except BaseException:
            self.close()
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        # Only status is appropriate for solver shell feedback. Receipts stay private.
        return {'status': result['status']}

    def act(self, action):
        if not action_valid(action):
            raise PixelActionError('invalid screenshot action')
        if not self.available:
            raise ValueError('native app unavailable; repair source; coordinator retains private diagnostics')
        kind = action['type']
        if kind in ('click', 'long_press', 'drag'):
            viewport = self.session.config['scene']['viewport']
            points = [('x', 'width'), ('y', 'height')] if kind != 'drag' else [
                ('from_x', 'width'), ('from_y', 'height'),
                ('to_x', 'width'), ('to_y', 'height'),
            ]
            if any(not 0 <= action[key] < viewport[axis] for key, axis in points):
                raise PixelActionError(
                    f"pointer outside viewport; x must be 0..{viewport['width'] - 1}, "
                    f"y must be 0..{viewport['height'] - 1}")
        try:
            result = self.session.request({'op': 'act', 'action': action})
            name = result.get('frame', '')
            if result.get('status') != 'pixels' or not isinstance(name, str) or Path(name).name != name or not name.endswith('.png'):
                raise Fault('image_delivery', 'invalid native frame receipt')
            source = self.session.artifacts / name
            if source.is_symlink() or not source.is_file():
                raise Fault('image_delivery', 'native frame missing/linked')
            return freeze_png(source, self.root / ('frame-' + uuid.uuid4().hex + '.png'))
        except BaseException as exc:
            self.close()
            if isinstance(exc, (KeyboardInterrupt, SystemExit, Fault)):
                raise
            raise Fault('image_delivery', 'native PNG transport/decode failed; private receipts retained') from exc

    def close(self):
        self.available = False
        if self.session:
            self.session.close()


def native_operation(task, workspace, root, operation, baseline=None):
    """Clean capture/grade. Returns process-compatible metadata; never interprets a score.

    `baseline` is a captured reference directory, NOT the source manifest. The
    supplied workspace is independently copied using existing patch/preimage code.
    Result is also placed at root/result.json or root/baseline.json for grading.py.
    """
    if operation not in ('capture', 'grade'):
        raise Fault('configuration', 'native operation must be capture or grade')
    root = output_path(root)
    root.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    session = None
    result_path = root / ('baseline.json' if operation == 'capture' else 'result.json')
    try:
        c = validate_native(task)
        manifest = prepare(task, root / 'source')
        patch = extract(task, manifest, workspace)
        if operation == 'capture' and patch['changes']:
            raise Fault('baseline', 'capture must precede candidate edits')
        apply(task, manifest, patch, root / 'source')
        session = _Session(task, root, root / 'source', c, operation, baseline)
        response = session.request({'op': operation})
        if response.get('status') != 'completed':
            raise Fault('grader', 'native operation did not complete')
        raw = json.loads((session.artifacts / result_path.name).read_text())
        write_json(result_path, raw)
        healthy = raw.get('execution') in ('complete', 'candidate_error') and raw.get('errors') == []
        timed_out = any(isinstance(e, dict) and e.get('type') in ('TimeoutError', 'TimeoutExpired') for e in raw.get('errors', []))
        result = {'returncode': 0 if healthy else 2, 'timed_out': timed_out, 'stdout': '', 'stderr': '' if healthy else json.dumps(raw),
                  'seconds': time.monotonic() - start, 'result': evidence(result_path)}
    except Exception as exc:
        if not result_path.exists():
            write_json(result_path, {'execution': 'exception', 'errors': [repr(exc)]})
        result = {'returncode': 2, 'timed_out': isinstance(exc, TimeoutError), 'stdout': '',
                  'stderr': repr(exc), 'seconds': time.monotonic() - start, 'result': evidence(result_path)}
    finally:
        if session:
            session.close()
    write_json(root / 'process.json', result)
    return result
