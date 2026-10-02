from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import select
import signal
import subprocess
from urllib.parse import urlparse
from .core import BROWSERS, Fault, PYTHON, digest, evidence, output_path, sha, write_json
from .sandbox import SAFE_ENV, Sandbox
from .workspace import prepare


class PixelActionError(ValueError):
    """Invalid public action input that must not terminate a pixel session."""


def action_valid(action):
    if not isinstance(action, dict): return False
    kind = action.get('type')
    fields = {'screenshot': {'type'}, 'reload': {'type'}, 'click': {'type', 'x', 'y'},
              'long_press': {'type', 'x', 'y', 'duration_ms'},
              'drag': {'type', 'from_x', 'from_y', 'to_x', 'to_y', 'duration_ms'}, 'type': {'type', 'text'},
              'press': {'type', 'key'}, 'scroll': {'type', 'dx', 'dy'}}
    if kind not in fields or set(action) != fields[kind]: return False
    if kind == 'click': return all(type(action[k]) is int and 0 <= action[k] < 10000 for k in ('x', 'y'))
    if kind == 'long_press':
        return (all(type(action[k]) is int and 0 <= action[k] < 10000 for k in ('x', 'y'))
                and type(action['duration_ms']) is int and 400 <= action['duration_ms'] <= 2000)
    if kind == 'drag':
        return (all(type(action[k]) is int and 0 <= action[k] < 10000
                    for k in ('from_x', 'from_y', 'to_x', 'to_y'))
                and type(action['duration_ms']) is int and 100 <= action['duration_ms'] <= 2000)
    if kind == 'scroll': return all(type(action[k]) is int and abs(action[k]) <= 5000 for k in ('dx', 'dy'))
    if kind == 'type': return isinstance(action['text'], str) and len(action['text']) <= 10000
    if kind == 'press': return action['key'] in ('Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space')
    return True


class PixelRuntime:
    def __init__(self, task, root, baseline):
        self.task, self.baseline = task, baseline
        self.root = output_path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.workspace = self.root / 'source'
        if prepare(task, self.workspace) != baseline:
            raise Fault('source', 'runtime source baseline mismatch')
        c = task.c['backend'].get('runtime')
        if not c or c.get('interface') != 'cua-swe-adapter-pixels-v1' or not task.c['backend'].get('adapter'):
            raise Fault('configuration', 'pinned CUA-SWE pixel adapter runtime required')
        u = urlparse(c['url'])
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost') or u.username or u.password:
            raise Fault('configuration', 'approved runtime must be private loopback HTTP URL')
        self.config = c
        self.available = True
        self.artifacts = self.root / 'artifacts'; self.artifacts.mkdir()
        config_path = self.root / 'runtime.json'; write_json(config_path, c)
        mounts = [(Path(__file__).with_name('runtime_worker.py'), '/runtime_worker.py', False),
                  (config_path, '/runtime.json', False), (self.artifacts, '/artifacts', True),
                  (task.c['backend']['adapter']['path'], '/adapter', False)]
        if task.c['backend'].get('browser_runtime'):
            mounts.append((BROWSERS, BROWSERS, False))
        self.log = (self.root / 'supervisor.stderr').open('wb')
        self.p = subprocess.Popen(Sandbox(self.workspace, task.c['dependencies']).argv([PYTHON, '-I', '/runtime_worker.py'], mounts),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, env=SAFE_ENV, start_new_session=True)
        self.index = 0
        self.previous = set()
        self.closed = False
        try:
            r = self.request({'op': 'start'})
            if r['status'] != 'ready': raise Fault('runtime', 'broken runtime failed health control')
            # Prove healthy screenshot availability for BOTH conditions; never deliver this control image to solver.
            self.control_image = self.act({'type': 'screenshot'})
        except BaseException:
            self.close(); raise

    def request(self, req):
        self.index += 1
        write_json(self.root / f'{self.index:04}-request.json', req)
        try:
            self.p.stdin.write(json.dumps(req).encode() + b'\n'); self.p.stdin.flush()
            if not select.select([self.p.stdout], [], [], 170)[0]: raise TimeoutError('runtime RPC timeout')
            line = self.p.stdout.readline()
            result = json.loads(line)
        except (OSError, ValueError, TimeoutError) as exc:
            raise Fault('runtime', f'runtime bridge failure: {exc}') from exc
        write_json(self.root / f'{self.index:04}-response.json', result)
        if result.get('status') == 'error': raise Fault('runtime', result['error'])
        return result

    def sync(self, patch):
        # Do not replace the bind-mount root inode. Apply all edits and restore reverted/deleted additions.
        current = {c['path']: c for c in patch['changes']}
        import shutil
        from .workspace import apply
        stage = self.root / f'sync-{self.index:04}'
        prepare(self.task, stage); apply(self.task, self.baseline, patch, stage)
        for name in self.previous | set(current):
            src, dst = stage / name, self.workspace / name
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
            elif dst.exists(): dst.unlink()
        self.previous = set(current)
        result = self.request({'op': 'sync'})
        self.available = result.get('status') == 'ready'
        return result

    def act(self, action):
        if not action_valid(action): raise ValueError('invalid pixel action')
        if not self.available:
            raise ValueError('candidate build failed; repair source before observing. Final protected grader will adjudicate.')
        result = self.request({'op': 'act', 'action': action})
        adapter = result.get('adapter', {})
        if adapter.get('url') != self.config['url'] or adapter.get('observation') != 'pixels':
            raise Fault('image_delivery', 'adapter URL/observation contract violation')
        path = Path(adapter.get('screenshot', ''))
        if not path.is_absolute() or not path.is_relative_to('/artifacts'):
            raise Fault('image_delivery', 'invalid screenshot path')
        host = self.artifacts / path.relative_to('/artifacts')
        if host.is_symlink() or not host.resolve().is_relative_to(self.artifacts) or not host.is_file():
            raise Fault('image_delivery', 'missing/escaping screenshot')
        try:
            from PIL import Image
            with Image.open(host) as img:
                if img.format != 'PNG' or not (1 <= img.width <= 10000 and 1 <= img.height <= 10000):
                    raise ValueError('invalid image format/dimensions')
                img.verify()
            # Preserve immutable pixels even if adapter reuses its output filename.
            raw = host.read_bytes()
            saved = self.root / f'{self.index:04}-pixels.png'; saved.write_bytes(raw)
        except (OSError, ValueError) as exc:
            raise Fault('image_delivery', f'undecodable screenshot: {exc}') from exc
        return {'evidence': evidence(saved), 'data_url': 'data:image/png;base64,' + base64.b64encode(raw).decode()}

    def close(self):
        if self.closed: return
        self.closed = True
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try: os.killpg(self.p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            self.p.wait(timeout=5)
        finally:
            self.log.close()
            if self.p.stdout: self.p.stdout.close()
