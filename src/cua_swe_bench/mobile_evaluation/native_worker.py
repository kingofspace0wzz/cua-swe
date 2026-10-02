"""Trusted standalone native supervisor (never imported/executed by project builds).

No browser starts at import. The host mounts this file read-only at /worker.py.
Project commands run ONLY in a host-launched sibling build namespace.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import http.server
import importlib.util
import inspect
import json
import mimetypes
import os
from pathlib import Path
import signal
import stat
import sys
import threading
import time
import traceback
from urllib.parse import unquote, urlsplit
import uuid


def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def namespace_base(*, venv=False, browser=False):
    from .settings import BROWSER_BWRAP, BWRAP, VENV
    launcher = BROWSER_BWRAP if browser else BWRAP
    argv = [launcher, '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
            '--ro-bind', '/usr', '/usr']
    for name in ('bin', 'sbin', 'lib', 'lib64'):
        if (Path('/usr') / name).exists():
            argv += ['--symlink', 'usr/' + name, '/' + name]
    argv += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/tmp/home', '--dir', '/etc']
    if venv:
        argv += ['--ro-bind', VENV, VENV]
    for k, v in {'PATH': '/usr/bin:/bin', 'HOME': '/tmp/home', 'TMPDIR': '/tmp', 'LANG': 'C.UTF-8',
                 'PYTHONDONTWRITEBYTECODE': '1'}.items():
        argv += ['--setenv', k, v]
    return argv


def outer_argv(root, source, dependencies, assets, browsers, python, reference=None, operation='runtime'):
    root = Path(root)
    argv = namespace_base(venv=True, browser=True)
    mounts = [(str(root / 'config.json'), '/config.json', False),
              (str(root / 'inputs/worker.py'), '/worker.py', False),
              (str(root / 'inputs/setup.py'), '/hooks/setup.py', False),
              (str(root / 'artifacts'), '/artifacts', True),
              (str(root / 'generations'), '/generations', False),
              (browsers, browsers, False), ('/etc/fonts', '/etc/fonts', False)]
    if Path('/var/cache/fontconfig').exists():
        mounts.append(('/var/cache/fontconfig', '/var/cache/fontconfig', False))
    if Path('/usr/share/zoneinfo').exists():
        mounts.append(('/usr/share/zoneinfo', '/usr/share/zoneinfo', False))
    if operation == 'grade':
        mounts.append((str(root / 'inputs/verifier.py'), '/hooks/verifier.py', False))
    if (root / 'inputs/fixture.json').exists():
        mounts.append((str(root / 'inputs/fixture.json'), '/hooks/fixture.json', False))
    if reference:
        mounts.append((str(reference), '/baseline', False))
    for i, asset in enumerate(assets):
        if asset['serve_prefix']:
            mounts.append((asset['path'], f'/public-assets/{i}', False))
    for src, dst, rw in mounts:
        argv += ['--bind' if rw else '--ro-bind', src, dst]
    argv += ['--setenv', 'PLAYWRIGHT_BROWSERS_PATH', browsers,
             '--chdir', '/tmp', '--', python, '-I', '/worker.py']
    return argv


def build_argv(config, scratch, output):
    """Host-launched sibling: RO public inputs, private writable copy and output.

    No candidate command executes on the host. No trusted runtime mounts enter
    this namespace. The tmpfs workspace permits generated CSS/config files.
    """
    c = config['native']
    argv = namespace_base()
    argv += ['--ro-bind', str(scratch), '/public-source', '--tmpfs', '/workspace']
    for dep in config['dependencies']:
        argv += ['--ro-bind', dep['path'], '/workspace/' + dep['destination']]
    for asset in c['assets']:
        argv += ['--ro-bind', asset['path'], '/workspace/' + asset['destination']]
    argv += ['--bind', str(output), '/workspace/' + c['build']['out_dir']]
    for key, value in c['build']['env'].items():
        argv += ['--setenv', key, value]
    # Fixed trusted bootstrap, arguments remain positional (no interpolation).
    return argv + ['--chdir', '/workspace', '--', '/bin/sh', '-c',
                   'cp -R /public-source/. /workspace/ || exit 125; exec "$@"',
                   'native-public-build', *c['build']['argv']]


def write_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2)
        f.write('\n')


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.file = self.path.open('x')

    def record(self, event, **data):
        with self.lock:
            self.file.write(json.dumps({'event': event, 'monotonic': time.monotonic(), **data}, default=str) + '\n')
            self.file.flush()

    def close(self):
        self.file.close()


def audit_output(root, required=()):
    """Build has exited. Reject links/devices/hardlinks BEFORE serving any bytes."""
    root = Path(root)
    manifest = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(base) / name
            if any(part in {'.git', '.env', 'environment.json', '.aws', '.ssh'} for part in p.relative_to(root).parts):
                raise ValueError('forbidden output path: ' + str(p))
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                raise ValueError(f'unsupported build output node: {p}')
            if stat.S_ISREG(st.st_mode):
                if st.st_nlink != 1:
                    raise ValueError(f'linked build output file: {p}')
                manifest[p.relative_to(root).as_posix()] = {'sha256': sha_file(p), 'size': st.st_size}
    for name in required:
        if name not in manifest:
            raise ValueError(f'build missing required file: {name}')
    return manifest


class StaticServer:
    """No source server, directory listings, arbitrary roots or fake API successes."""
    def __init__(self, root, cdn=None, journal=None):
        self.root = Path(root).resolve()
        self.cdn = Path(cdn).resolve() if cdn else None
        self.journal = journal
        self.unsupported = []
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), self.handler())
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.httpd.server_port}'

    def handler(self):
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = 'NativeStatic/1'
            sys_version = ''

            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self.serve(False)

            def do_GET(self):
                self.serve(True)

            def do_POST(self):
                self.serve(True)

            do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST

            def serve(self, send_body):
                started = time.monotonic()
                status, body, mime, filename = 404, b'Not found\n', 'text/plain; charset=utf-8', None
                parsed = urlsplit(self.path)
                path = unquote(parsed.path)
                pieces = path.split('/')
                unsafe = (parsed.scheme or parsed.netloc or not path.startswith('/') or path.startswith('//')
                          or any(x in ('.', '..') for x in pieces) or '\\' in path or '\0' in path
                          or any(x in ('.env', 'environment.json', '.git', '.ssh', '.aws') for x in pieces))
                if unsafe:
                    status, body = 403, b'Forbidden\n'
                elif path == '/api' or path.startswith('/api/') or self.command not in ('GET', 'HEAD'):
                    status = 501
                    body = b'{"error":"unsupported_application_api","backend":"native_static"}\n'
                    mime = 'application/json'
                    owner.unsupported.append({'method': self.command, 'path': path})
                else:
                    is_cdn = path == '/cdn' or path.startswith('/cdn/')
                    root = owner.cdn if is_cdn else owner.root
                    relative_path = path[len('/cdn/'):] if is_cdn else path.lstrip('/')
                    if root:
                        candidate = root / relative_path
                        resolved = candidate.resolve()
                        if not resolved.is_relative_to(root) or any(p.is_symlink() for p in [candidate, *candidate.parents] if p.is_relative_to(root)):
                            status, body = 403, b'Forbidden\n'
                        else:
                            if candidate.is_dir():
                                candidate = candidate / 'index.html'
                            # SPA fallback only for HTML navigations, not fetches/assets/CDN.
                            if not candidate.exists() and not is_cdn and not Path(path).suffix and 'text/html' in self.headers.get('Accept', ''):
                                candidate = root / 'index.html'
                            if candidate.is_file() and not candidate.is_symlink():
                                status, body = 200, candidate.read_bytes()
                                filename = str(candidate)
                                mime = {'.js': 'application/javascript', '.mjs': 'application/javascript',
                                        '.wasm': 'application/wasm', '.json': 'application/json',
                                        '.svg': 'image/svg+xml'}.get(candidate.suffix.lower()) or mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
                headers = {'Content-Type': mime, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
                           'X-Content-Type-Options': 'nosniff', 'Connection': 'close',
                           'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"}
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    if send_body:
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    if owner.journal:
                        owner.journal.record('static_http', method=self.command, target=self.path,
                                             request_headers=dict(self.headers), status=status, response_headers=headers,
                                             response_file=filename, response_sha256=hashlib.sha256(body).hexdigest(),
                                             response_b64=None if filename else base64.b64encode(body).decode(),
                                             seconds=time.monotonic() - started)
                self.close_connection = True
        return Handler

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def error_outcome(exc, stage='supervisor'):
    return {'execution': 'exception', 'errors': [{'stage': stage, 'type': type(exc).__name__, 'message': str(exc)}]}


def validate_outcome(raw, expected):
    """Same contract as grading.interpret; rejecting exceptions never means False."""
    if not isinstance(raw, dict) or raw.get('errors') != []:
        raise ValueError('verifier returned errors/missing errors')
    if raw.get('execution') == 'candidate_error':
        err = raw.get('candidate_error', {})
        if err.get('kind') not in ('syntax', 'app_crash', 'behavioral_timeout') or not isinstance(err.get('evidence'), str) or not err['evidence'].strip():
            raise ValueError('unattributed candidate error')
    elif raw.get('execution') == 'complete':
        rows = raw.get('assertions')
        if raw.get('expected_assertions') != expected or not isinstance(rows, list) or len(rows) != len(expected):
            raise ValueError('assertion manifest/count mismatch')
        if any(not isinstance(x, dict) or type(x.get('passed')) is not bool for x in rows) or {x.get('id') for x in rows} != set(expected):
            raise ValueError('invalid assertion IDs/truth values')
    else:
        raise ValueError('unknown verifier execution state')
    # Ensure no live objects, NaNs, or unserializable evidence leave a hook.
    json.dumps(raw, allow_nan=False)
    return raw


def load_hook(path, expected_sha, name):
    if sha_file(path) != expected_sha:
        raise ValueError(f'{name} hook digest changed')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BrowserDiagnostic(RuntimeError):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('native browser diagnostics: ' + json.dumps(diagnostics))


class Supervisor:
    def __init__(self, config, artifacts='/artifacts'):
        self.config, self.c = config, config['native']
        self.artifacts = Path(artifacts)
        self.journal = Journal(self.artifacts / 'events.jsonl')
        self.server = self.browser = self.playwright = self.context = self.page = None
        self.build_index = 0
        self.sync_pending = False
        self.generation = None
        self.ready = False
        self.setup = self.verifier = None
        self.pending_state = None
        self.faults = []
        self.page_tasks = set()
        self.baseline = None
        self.ctx = {'task_digest': config['task_digest'], 'expected_assertions': config['expected_assertions'],
                    'phase': config['operation'], 'output_dir': str(self.artifacts), 'fixture': None, 'baseline': None}

    async def initialize(self):
        self.setup = load_hook('/hooks/setup.py', self.c['setup']['sha256'], 'native_task_setup')
        if self.config['operation'] == 'grade':
            self.verifier = load_hook('/hooks/verifier.py', self.c['verifier']['sha256'], 'native_task_verifier')
            if not inspect.iscoroutinefunction(getattr(self.verifier, 'grade', None)):
                raise ValueError('verifier must define async grade(page, ctx)')
        names = ['seed']
        if self.c['capture_required']:
            names.append('capture')
        if self.c['scene']['state_mode'] == 'hooks':
            names += ['save', 'restore']
        for name in names:
            if not inspect.iscoroutinefunction(getattr(self.setup, name, None)):
                raise ValueError(f'setup must define async {name}(page, ctx, ...)')
        if 'fixture' in self.c:
            if sha_file('/hooks/fixture.json') != self.c['fixture']['sha256']:
                raise ValueError('fixture digest changed')
            self.ctx['fixture'] = json.loads(Path('/hooks/fixture.json').read_text())
        if self.config['has_reference']:
            self.baseline = json.loads(Path('/baseline/baseline.json').read_text())
            self.ctx['baseline'] = self.baseline
            self.ctx['baseline_dir'] = '/baseline/artifacts'
        self.journal.record('initialized', operation=self.config['operation'],
                            namespaces={n: os.readlink('/proc/self/ns/' + n) for n in ('mnt', 'net', 'pid', 'user')})

    async def hook(self, module, name, *extra):
        started = time.monotonic()
        self.journal.record('hook_start', name=name)
        try:
            value = await asyncio.wait_for(getattr(module, name)(self.page, dict(self.ctx), *extra),
                                           self.c['scene']['timeout_ms'] / 1000)
            self.journal.record('hook_finish', name=name, seconds=time.monotonic() - started)
            return value
        except BaseException as exc:
            self.journal.record('hook_error', name=name, error=repr(exc), traceback=traceback.format_exc())
            raise

    async def prepare_sync(self):
        # Save exactly once across failed edits; never overwrite with broken state.
        if self.ready and self.c['scene']['state_mode'] == 'hooks' and not self.sync_pending:
            state = await self.hook(self.setup, 'save')
            json.dumps(state, allow_nan=False)
            self.pending_state = state
        self.sync_pending = True
        self.ready = False
        return {'status': 'build_prepared'}

    def accept_generation(self, update, root='/generations'):
        number = update.get('generation')
        if not isinstance(number, str) or len(number) != 8 or not number.isascii() or not number.isdigit():
            raise ValueError('invalid generation name')
        if int(number) <= self.build_index:
            raise ValueError('stale generation update')
        generation = Path(root) / number
        manifest_path = generation / 'manifest.json'
        if generation.is_symlink() or manifest_path.is_symlink() or sha_file(manifest_path) != update.get('manifest_sha256'):
            raise ValueError('generation manifest digest mismatch')
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('task_digest') != self.config['task_digest'] or manifest.get('generation') != number:
            raise ValueError('generation identity mismatch')
        output = generation / 'app'
        if output.is_symlink() or not output.is_dir():
            raise ValueError('invalid generation output')
        if audit_output(output, self.c['build']['required_files']) != manifest['output']:
            raise ValueError('generation bytes differ from manifest')
        self.build_index = int(number)
        self.generation = number
        self.journal.record('generation_accepted', update=update, manifest=manifest)
        return output

    def spawn(self, coro):
        task = asyncio.create_task(coro)
        self.page_tasks.add(task)
        def done(t):
            self.page_tasks.discard(t)
            if not t.cancelled() and t.exception():
                self.faults.append({'stage': 'browser_callback', 'error': repr(t.exception())})
        task.add_done_callback(done)

    def allowed_url(self, url, frame=False):
        u, app = urlsplit(url), urlsplit(self.server.origin)
        if u.scheme != 'http' or u.netloc != app.netloc or u.username or u.password:
            return False
        if not frame:
            return True
        return any(u.path == p.rstrip('/') or u.path.startswith(p if p.endswith('/') else p + '/') for p in self.c['scene']['frame_paths'])

    async def route(self, route, request):
        allowed = self.allowed_url(request.url)
        if request.is_navigation_request():
            frame = request.frame
            allowed = allowed and frame.page == self.page
            if frame != self.page.main_frame:
                allowed = allowed and self.allowed_url(request.url, frame=True)
        if allowed:
            await route.continue_()
        else:
            self.faults.append({'stage': 'network_policy', 'url': request.url, 'method': request.method})
            await route.abort('blockedbyclient')

    async def navigation(self, frame):
        # file:/data:/about: navigation may never enter HTTP routing. Fail closed,
        # close page before any later screenshot can be delivered.
        if not self.allowed_url(frame.url, frame=frame != self.page.main_frame):
            self.faults.append({'stage': 'navigation_policy', 'url': frame.url})
            await self.page.close()

    async def extra_page(self, page):
        if page != self.page:
            self.faults.append({'stage': 'popup_blocked'})
            await page.close()

    async def request_receipt(self, request):
        self.journal.record('browser_request', url=request.url, method=request.method,
                            headers=await request.all_headers(), resource_type=request.resource_type,
                            body_b64=base64.b64encode(request.post_data_buffer or b'').decode())

    async def response_receipt(self, response):
        self.journal.record('browser_response', url=response.url, status=response.status,
                            headers=await response.all_headers())

    async def new_context(self):
        if self.context:
            await self.context.tracing.stop(path=str(self.artifacts / f'trace-{self.build_index - 1:04}.zip'))
            await self.context.close()
        s = self.c['scene']
        self.context = await self.browser.new_context(viewport=s['viewport'], timezone_id=s['timezone'],
                            locale=s['locale'], device_scale_factor=s['device_scale_factor'], service_workers='block',
                            accept_downloads=False, permissions=[], bypass_csp=False,
                            record_har_path=str(self.artifacts / f'network-{self.build_index:04}.har'),
                            record_har_mode='full', record_har_content='embed')
        self.context.set_default_timeout(s['timeout_ms'])
        self.context.set_default_navigation_timeout(s['timeout_ms'])
        await self.context.tracing.start(screenshots=False, snapshots=False, sources=False)
        await self.context.route('**/*', self.route)
        async def block_websocket(ws):
            self.faults.append({'stage': 'websocket_unsupported', 'url': ws.url})
            await ws.close(code=1008, reason='Static application backend has no WebSocket API')
        await self.context.route_web_socket('**/*', block_websocket)
        self.page = await self.context.new_page()
        self.context.on('page', lambda p: self.spawn(self.extra_page(p)))
        self.page.on('framenavigated', lambda f: self.spawn(self.navigation(f)))
        self.page.on('pageerror', self.record_page_error)
        self.page.on('crash', lambda: self.faults.append({'stage': 'page_crash', 'error': 'Chromium renderer crashed; attribution unknown'}))
        self.page.on('console', lambda m: self.journal.record('console', type=m.type, text=m.text, location=m.location))
        self.page.on('dialog', lambda d: self.spawn(d.dismiss()))
        self.page.on('download', lambda d: self.spawn(d.cancel()))
        self.context.on('request', lambda r: self.spawn(self.request_receipt(r)))
        self.context.on('response', lambda r: self.spawn(self.response_receipt(r)))
        self.context.on('requestfailed', lambda r: self.journal.record('browser_request_failed', url=r.url, failure=r.failure))

    def record_page_error(self, error):
        diagnostic = {'stage': 'pageerror', 'error': str(error)}
        self.faults.append(diagnostic)
        # Keep diagnostics in private custody while returning actual pixels.
        # This records an app exception, not a grading attribution.
        self.journal.record('browser_page_error', diagnostic=diagnostic,
                            generation=self.generation)

    async def load(self, output, *, allow_page_errors=False):
        cdn = next((f'/public-assets/{i}' for i, a in enumerate(self.c['assets']) if a['serve_prefix']), None)
        if self.server is None:
            self.server = StaticServer(output, cdn, self.journal)
        else:
            # Keep origin/localStorage/navigation constant across builds.
            self.server.root = output.resolve()
            self.server.unsupported.clear()
        if self.browser is None:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True, chromium_sandbox=True,
                args=['--disable-background-networking', '--disable-component-update', '--disable-sync',
                      '--no-first-run', '--no-default-browser-check', '--disable-extensions'])
        self.faults = []
        if self.context is None or self.c['scene']['state_mode'] == 'reset_to_scene':
            await self.new_context()
            await self.page.goto(self.server.origin + self.c['scene']['path'], wait_until='load')
            await self.hook(self.setup, 'seed')
        else:
            await self.page.reload(wait_until='load')
            await self.hook(self.setup, 'restore', self.pending_state)
        await self.check_faults(allow_page_errors=allow_page_errors)
        self.pending_state = None
        self.sync_pending = False
        self.ready = True

    async def check_faults(self, *, allow_page_errors=False):
        await asyncio.sleep(0)  # Drain navigation/callback tasks before returning pixels.
        if self.page_tasks:
            await asyncio.gather(*list(self.page_tasks), return_exceptions=True)
        unsupported = [r for r in self.server.unsupported if r['method'] not in ('GET', 'HEAD') or r['path'] not in self.c.get('static_api_fallbacks', {})] if self.server else []
        if unsupported:
            raise RuntimeError('unsupported application API; no successful behavior invented: ' + json.dumps(unsupported))
        recoverable = allow_page_errors and self.config['operation'] == 'runtime'
        fatal = [d for d in self.faults if not (recoverable and d.get('stage') == 'pageerror')]
        if fatal:
            raise BrowserDiagnostic(fatal)

    async def capture(self):
        if self.c['capture_required']:
            state = await self.hook(self.setup, 'capture')
            if not state or not isinstance(state, (dict, list)):
                raise ValueError('capture hook must return nonempty real JSON state')
            json.dumps(state, allow_nan=False)
            kind = 'native_hook_pre_edit'
        else:
            # Explicitly source-only, never a fake visual reference.
            state = {'source_manifest': self.config['source_manifest']}
            kind = 'source_only_explicit_backend'
        await self.check_faults()
        raw = {'execution': 'complete', 'errors': [], 'state': state, 'capture_kind': kind,
               'task_digest': self.config['task_digest']}
        write_json(self.artifacts / 'baseline.json', raw)
        self.baseline = raw
        self.ctx['baseline'] = raw
        self.ctx['baseline_dir'] = str(self.artifacts)
        return raw

    async def diagnose(self, diagnostic):
        # Timeouts, missing setup, provider or hook exceptions never reach this
        # attribution hook. Only concrete build/page diagnostics can be attributed.
        if diagnostic.get('stage') == 'browser' and any(d.get('stage') != 'pageerror' for d in diagnostic['diagnostics']):
            return error_outcome(RuntimeError(json.dumps(diagnostic)), 'browser_infrastructure_or_policy')
        if diagnostic.get('infrastructure') or (diagnostic.get('stage') == 'build' and 'bwrap:' in diagnostic.get('stderr_tail', '')):
            return error_outcome(RuntimeError(json.dumps(diagnostic)), 'build_sandbox')
        if self.verifier and inspect.iscoroutinefunction(getattr(self.verifier, 'diagnose', None)):
            result = await self.hook(self.verifier, 'diagnose', diagnostic)
            if result is not None:
                validate_outcome(result, self.config['expected_assertions'])
                if result['execution'] != 'candidate_error':
                    raise ValueError('diagnose may only return attributed candidate_error or None')
                return result
        return error_outcome(RuntimeError(json.dumps(diagnostic)), 'unattributed_application_failure')

    async def rebuild(self, op, update):
        if op == 'sync' and not self.sync_pending:
            raise ValueError('sync must prepare state before sibling build')
        self.ready = False
        diagnostic = update.get('diagnostic')
        if diagnostic:
            if op == 'grade':
                return await self.diagnose(diagnostic)
            if op == 'capture':
                raise RuntimeError('capture build failed: ' + json.dumps(diagnostic))
            return {'status': 'candidate_build_failed', 'diagnostic': diagnostic}
        try:
            await self.load(self.accept_generation(update), allow_page_errors=(op == 'sync'))
        except BrowserDiagnostic as exc:
            if op == 'grade':
                return await self.diagnose({'stage': 'browser', 'diagnostics': exc.diagnostics})
            raise
        if op in ('start', 'capture'):
            await self.capture()
        if op == 'grade':
            raw = await self.hook(self.verifier, 'grade')
            try:
                await self.check_faults()
            except BrowserDiagnostic as exc:
                return await self.diagnose({'stage': 'browser', 'diagnostics': exc.diagnostics})
            return validate_outcome(raw, self.config['expected_assertions'])
        return {'status': 'ready'}

    async def act(self, action):
        allowed = {'screenshot': {'type'}, 'reload': {'type'}, 'click': {'type', 'x', 'y'}, 'type': {'type', 'text'},
                   'press': {'type', 'key'}, 'scroll': {'type', 'dx', 'dy'},
                   'long_press': {'type', 'x', 'y', 'duration_ms'},
                   'drag': {'type', 'from_x', 'from_y', 'to_x', 'to_y', 'duration_ms'}}
        if not isinstance(action, dict) or action.get('type') not in allowed or set(action) != allowed[action['type']]:
            raise ValueError('unknown action schema')
        if not self.ready:
            raise RuntimeError('app not ready')
        kind = action['type']
        if kind in ('click', 'long_press', 'drag'):
            vp = self.c['scene']['viewport']
            points = [('x', 'width'), ('y', 'height')] if kind != 'drag' else [
                ('from_x', 'width'), ('from_y', 'height'), ('to_x', 'width'), ('to_y', 'height')]
            if any(type(action[k]) is not int or not 0 <= action[k] < vp[axis] for k, axis in points):
                raise ValueError('pointer outside viewport')
            if kind == 'click':
                await self.page.mouse.click(action['x'], action['y'])
            else:
                duration = action['duration_ms']
                if type(duration) is not int or not (400 if kind == 'long_press' else 100) <= duration <= 2000:
                    raise ValueError('invalid pointer duration')
                x, y = (action['x'], action['y']) if kind == 'long_press' else (action['from_x'], action['from_y'])
                await self.page.mouse.move(x, y)
                try:
                    await self.page.mouse.down()
                    if kind == 'long_press':
                        await asyncio.sleep(duration / 1000)
                    else:
                        # Playwright steps alone are not timed; schedule ~60Hz motion.
                        steps = max(2, round(duration / 16))
                        start = time.monotonic()
                        for step in range(1, steps + 1):
                            await asyncio.sleep(max(0, start + duration / 1000 * step / steps - time.monotonic()))
                            await self.page.mouse.move(x + (action['to_x'] - x) * step / steps,
                                                       y + (action['to_y'] - y) * step / steps)
                finally:
                    await self.page.mouse.up()
        elif kind == 'reload':
            # A user reload must observe persisted application state. It must
            # never re-inject the initial fixture or restore transient UI state.
            await self.page.reload(wait_until='load')
        elif kind == 'type':
            if not isinstance(action['text'], str) or len(action['text']) > 10000:
                raise ValueError('invalid text')
            await self.page.keyboard.insert_text(action['text'])
        elif kind == 'press':
            if action['key'] not in ('Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'):
                raise ValueError('invalid key')
            await self.page.keyboard.press(action['key'])
        elif kind == 'scroll':
            if any(type(action[k]) is not int or abs(action[k]) > 5000 for k in ('dx', 'dy')):
                raise ValueError('invalid scroll')
            await self.page.mouse.wheel(action['dx'], action['dy'])
        await self.check_faults(allow_page_errors=True)
        name = 'pixels-' + uuid.uuid4().hex + '.png'
        await self.page.screenshot(path=str(self.artifacts / name), type='png', full_page=False, timeout=self.c['scene']['timeout_ms'])
        await self.check_faults(allow_page_errors=True)
        self.journal.record('pixels', path=name, sha256=sha_file(self.artifacts / name))
        return {'status': 'pixels', 'frame': name}

    async def close(self):
        # Attempt every cleanup independently; a failed trace flush must not
        # leave the browser/server or a build process alive.
        async def cleanup(name, call):
            try:
                await asyncio.wait_for(call(), timeout=5)
            except Exception as exc:
                self.journal.record('cleanup_error', resource=name, error=repr(exc))
        for task in list(self.page_tasks):
            task.cancel()
        if self.page_tasks:
            await asyncio.gather(*list(self.page_tasks), return_exceptions=True)
        if self.context:
            await cleanup('trace', lambda: self.context.tracing.stop(path=str(self.artifacts / 'trace-final.zip')))
            await cleanup('context', self.context.close)
        if self.browser:
            await cleanup('browser', self.browser.close)
        if self.playwright:
            await cleanup('playwright', self.playwright.stop)
        try:
            if self.server:
                self.server.close()
        finally:
            self.journal.close()


async def main():
    config = json.loads(Path('/config.json').read_text())
    worker = Supervisor(config)
    # Keep stdout a private RPC channel even if a trusted hook prints diagnostics.
    channel = sys.stdout
    sys.stdout = sys.stderr
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, current.cancel)
    try:
        await worker.initialize()
        reader = asyncio.StreamReader(limit=16 * 1024 * 1024)
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
        started = False
        while line := await reader.readline():
            request = json.loads(line)
            op = request.get('op')
            worker.journal.record('rpc_request', request=request)
            try:
                if op in ('start', 'sync', 'capture', 'grade'):
                    if (op == 'sync' and (not started or config['operation'] != 'runtime')) or (op != 'sync' and started):
                        raise ValueError('invalid lifecycle operation')
                    if op != 'sync' and op != ('start' if config['operation'] == 'runtime' else config['operation']):
                        raise ValueError('operation not authorized by immutable config')
                    started = True
                    answer = await asyncio.wait_for(worker.rebuild(op, request), config['rpc_timeout'])
                    if op in ('capture', 'grade'):
                        if op == 'grade':
                            write_json(worker.artifacts / 'result.json', answer)
                        answer = {'status': 'completed'}
                elif op == 'prepare_sync' and started and config['operation'] == 'runtime':
                    answer = await asyncio.wait_for(worker.prepare_sync(), config['rpc_timeout'])
                elif op == 'act' and config['operation'] == 'runtime':
                    answer = await asyncio.wait_for(worker.act(request['action']), config['rpc_timeout'])
                elif op == 'close':
                    answer = {'status': 'closed'}
                else:
                    raise ValueError('invalid operation')
            except Exception as exc:
                worker.journal.record('rpc_exception', error=repr(exc), traceback=traceback.format_exc())
                if op in ('capture', 'grade'):
                    name = 'baseline.json' if op == 'capture' else 'result.json'
                    if not (worker.artifacts / name).exists():
                        write_json(worker.artifacts / name, error_outcome(exc, op))
                    answer = {'status': 'completed'}
                else:
                    answer = {'status': 'error', 'error': repr(exc)}
            worker.journal.record('rpc_response', response=answer)
            channel.write(json.dumps(answer) + '\n')
            channel.flush()
            if op in ('close', 'capture', 'grade'):
                break
    finally:
        await worker.close()


if __name__ == '__main__':
    asyncio.run(main())
