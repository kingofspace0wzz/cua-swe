"""Browser-free native constructor checks. All artifacts stay in authorized job dir."""
import asyncio
import copy
import time
import shutil
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import pytest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cua_swe_bench.mobile_evaluation.settings import PYTHON, VENV
from cua_swe_bench.mobile_evaluation.core import Task, Fault, digest, evidence, tree, write_json
from cua_swe_bench.mobile_evaluation.workspace import prepare, extract
from cua_swe_bench.mobile_evaluation.grading import interpret
from cua_swe_bench.mobile_evaluation.native_backend import (
    validate_native, stage_patch, freeze_png, native_operation, NativeRuntime, _Session, SiblingBuilds)
from cua_swe_bench.mobile_evaluation.native_worker import (
    StaticServer, Journal, audit_output, namespace_base, outer_argv, build_argv,
    validate_outcome, error_outcome, Supervisor)

JOB = Path(tempfile.mkdtemp(prefix='mobile-reconstruction-native-tests-')).resolve()


def fixture(root):
    """Real Task schema; fake browser hash is only bypassed in unit validation."""
    root.mkdir()
    (root / 'instruction.md').write_text('Repair the label; preserve entered text.\n')
    (root / 'index.html').write_text('<!doctype html><input id="name"><script src="/app.js"></script>')
    (root / 'app.js').write_text('window.publicValue = 1;\n')
    (root / 'setup.py').write_text('async def seed(page, ctx):\n    await page.locator("#name").fill("initial")\n')
    (root / 'verifier.py').write_text('async def grade(page, ctx):\n    return {"execution":"complete","errors":[],"expected_assertions":["label"],"assertions":[{"id":"label","passed":True}]}\n')
    return Task({'task_id': 'native-unit-control', 'revision': '1', 'release': 'construction-only',
                 'instruction': evidence(root / 'instruction.md'),
                 'public_files': {n: evidence(root / n) for n in ('index.html', 'app.js')},
                 'editable': ['app.js', 'added/'], 'scratch': ['dist/'], 'dependencies': [],
                 'expected_assertions': ['label'],
                 'backend': {'browser_runtime': True, 'browser_sha256': 'unit-not-a-browser-hash', 'grade': 'native',
                             'native': {'schema': 1, 'capture_required': False, 'assets': [],
                                'setup': evidence(root / 'setup.py'), 'verifier': evidence(root / 'verifier.py'),
                                'build': {'argv': ['/bin/sh', '-c', 'cp index.html app.js dist/'],
                                          'out_dir': 'dist', 'timeout_seconds': 10, 'env': {}, 'required_files': ['index.html', 'app.js']},
                                'scene': {'path': '/', 'viewport': {'width': 400, 'height': 800}, 'timezone': 'UTC',
                                          'locale': 'en-US', 'device_scale_factor': 1, 'state_mode': 'reset_to_scene',
                                          'frame_paths': [], 'timeout_ms': 1000}}}})


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_root = Path(tempfile.mkdtemp(prefix='unit-', dir=JOB)).resolve()

    def setUp(self):
        self.root = self.run_root / self._testMethodName
        self.root.mkdir()
        self.task = fixture(self.root / 'fixture')

    def validate(self, task=None):
        # Avoid hashing installed browser tree in every unit test. All native
        # hook/assets validation still runs, as do core source checks elsewhere.
        with patch.object(Task, 'validate_inputs'):
            return validate_native(task or self.task)

    def test_config_and_task_identity_no_circular_hash(self):
        c = self.validate()
        self.assertEqual(c['scene']['state_mode'], 'reset_to_scene')
        old = self.task.id
        config = copy.deepcopy(self.task.c)
        config['controls'] = {'gold': {'patch': {'sha256': old}}}
        self.assertEqual(Task(config).id, old)
        config['backend']['native']['scene']['path'] = '/other'
        self.assertNotEqual(Task(config).id, old)

    def test_reject_ambiguous_or_unpinned_config(self):
        mutations = [lambda c: c['scene'].pop('state_mode'),
                     lambda c: c['scene'].update(path='https://elsewhere/'),
                     lambda c: c['scene'].update(frame_paths=['//outside']),
                     lambda c: c['build'].update(env={'PROVIDER_TOKEN': 'not-read'}),
                     lambda c: c['build'].update(out_dir='../artifacts'),
                     lambda c: c['build'].update(required_files=[]),
                     lambda c: c['setup'].update(sha256='0' * 64),
                     lambda c: c.update(services=[['npm', 'run', 'preview']])]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                t = Task(copy.deepcopy(self.task.c))
                mutate(t.c['backend']['native'])
                with self.assertRaises((Fault, ValueError)):
                    self.validate(t)

    def test_capture_required_uses_explicit_marker_not_task_digest(self):
        self.task.c['backend']['native']['capture_required'] = True
        with self.assertRaises(Fault):
            self.validate()
        self.task.c['backend']['capture'] = 'native'
        self.validate()

    def test_normalized_hashed_public_assets(self):
        asset = self.root / 'cdn'
        asset.mkdir()
        (asset / 'photo.svg').write_text('<svg/>')
        self.task.c['backend']['native']['assets'] = [{'path': str(asset), 'sha256': digest(tree(asset)),
                                                     'destination': 'mobilegym-data', 'serve_prefix': '/cdn/'}]
        self.validate()
        (asset / 'photo.svg').write_text('changed')
        with self.assertRaises(Fault):
            self.validate()

    def test_child_mount_separation(self):
        c = self.validate()
        c['assets'] = [{'path': '/public-cdn', 'destination': 'mobilegym-data', 'serve_prefix': '/cdn/'}]
        config = {'native': c, 'dependencies': [{'path': '/public-deps', 'destination': 'node_modules'}]}
        child = build_argv(config, '/scratch/0001', '/builds/0001')
        self.assertIn('--unshare-all', child)
        self.assertIn('--clearenv', child)
        self.assertIn('/workspace/dist', child)
        for private in ('/artifacts', '/hooks', '/worker.py', '/config.json', '/baseline', VENV, '/source', '/proc/1/root'):
            self.assertNotIn(private, child)
        self.assertIn('/public-deps', child)
        self.assertIn('--tmpfs', child)
        self.assertNotIn('--bind /scratch', ' '.join(child))
        outer = outer_argv(self.root, '/clean', [], [], '/browsers', '/python', operation='runtime')
        self.assertIn('/hooks/setup.py', outer)
        self.assertNotIn('/hooks/verifier.py', outer)
        self.assertIn('/etc/fonts', outer)
        self.assertIn('/hooks/verifier.py', outer_argv(self.root, '/clean', [], [], '/browsers', '/python', operation='grade'))
        self.assertNotIn('preview', outer)
        for ordinary in ('/source', '/deps/0', '/scratch', '/builds', '/clean'):
            self.assertNotIn(ordinary, outer)
        index = outer.index('/generations')
        self.assertEqual(outer[index - 2], '--ro-bind')

    def test_patch_deletion_addition_reversion_preserves_source_inputs(self):
        with patch.object(Task, 'validate_inputs'):
            source, runtime = self.root / 'candidate', self.root / 'runtime'
            baseline = prepare(self.task, source)
            prepare(self.task, runtime)
            original_inode = runtime.stat().st_ino
            (source / 'app.js').unlink()
            (source / 'added').mkdir()
            (source / 'added/new.bin').write_bytes(b'\0\xff')
            one = extract(self.task, baseline, source)
            previous = stage_patch(self.task, baseline, one, runtime, self.root / 'stage1', set())
            self.assertEqual(tree(source), tree(runtime))
            empty = {'task_digest': self.task.id, 'baseline_digest': digest(baseline), 'changes': []}
            stage_patch(self.task, baseline, empty, runtime, self.root / 'stage2', previous)
            self.assertEqual(tree(runtime), baseline)
            self.assertEqual(runtime.stat().st_ino, original_inode)
            self.assertEqual((self.root / 'fixture/app.js').read_text(), 'window.publicValue = 1;\n')
            one['changes'][0]['before'] = {'sha256': 'wrong'}
            with self.assertRaises(Fault):
                stage_patch(self.task, baseline, one, runtime, self.root / 'stage3', set())

    def test_png_full_decode_and_immutable_unique_frames(self):
        from PIL import Image
        source = self.root / 'source.png'
        Image.new('RGB', (4, 3), 'blue').save(source)
        out = self.root / 'frozen.png'
        pixels = freeze_png(source, out)
        self.assertEqual(set(pixels), {'evidence', 'data_url'})
        frozen = out.read_bytes()
        Image.new('RGB', (4, 3), 'red').save(source)
        self.assertEqual(out.read_bytes(), frozen)
        with self.assertRaises(FileExistsError):
            freeze_png(source, out)
        source.write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
        with self.assertRaises(Exception):
            freeze_png(source, self.root / 'bad.png')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_static_spa_javascript_cdn_and_no_fake_api(self):
        app, cdn = self.root / 'app', self.root / 'cdn'
        app.mkdir(); cdn.mkdir()
        (app / 'index.html').write_text('<!doctype html>simple app')
        (app / 'app.mjs').write_text('export const value = 1;')
        (app / 'empty').mkdir()
        (cdn / 'x.json').write_text('{"public":true}')
        journal = Journal(self.root / 'http.jsonl')
        server = StaticServer(app, cdn, journal)
        def get(path, accept='*/*', method='GET'):
            conn = http.client.HTTPConnection('127.0.0.1', server.httpd.server_port, timeout=2)
            try:
                conn.request(method, path, headers={'Accept': accept})
                response = conn.getresponse()
                return response.status, response.getheader('Content-Type'), response.read()
            finally:
                conn.close()
        try:
            self.assertEqual(get('/scene/thread/42', 'text/html')[0], 200)
            self.assertEqual(get('/app.mjs')[1], 'application/javascript')
            self.assertEqual(get('/missing.js', 'text/html')[0], 404)
            self.assertEqual(get('/cdn/x.json')[2], b'{"public":true}')
            self.assertEqual(get('/cdn/missing', 'text/html')[0], 404)
            self.assertEqual(get('/api/sdcard')[0], 501)
            self.assertIn(b'unsupported_application_api', get('/api/runs')[2])
            self.assertEqual(get('/empty/')[0], 404)
            self.assertEqual(get('/%2e%2e/private')[0], 403)
            self.assertEqual(get('/app.mjs', method='HEAD')[2], b'')
            self.assertEqual(get('/scene', method='POST')[0], 501)
        finally:
            server.close(); journal.close()
        self.assertTrue(all('response_sha256' in json.loads(line) for line in (self.root / 'http.jsonl').read_text().splitlines()))

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_output_and_server_reject_nonregular_links(self):
        app = self.root / 'app'; app.mkdir()
        (app / 'index.html').write_text('app')
        (app / 'alias').symlink_to('index.html')
        with self.assertRaises(ValueError):
            audit_output(app, ['index.html'])
        server = StaticServer(app)
        conn = http.client.HTTPConnection('127.0.0.1', server.httpd.server_port, timeout=2)
        try:
            conn.request('GET', '/alias')
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        finally:
            conn.close(); server.close()

    def test_outcome_false_is_not_exception_or_timeout(self):
        raw = {'execution': 'complete', 'errors': [], 'expected_assertions': ['label'],
               'assertions': [{'id': 'label', 'passed': False}]}
        self.assertFalse(interpret(validate_outcome(raw, ['label']), ['label'])['correct'])
        for bad in (error_outcome(TimeoutError('unknown')), error_outcome(AssertionError('hook defect')),
                    {'execution': 'complete', 'errors': [], 'expected_assertions': ['label'], 'assertions': []},
                    {'execution': 'candidate_error', 'errors': [], 'candidate_error': {'kind': 'syntax'}}):
            with self.assertRaises(ValueError):
                validate_outcome(bad, ['label'])
            with self.assertRaises(Fault):
                interpret(bad, ['label'])
        candidate = {'execution': 'candidate_error', 'errors': [],
                     'candidate_error': {'kind': 'syntax', 'evidence': 'pinned task verifier attributed app.js parser diagnostic'}}
        self.assertFalse(interpret(validate_outcome(candidate, ['label']), ['label'])['correct'])

    def test_unsupported_missing_setup_is_structured_not_false(self):
        with patch('cua_swe_bench.mobile_evaluation.native_backend.validate_native', side_effect=Fault('configuration', 'missing setup')):
            result = native_operation(self.task, self.root / 'missing', self.root / 'operation', 'grade')
        self.assertEqual(result['returncode'], 2)
        raw = json.loads((self.root / 'operation/result.json').read_text())
        self.assertEqual(raw['execution'], 'exception')
        with self.assertRaises(Fault):
            interpret(raw, ['label'])

    def test_capture_after_patch_is_rejected_before_any_process(self):
        with patch.object(Task, 'validate_inputs'):
            source = self.root / 'candidate'; prepare(self.task, source)
            (source / 'app.js').write_text('edited')
            with patch('cua_swe_bench.mobile_evaluation.native_backend.subprocess.Popen') as popen:
                result = native_operation(self.task, source, self.root / 'capture', 'capture')
                popen.assert_not_called()
        self.assertEqual(result['returncode'], 2)
        self.assertIn('precede candidate edits', result['stderr'])

    def test_constructor_interruption_reaps_session(self):
        with patch.object(Task, 'validate_inputs'):
            baseline = prepare(self.task, self.root / 'baseline-source')
            with patch('cua_swe_bench.mobile_evaluation.native_backend._Session') as cls:
                cls.return_value.request.side_effect = KeyboardInterrupt()
                with self.assertRaises(KeyboardInterrupt):
                    NativeRuntime(self.task, self.root / 'runtime', baseline)
                cls.return_value.close.assert_called_once()

    def test_state_policy_is_explicit_and_save_restore_not_silent(self):
        c = self.validate()
        config = {'native': c, 'dependencies': [], 'operation': 'runtime', 'expected_assertions': ['label'],
                  'task_digest': self.task.id, 'has_reference': False, 'source_manifest': {}}
        worker = Supervisor(config, self.root)
        worker.c['scene']['state_mode'] = 'hooks'
        worker.ready = True
        calls = []
        async def hook(module, name, *args):
            calls.append(name)
            return {'input': 'preserved', 'navigation': 'fixture-defined'}
        worker.hook = hook
        try:
            asyncio.run(worker.prepare_sync())
            result = asyncio.run(worker.rebuild('sync', {'diagnostic': {'stage': 'build', 'returncode': 1}}))
            asyncio.run(worker.prepare_sync())
            self.assertEqual(result['status'], 'candidate_build_failed')
            self.assertEqual(calls, ['save'])
            self.assertEqual(worker.pending_state['input'], 'preserved')
        finally:
            worker.journal.close()

    def test_preserve_restores_inputs_while_reset_reseeds(self):
        c = self.validate()
        config = {'native': c, 'dependencies': [], 'operation': 'runtime', 'expected_assertions': ['label'],
                  'task_digest': self.task.id, 'has_reference': False, 'source_manifest': {}}
        worker = Supervisor(config, self.root)
        worker.browser = object()  # No real browser/Playwright API is constructed.
        worker.context = object()
        worker.page = SimpleNamespace(reload=AsyncMock(), goto=AsyncMock())
        worker.server = SimpleNamespace(root=self.root, unsupported=[], origin='http://127.0.0.1:12345')
        worker.hook = AsyncMock()
        worker.new_context = AsyncMock()
        try:
            worker.c['scene']['state_mode'] = 'hooks'
            worker.pending_state = {'input': 'typed text', 'navigation': '/scene/second'}
            asyncio.run(worker.load(self.root))
            worker.hook.assert_awaited_once_with(worker.setup, 'restore', {'input': 'typed text', 'navigation': '/scene/second'})
            worker.new_context.assert_not_awaited()
            worker.page.reload.assert_awaited_once()
            worker.hook.reset_mock()
            worker.c['scene']['state_mode'] = 'reset_to_scene'
            asyncio.run(worker.load(self.root))
            worker.new_context.assert_awaited_once()
            worker.hook.assert_awaited_once_with(worker.setup, 'seed')
            worker.page.goto.assert_awaited_once_with('http://127.0.0.1:12345/', wait_until='load')
        finally:
            worker.journal.close()

    def test_unsupported_api_is_infrastructure_except_declared_real_fallback(self):
        c = self.validate()
        config = {'native': c, 'dependencies': [], 'operation': 'runtime', 'expected_assertions': ['label'],
                  'task_digest': self.task.id, 'has_reference': False, 'source_manifest': {}}
        worker = Supervisor(config, self.root)
        worker.server = SimpleNamespace(unsupported=[{'method': 'GET', 'path': '/api/sdcard'}])
        try:
            with self.assertRaisesRegex(RuntimeError, 'unsupported application API'):
                asyncio.run(worker.check_faults())
            worker.c['static_api_fallbacks'] = {'/api/sdcard': 'sdcard/manifest.json'}
            asyncio.run(worker.check_faults())
            worker.server.unsupported.append({'method': 'POST', 'path': '/api/sdcard'})
            with self.assertRaises(RuntimeError):
                asyncio.run(worker.check_faults())
        finally:
            worker.journal.close()
        self.task.c['backend']['native']['static_api_fallbacks'] = {'/api/sdcard': 'sdcard/manifest.json'}
        with self.assertRaises(Fault):
            self.validate()
        self.task.c['backend']['native']['build']['required_files'].append('sdcard/manifest.json')
        self.validate()

    def test_navigation_policy_only_same_origin_and_explicit_frames(self):
        c = self.validate()
        config = {'native': c, 'dependencies': [], 'operation': 'runtime', 'expected_assertions': ['label'],
                  'task_digest': self.task.id, 'has_reference': False, 'source_manifest': {}}
        worker = Supervisor(config, self.root)
        worker.server = SimpleNamespace(origin='http://127.0.0.1:12345')
        try:
            self.assertTrue(worker.allowed_url('http://127.0.0.1:12345/thread/42'))
            for url in ('https://127.0.0.1:12345/', 'http://127.0.0.1:12346/', 'file:///tmp/index.html', 'data:text/html,hi', 'about:blank'):
                self.assertFalse(worker.allowed_url(url))
            self.assertFalse(worker.allowed_url('http://127.0.0.1:12345/frame', frame=True))
            worker.c['scene']['frame_paths'] = ['/frame/']
            self.assertTrue(worker.allowed_url('http://127.0.0.1:12345/frame/a', frame=True))
            self.assertFalse(worker.allowed_url('http://127.0.0.1:12345/frame-elsewhere', frame=True))
        finally:
            worker.journal.close()

    def test_diagnose_never_attributes_bwrap_or_policy_errors(self):
        c = self.validate()
        config = {'native': c, 'dependencies': [], 'operation': 'grade', 'expected_assertions': ['label'],
                  'task_digest': self.task.id, 'has_reference': False, 'source_manifest': {}}
        worker = Supervisor(config, self.root)
        worker.verifier = SimpleNamespace(diagnose=AsyncMock())
        worker.hook = AsyncMock()
        try:
            for diagnostic in ({'stage': 'build', 'stderr_tail': 'bwrap: cannot create namespace'},
                               {'stage': 'browser', 'diagnostics': [{'stage': 'navigation_policy'}]}):
                outcome = asyncio.run(worker.diagnose(diagnostic))
                self.assertEqual(outcome['execution'], 'exception')
                worker.hook.assert_not_awaited()
        finally:
            worker.journal.close()

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_actual_sibling_build_public_inputs_failure_reversion_and_live_reader(self):
        c = self.validate()
        source = self.root / 'source'
        with patch.object(Task, 'validate_inputs'):
            baseline = prepare(self.task, source)
        deps, asset = self.root / 'deps', self.root / 'cdn'
        deps.mkdir(); asset.mkdir()
        (deps / 'value.txt').write_text('public dependency')
        (asset / 'value.txt').write_text('public asset')
        self.task.c['dependencies'] = [{'path': str(deps), 'destination': 'node_modules'}]
        (source / 'node_modules').mkdir()  # prepare() normally creates mountpoints
        c['assets'] = [{'path': str(asset), 'destination': 'mobilegym-data', 'serve_prefix': '/cdn/'}]
        c['build']['argv'] = ['/bin/sh', '-c',
            'if grep -q BROKEN app.js; then echo "candidate compile diagnostic" >&2; exit 7; fi; '
            'cp index.html app.js dist/; cat node_modules/value.txt mobilegym-data/value.txt > dist/public.txt; '
            'echo generated > generated.css; (sleep 1; echo late-child-output >&2; echo late > dist/late.txt) &']
        builds = SiblingBuilds(self.root, self.task, c)
        first = builds.run(source)
        first_root = self.root / 'generations' / first['generation']
        frozen = tree(first_root)
        self.assertEqual(tree(source), baseline)
        self.assertFalse((source / 'generated.css').exists())
        self.assertEqual((first_root / 'app/public.txt').read_text(), 'public dependencypublic asset')
        self.assertEqual((first_root / 'app/index.html').stat().st_mode & 0o222, 0)
        # Independent long-lived trusted sibling observes only atomic publications.
        # This is Python/manifest I/O, NOT Playwright or any browser launch.
        (self.root / 'inputs').mkdir(); (self.root / 'artifacts').mkdir()
        shutil.copyfile(Path(__file__).parents[1] / 'src/cua_swe_bench/mobile_evaluation/native_worker.py', self.root / 'inputs/worker.py')
        shutil.copyfile(self.root / 'fixture/setup.py', self.root / 'inputs/setup.py')
        config = {'native': c, 'operation': 'runtime', 'task_digest': self.task.id,
                  'expected_assertions': ['label'], 'has_reference': False, 'source_manifest': baseline}
        (self.root / 'config.json').write_text(json.dumps(config))
        argv = outer_argv(self.root, None, [], [], '/usr/share/zoneinfo', PYTHON)
        argv = argv[:argv.index('--') + 1] + [PYTHON, '-I', '-u', '-c',
            'import runpy,json,sys; from pathlib import Path; '
            'm=runpy.run_path("/worker.py",run_name="trusted_reader"); '
            's=m["Supervisor"](json.loads(Path("/config.json").read_text())); '
            '\ntry:\n for line in sys.stdin:\n  p=s.accept_generation(json.loads(line)); print((p/"app.js").read_text().strip(),flush=True)'
            '\nfinally: s.journal.close()']
        (self.root / 'reader-launch.json').write_text(json.dumps({'argv': argv, 'browser_launched': False}, indent=2))
        with (self.root / 'reader.stderr').open('wb') as err:
            reader = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                      text=True, env={'PATH': '/usr/bin:/bin'}, start_new_session=True)
            try:
                reader.stdin.write(json.dumps(first) + '\n'); reader.stdin.flush()
                import select
                self.assertTrue(select.select([reader.stdout], [], [], 10)[0])
                self.assertEqual(reader.stdout.readline().strip(), 'window.publicValue = 1;')
                (source / 'app.js').write_text('BROKEN')
                failed = builds.run(source)
                self.assertEqual(failed['diagnostic']['returncode'], 7)
                self.assertFalse(failed['diagnostic']['infrastructure'])
                self.assertEqual((source / 'app.js').read_text(), 'BROKEN')
                self.assertEqual(tree(first_root), frozen)
                (source / 'app.js').write_text('window.publicValue = 2;')
                second = builds.run(source)
                reader.stdin.write(json.dumps(second) + '\n'); reader.stdin.flush()
                self.assertTrue(select.select([reader.stdout], [], [], 10)[0])
                self.assertEqual(reader.stdout.readline().strip(), 'window.publicValue = 2;')
                time.sleep(1.1)  # detached build child must not survive completion
                self.assertFalse((first_root / 'app/late.txt').exists())
                self.assertNotIn('late-child-output', (self.root / 'build-receipts/00000001.stderr').read_text())
                self.assertEqual(tree(first_root), frozen)
            finally:
                reader.stdin.close()
                try:
                    reader.wait(timeout=10)
                finally:
                    if reader.poll() is None:
                        reader.kill(); reader.wait(timeout=5)
                    reader.stdout.close()
            self.assertEqual(reader.returncode, 0, (self.root / 'reader.stderr').read_text())
        self.assertEqual(list((self.root / 'build-work').iterdir()), [])
        self.assertEqual(len(list((self.root / 'generations').iterdir())), 2)
        (self.root / 'sibling-functional.json').write_text(json.dumps({
            'first_update': first, 'second_update': second, 'candidate_build_exit': failed['diagnostic']['returncode'],
            'live_sibling_reader_exit': reader.returncode, 'first_generation_unchanged': tree(first_root) == frozen,
            'private_work_cleaned': True, 'late_child_stderr_absent': True,
            'browser_launched': False, 'actual_bwrap_no_skips': True}, indent=2) + '\n')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_actual_build_timeout_and_invalid_output_are_distinct(self):
        c = self.validate()
        with patch.object(Task, 'validate_inputs'):
            source = self.root / 'source'; prepare(self.task, source)
        builds = SiblingBuilds(self.root, self.task, c)
        c['build']['argv'] = ['/bin/sh', '-c', 'sleep 10']
        c['build']['timeout_seconds'] = 1
        with self.assertRaises(Fault):
            builds.run(source)
        receipt = json.loads((self.root / 'build-receipts/00000001.json').read_text())
        self.assertTrue(receipt['infrastructure']); self.assertTrue(receipt['cleanup_complete'])
        self.assertTrue(receipt['timed_out'])
        c['build']['argv'] = ['/bin/true']
        result = builds.run(source)
        self.assertEqual(result['diagnostic']['stage'], 'build_output')
        self.assertFalse(result['diagnostic']['infrastructure'])
        self.assertEqual(list((self.root / 'generations').iterdir()), [])

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_actual_build_invalid_executable_is_infrastructure(self):
        c = self.validate()
        with patch.object(Task, 'validate_inputs'):
            source = self.root / 'source'; prepare(self.task, source)
        c['build']['argv'] = ['/missing-public-tool']
        builds = SiblingBuilds(self.root, self.task, c)
        with self.assertRaises(Fault):
            builds.run(source)
        self.assertTrue(json.loads((self.root / 'build-receipts/00000001.json').read_text())['infrastructure'])

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_real_native_operation_diagnostic_rpc_without_browser(self):
        # Exercise actual _Session host build -> sibling trusted supervisor RPC.
        # Diagnose runs without loading Chromium; no model or real app involved.
        c = self.task.c['backend']['native']
        c['build']['argv'] = ['/bin/sh', '-c', 'echo fixture-syntax-error >&2; exit 7']
        verifier = self.root / 'fixture/verifier.py'
        verifier.write_text('async def grade(page, ctx): raise RuntimeError("not called")\n'
            'async def diagnose(page, ctx, diagnostic):\n'
            '    if diagnostic["returncode"] != 7: raise RuntimeError("wrong diagnostic")\n'
            '    return {"execution":"candidate_error","errors":[],"candidate_error":'
            '{"kind":"syntax","evidence":"public tiny fixture compiler diagnostic only"}}\n')
        c['verifier'] = evidence(verifier)
        with patch.object(Task, 'validate_inputs'):
            source = self.root / 'source'; before = prepare(self.task, source)
            result = native_operation(self.task, source, self.root / 'operation', 'grade')
        self.assertEqual(result['returncode'], 0, result)
        self.assertFalse(interpret(json.loads((self.root / 'operation/result.json').read_text()), ['label'])['correct'])
        self.assertEqual(tree(source), before)
        self.assertEqual(list((self.root / 'operation/build-work').iterdir()), [])
        self.assertEqual(list((self.root / 'operation/generations').iterdir()), [])
        self.assertEqual(json.loads((self.root / 'operation/0001-response.json').read_text())['response']['status'], 'completed')
        config = json.loads((self.root / 'operation/config.json').read_text())
        self.assertNotIn('argv', config['native']['build']); self.assertNotIn('dependencies', config)

    def test_session_sync_saves_before_host_build_and_private_update(self):
        session = object.__new__(_Session)
        session.source = self.root; session.closed = False
        order = []
        update = {'generation': '00000002', 'manifest_sha256': 'pinned-host-manifest'}
        session.builds = SimpleNamespace(run=lambda source: order.append('build') or update)
        session._launch = lambda: order.append('launch-if-needed')
        def rpc(req):
            order.append(req)
            return {'status': 'build_prepared' if req['op'] == 'prepare_sync' else 'ready'}
        session._rpc = rpc
        self.assertEqual(session.request({'op': 'sync'}), {'status': 'ready'})
        self.assertEqual(order, [{'op': 'prepare_sync'}, 'build', 'launch-if-needed', {'op': 'sync', **update}])

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_generation_rejects_wrong_manifest_task_and_replay(self):
        c = self.validate()
        with patch.object(Task, 'validate_inputs'):
            source = self.root / 'source'; prepare(self.task, source)
        builds = SiblingBuilds(self.root, self.task, c)
        update = builds.run(source)
        config = {'native': c, 'operation': 'runtime', 'task_digest': self.task.id,
                  'expected_assertions': ['label'], 'has_reference': False}
        worker = Supervisor(config, self.root)
        root = self.root / 'generations'
        try:
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                worker.accept_generation({**update, 'manifest_sha256': 'wrong'}, root)
            worker.config['task_digest'] = 'another-task'
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                worker.accept_generation(update, root)
            worker.config['task_digest'] = self.task.id
            worker.accept_generation(update, root)
            with self.assertRaisesRegex(ValueError, 'stale'):
                worker.accept_generation(update, root)
        finally:
            worker.journal.close()

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_real_build_interruption_reaps_and_cleans_work(self):
        c = self.validate()
        c['build']['argv'] = ['/bin/sh', '-c', 'sleep 10']
        with patch.object(Task, 'validate_inputs'):
            source = self.root / 'source'; before = prepare(self.task, source)
        builds = SiblingBuilds(self.root, self.task, c)
        real_popen = subprocess.Popen
        children = []
        class InterruptOnce:
            def __init__(self, *a, **kw):
                self.p = real_popen(*a, **kw); children.append(self.p); self.once = True
            def __getattr__(self, name): return getattr(self.p, name)
            def wait(self, *a, **kw):
                if self.once:
                    self.once = False
                    raise KeyboardInterrupt()
                return self.p.wait(*a, **kw)
        with patch('cua_swe_bench.mobile_evaluation.native_backend.subprocess.Popen', InterruptOnce):
            with self.assertRaises(KeyboardInterrupt):
                builds.run(source)
        self.assertIsNotNone(children[0].poll())
        self.assertEqual(tree(source), before)
        self.assertEqual(list((self.root / 'build-work').iterdir()), [])
        receipt = json.loads((self.root / 'build-receipts/00000001.json').read_text())
        self.assertTrue(receipt['cleanup_complete']); self.assertTrue(receipt['infrastructure'])

    def test_pointer_actions_timed_motion_release_and_bounds(self):
        c = self.validate()
        config = {'native': c, 'operation': 'runtime', 'task_digest': self.task.id,
                  'expected_assertions': ['label'], 'has_reference': False}
        worker = Supervisor(config, self.root)
        mouse = SimpleNamespace(move=AsyncMock(), down=AsyncMock(), up=AsyncMock())
        async def screenshot(**kwargs):
            Path(kwargs['path']).write_bytes(b'unit screenshot transport only')
        worker.page = SimpleNamespace(mouse=mouse, screenshot=screenshot)
        worker.ready = True
        try:
            start = time.monotonic()
            asyncio.run(worker.act({'type': 'long_press', 'x': 10, 'y': 20, 'duration_ms': 400}))
            self.assertGreaterEqual(time.monotonic() - start, .39)
            mouse.down.assert_awaited_once(); mouse.up.assert_awaited_once()
            mouse.move.reset_mock(); mouse.up.reset_mock()
            start = time.monotonic()
            asyncio.run(worker.act({'type': 'drag', 'from_x': 10, 'from_y': 20, 'to_x': 300, 'to_y': 200, 'duration_ms': 100}))
            self.assertGreaterEqual(time.monotonic() - start, .09)
            self.assertGreater(mouse.move.await_count, 3)
            self.assertEqual(mouse.move.await_args.args, (300, 200))
            mouse.up.assert_awaited_once()
            mouse.up.reset_mock(); mouse.down.side_effect = RuntimeError('interrupted hold')
            with self.assertRaises(RuntimeError):
                asyncio.run(worker.act({'type': 'long_press', 'x': 10, 'y': 20, 'duration_ms': 400}))
            mouse.up.assert_awaited_once()
            mouse.down.side_effect = None
            mouse.up.reset_mock()
            async def cancel_hold():
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(worker.act({'type': 'long_press', 'x': 10, 'y': 20, 'duration_ms': 400}), .02)
            asyncio.run(cancel_hold())
            mouse.up.assert_awaited_once()
            mouse.up.reset_mock()
            mouse.move.side_effect = [None, None, RuntimeError('motion interrupted')]
            with self.assertRaises(RuntimeError):
                asyncio.run(worker.act({'type': 'drag', 'from_x': 10, 'from_y': 20, 'to_x': 300, 'to_y': 200, 'duration_ms': 100}))
            mouse.up.assert_awaited_once()
            for action in ({'type': 'long_press', 'x': 400, 'y': 20, 'duration_ms': 400},
                           {'type': 'long_press', 'x': 1, 'y': 2, 'duration_ms': 399},
                           {'type': 'drag', 'from_x': 10, 'from_y': 20, 'to_x': 300, 'to_y': 800, 'duration_ms': 100},
                           {'type': 'drag', 'from_x': 10, 'from_y': 20, 'to_x': 30, 'to_y': 80, 'duration_ms': True}):
                with self.assertRaises(ValueError):
                    asyncio.run(worker.act(action))
        finally:
            worker.journal.close()


if __name__ == '__main__':
    run = unittest.main(verbosity=2, exit=False).result
    summary = {'passed': run.wasSuccessful() and not run.skipped,
               'tests_run': run.testsRun, 'failures': [(str(t), msg) for t, msg in run.failures],
               'errors': [(str(t), msg) for t, msg in run.errors],
               'skipped': [(str(t), msg) for t, msg in run.skipped],
               'artifact_root': str(JOB), 'browser_called': False, 'provider_called': False}
    write_json(JOB / 'test-result.json', summary)
    print('TEST_RESULT_JSON=' + str(JOB / 'test-result.json'))
    raise SystemExit(0 if summary['passed'] else 1)
