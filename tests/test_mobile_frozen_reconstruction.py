"""Local construction controls, deliberately no provider calls and no native app certification."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import pytest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cua_swe_bench.mobile_evaluation.core import Fault, Protocol, Task, PYTHON, digest, evidence, harness_identity, sha, tree, write_json
from cua_swe_bench.mobile_evaluation.workspace import prepare, extract, apply, prepare_git_metadata
from cua_swe_bench.mobile_evaluation.sandbox import Sandbox
from cua_swe_bench.mobile_evaluation.grading import capture, grade, interpret, controls
from cua_swe_bench.mobile_evaluation.agent import Agent
from cua_swe_bench.mobile_evaluation.browser import PixelRuntime, action_valid
from cua_swe_bench.mobile_evaluation.admission import aggregate, classify, append_ledger, ledger_attempts, validate_evidence
from cua_swe_bench.mobile_evaluation.synthetic import fixture, ScriptedClient, preflight

ROOT = Path(tempfile.mkdtemp(prefix='mobile-reconstruction-tests-')).resolve()

def healthy():
    return dict.fromkeys(('instruction', 'source', 'shell_before', 'shell_after', 'runtime_before', 'grader_controls', 'baseline'), True)

def agent_state(correct=False, used=False):
    return {'responses': 1, 'termination': 'submitted', 'returned_models': [Protocol().model], 'faults': [], 'images_delivered': [{}] if used else []}

class LocalControls(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / self._testMethodName
        self.root.mkdir()
        self.task = fixture(self.root / 'fixture')

    def source(self):
        root = self.root / 'source'
        return root, prepare(self.task, root)

    def test_protocol_frozen(self):
        p = Protocol()
        self.assertEqual((p.model, p.provider, p.responses, p.active_seconds, p.reasoning, p.max_output_tokens, p.transport_attempts),
                         ('gpt-6-astra', 'responses', 60, 2700, 'high', 16384, 1))
        self.assertEqual(digest(p.record()), digest(Protocol().record()))
        self.assertEqual(p.request_timeout_seconds, 600)

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_git_status_and_diff_with_metadata_excluded_from_submission(self):
        src, baseline = self.source()
        record = prepare_git_metadata(src, self.root / 'git-metadata')
        sb = Sandbox(src, git_metadata=record['metadata_path'])
        result = sb.shell("git status --porcelain; printf '2\\n' > value.txt; git diff -- value.txt",
                          record=self.root / 'git-shell.json')
        self.assertEqual(result['returncode'], 0, result['stderr'])
        self.assertIn('-0', result['stdout'])
        self.assertIn('+2', result['stdout'])
        repair = extract(self.task, baseline, src)
        self.assertEqual([c['path'] for c in repair['changes']], ['value.txt'])
        self.assertEqual(list((src / '.git').iterdir()), [])

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_shell_actual_read_write_namespace_and_denied_access(self):
        src, baseline = self.source()
        sb = Sandbox(src)
        r = sb.control(baseline, self.root / 'health.json')
        self.assertEqual(set(r['source_read']), set(baseline))
        self.assertTrue(r['protected_absent'])
        result = sb.shell("printf '2\\n' > value.txt; test ! -e /protected; test ! -e /efs; test ! -e /home", record=self.root / 'tool.json')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual((src / 'value.txt').read_text(), '2\n')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_large_public_tree_health_reads_every_file_without_argv_limit(self):
        src, _ = self.source()
        context = src / 'ordinary-context'
        context.mkdir()
        for i in range(1800):
            (context / f'component-{i:05d}-with-realistic-public-source-name.txt').write_text(f'public source {i}\n')
        baseline = tree(src)
        self.assertGreater(len(repr({n: v['sha256'] for n, v in baseline.items()})), 128 * 1024)
        sb = Sandbox(src, read_only_files=[n for n in baseline if n != 'value.txt'])
        health = sb.control(baseline, self.root / 'large-tree-health.json')
        self.assertEqual(health['source_read'], {n: v['sha256'] for n, v in baseline.items()})
        self.assertFalse((src / '.harness-control').exists())
        changed = context / 'component-00999-with-realistic-public-source-name.txt'
        changed.write_text('changed after baseline\n')
        with self.assertRaises(Fault):
            sb.control(baseline, self.root / 'large-tree-drift.json')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_large_readonly_tree_preserves_new_edit_paths_and_blocks_source_writes(self):
        src, _ = self.source()
        for i in range(5000):
            p = src / 'app-context' / f'part-{i // 250:02d}' / f'component-{i:05d}.txt'
            p.parent.mkdir(exist_ok=True, parents=True)
            p.write_text(f'ordinary source {i}\n')
        baseline = tree(src)
        git = prepare_git_metadata(src, self.root / 'git-metadata')
        sb = Sandbox(src, read_only_files=[n for n in baseline if n != 'value.txt'],
                     writable_paths=['value.txt', 'app-context/new-components/', 'dist/'],
                     git_metadata=git['metadata_path'])
        health = sb.control(baseline, self.root / 'large-mount-health.json')
        self.assertEqual(set(health['source_read']), set(baseline))
        r = sb.shell("mkdir -p app-context/new-components dist; "
                     "printf new > app-context/new-components/new.txt; "
                     "printf build > dist/result; printf '2\\n' > value.txt; "
                     "git diff -- value.txt", record=self.root / 'permitted-new-path.json')
        self.assertEqual(r['returncode'], 0, r['stderr'])
        self.assertIn('+2', r['stdout'])
        self.assertEqual((src / 'app-context/new-components/new.txt').read_text(), 'new')
        r = sb.shell("printf tamper > app-context/part-10/component-02501.txt",
                     record=self.root / 'readonly-subtree-write.json')
        self.assertNotEqual(r['returncode'], 0)
        self.assertEqual((src / 'app-context/part-10/component-02501.txt').read_text(), 'ordinary source 2501\n')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_noneditable_source_and_instruction_readonly_but_readable(self):
        src,baseline=self.source()
        sb=Sandbox(src,read_only_files=['context.txt'])
        r=sb.shell('cat context.txt; printf tamper > context.txt',record=self.root/'readonly-source.json')
        self.assertNotEqual(r['returncode'],0)
        self.assertTrue(r['stdout'].startswith('Ordinary public context'))
        r=sb.shell('printf tamper > TASK.md',record=self.root/'readonly-task.json')
        self.assertNotEqual(r['returncode'],0)
        self.assertEqual(tree(src),baseline)

    def test_sandbox_hidden_failure_with_exit_zero(self):
        src, baseline = self.source()
        fake = self.root / 'fake-bwrap'
        fake.write_text('#!/bin/sh\necho "bwrap: cannot mkdir /workspace/.git" >&2\nexit 0\n'); fake.chmod(0o755)
        with self.assertRaises(Fault) as caught:
            Sandbox(src, bwrap=str(fake)).shell('true', record=self.root / 'hidden-zero.json')
        self.assertEqual(caught.exception.category, 'sandbox')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_normal_shell_error_is_not_sandbox_error(self):
        src, baseline = self.source()
        result = Sandbox(src).shell('exit 7', record=self.root / 'ordinary-error.json')
        self.assertEqual(result['returncode'], 7)
        self.assertTrue(result['completed'])

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_shell_timeout_and_child_cleanup(self):
        src, _ = self.source()
        result = Sandbox(src).shell('sleep 20 & wait', timeout=1, record=self.root / 'timeout.json')
        self.assertTrue(result['timed_out'])

    def test_add_delete_mode_and_binary_patch_roundtrip(self):
        src, baseline = self.source()
        (src / 'value.txt').unlink()
        (src / 'added').mkdir(); (src / 'added/binary').write_bytes(b'\x00\xffabc'); (src / 'added/binary').chmod(0o755)
        repair = extract(self.task, baseline, src)
        destination = self.root / 'clean'; prepare(self.task, destination)
        apply(self.task, baseline, repair, destination)
        self.assertEqual(tree(src), tree(destination))
        self.assertEqual(len(repair['changes']), 2)

    def test_protected_edits_symlinks_hardlinks_and_traversal_rejected(self):
        src, baseline = self.source()
        (src / 'context.txt').write_text('tamper')
        with self.assertRaises(Fault): extract(self.task, baseline, src)
        (src / 'context.txt').write_text('Ordinary public context, retained outside edit boundary.\n')
        (src / 'added').mkdir(); (src / 'added/escape').symlink_to('/etc/passwd')
        with self.assertRaises(Fault): extract(self.task, baseline, src)
        (src / 'added/escape').unlink(); os.link(src / 'value.txt', src / 'added/link')
        with self.assertRaises(Fault): extract(self.task, baseline, src)
        cfg = copy.deepcopy(self.task.c); cfg['public_files']['../escape'] = cfg['public_files']['value.txt']
        with self.assertRaises(Fault): Task(cfg)

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_dependency_symlink_escape_rejected_and_readonly_bind(self):
        dep = self.root / 'deps'; dep.mkdir(); (dep / 'readme').write_text('public')
        (dep / 'ok').symlink_to('readme')
        cfg = copy.deepcopy(self.task.c); cfg['dependencies'] = [{'path': str(dep), 'destination': 'node_modules', 'sha256': digest(tree(dep, dependency=True))}]
        task = Task(cfg); src = self.root / 'with-deps'; baseline = prepare(task, src)
        result = Sandbox(src, task.c['dependencies']).shell('cat node_modules/ok; echo tamper > node_modules/readme', record=self.root / 'dependency.json')
        self.assertNotEqual(result['returncode'], 0); self.assertEqual((dep / 'readme').read_text(), 'public')
        (dep / 'escape').symlink_to('/home')
        with self.assertRaises(Fault): tree(dep, dependency=True)

    def test_generated_build_scratch_not_patch_or_scope(self):
        src, baseline = self.source()
        (src / 'dist').mkdir(); (src / 'dist/out.js').write_text('generated')
        self.assertEqual(extract(self.task, baseline, src)['changes'], [])

    def test_missing_instruction_and_source_not_model_failure(self):
        cfg = copy.deepcopy(self.task.c); cfg['instruction']['path'] = str(self.root / 'missing.md')
        with self.assertRaises(Fault) as c: prepare(Task(cfg), self.root / 'absent')
        self.assertEqual(c.exception.category, 'missing_instruction')
        cfg = copy.deepcopy(self.task.c); cfg['public_files']['value.txt']['sha256'] = '0' * 64
        with self.assertRaises(Fault) as c: prepare(Task(cfg), self.root / 'changed')
        self.assertEqual(c.exception.category, 'source')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_baseline_capture_precedes_candidate_edits(self):
        baseline, reference = capture(self.task, self.root / 'capture')
        src, _ = self.source(); (src / 'value.txt').write_text('2\n')
        patch_ = extract(self.task, baseline, src)
        result = grade(self.task, baseline, patch_, reference, self.root / 'grade')
        self.assertTrue(result['correct'])
        self.assertEqual(json.loads((reference / 'baseline.json').read_text())['state']['broken_value'], 0)
        (reference / 'baseline.json').unlink()
        with self.assertRaises(Fault) as c: grade(self.task, baseline, patch_, reference, self.root / 'missing')
        self.assertEqual(c.exception.category, 'baseline')

    def test_153_cannot_skip_capture(self):
        cfg = copy.deepcopy(self.task.c); cfg['task_id'] = 'audit-mobile-153'; del cfg['backend']['capture']
        with self.assertRaises(Fault) as c: Task(cfg).validate_inputs()
        self.assertEqual(c.exception.category, 'baseline')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_broken_gold_alternative_partial_clean_controls(self):
        _, _, r = controls(self.task, self.root / 'controls')
        self.assertTrue(r['passed'])
        self.assertEqual({n: x['correct'] for n, x in r['outcomes'].items()}, {'broken': False, 'gold': True, 'alternative': True, 'partial': False})

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_candidate_syntax_error_is_failure_after_healthy_controls(self):
        baseline, reference, r = controls(self.task, self.root / 'controls')
        src, _ = self.source(); (src / 'value.txt').write_text('syntax-error\n')
        v = grade(self.task, baseline, extract(self.task, baseline, src), reference, self.root / 'syntax')
        result = classify(agent_state(), v, healthy())
        self.assertEqual(result['classification'], 'valid_model_failure')
        self.assertEqual(v['candidate_error']['kind'], 'syntax')
        self.assertIn('replay', v)

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_verifier_exception_exit_zero_invalid(self):
        private = self.root / 'bad-verifier'; private.mkdir()
        (private / 'bad.py').write_text("import pathlib,json; pathlib.Path('/artifacts/result.json').write_text(json.dumps({'execution':'complete','errors':['injected verifier exception'],'expected_assertions':['square','context'],'assertions':[]}))")
        cfg = copy.deepcopy(self.task.c); cfg['backend']['protected'] = {'path': str(private), 'sha256': digest(tree(private))}; cfg['backend']['grade'] = [PYTHON, '-I', '/protected/bad.py']; cfg['backend'].pop('capture')
        task = Task(cfg); baseline, reference = capture(task, self.root / 'capture')
        empty = {'task_digest': task.id, 'baseline_digest': digest(baseline), 'changes': []}
        with self.assertRaises(Fault) as c: grade(task, baseline, empty, reference, self.root / 'grade')
        self.assertEqual(c.exception.category, 'grader')
        process = json.loads((self.root / 'grade/first/verifier/process.json').read_text())
        self.assertEqual(process['returncode'], 0)

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_exception_in_stderr_with_nominal_json_exit_zero_invalid(self):
        private = self.root / 'bad-verifier'; private.mkdir()
        (private / 'bad.py').write_text("import pathlib,json,sys; print('Traceback (most recent call last):',file=sys.stderr); pathlib.Path('/artifacts/result.json').write_text(json.dumps({'execution':'complete','errors':[],'expected_assertions':['square','context'],'assertions':[{'id':'square','passed':True},{'id':'context','passed':True}]}))")
        cfg = copy.deepcopy(self.task.c); cfg['backend']['protected'] = {'path': str(private), 'sha256': digest(tree(private))}; cfg['backend']['grade'] = [PYTHON, '-I', '/protected/bad.py']; cfg['backend'].pop('capture')
        task=Task(cfg); baseline,reference=capture(task,self.root/'baseline')
        empty={'task_digest':task.id,'baseline_digest':digest(baseline),'changes':[]}
        with self.assertRaises(Fault) as c: grade(task,baseline,empty,reference,self.root/'grade')
        self.assertEqual(c.exception.category,'grader')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_private_runtime_logs_never_reach_solver_requests(self):
        src,baseline=self.source()
        class Runtime:
            def sync(self, patch): return {'status':'ready', 'readiness':{'stdout':'SECRET_PRIVATE_RUNTIME_TEXT'}}
        client=ScriptedClient()
        a=Agent(self.task,baseline,Sandbox(src),Runtime(),'code-only',self.root/'agent',lambda *args:client).run()
        self.assertEqual(a['termination'],'submitted')
        self.assertNotIn('SECRET_PRIVATE_RUNTIME_TEXT',json.dumps(client.inputs))

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_no_missing_screenshot_attachment_in_evidence_validation(self):
        r=preflight(self.root/'preflight')
        a=json.loads(Path(r['controls']['cua']['attempt']['path']).read_text())
        self.assertTrue(validate_evidence(a))
        # Corrupt association without inventing valid evidence from a normal exit.
        a['agent']['images_delivered'][0]['request']=a['agent']['requests'][0]['request']
        self.assertFalse(validate_evidence(a))

    def test_assertion_semantics_not_returncodes(self):
        raw = {'execution': 'complete', 'errors': [], 'expected_assertions': ['a', 'b'], 'assertions': [{'id': 'a', 'passed': True}, {'id': 'b', 'passed': False}]}
        self.assertFalse(interpret(raw, ['a', 'b'])['correct'])
        raw['assertions'][1]['passed'] = True; self.assertTrue(interpret(raw, ['a', 'b'])['correct'])
        for bad in ('false', 0, None):
            raw['assertions'][1]['passed'] = bad
            with self.assertRaises(Fault): interpret(raw, ['a', 'b'])
        raw['assertions'] = [{'id': 'a', 'passed': True}]*2
        with self.assertRaises(Fault): interpret(raw, ['a', 'b'])

    def test_classification_empty_caps_nonuse_and_scope(self):
        a = agent_state(); a['termination'] = 'response_cap'
        self.assertEqual(classify(a, {'correct': False}, healthy())['classification'], 'valid_model_failure')
        a['termination'] = 'time_cap'
        self.assertEqual(classify(a, {'correct': False}, healthy())['classification'], 'valid_model_failure')
        h = healthy(); h['shell_before'] = False
        self.assertFalse(classify(a, {'correct': False}, h)['scorable'])
        self.assertEqual(classify(a, {'correct': False}, healthy(), [{'category': 'scope'}])['classification'], 'scope_violation')
        self.assertTrue(classify(a, {'correct': True}, healthy())['success_without_cua'])
        for cause in ('sandbox','source','provider','missing_instruction','image_delivery','grader','runtime'):
            self.assertEqual(classify(a, {'correct': False}, healthy(), [{'category': cause}])['classification'], 'infrastructure_interface_invalid')

    def test_transport_trace_full_body_single_call_no_redirect_or_auth_log(self):
        from cua_swe_bench.mobile_evaluation.agent import TraceHTTP
        class HTTP:
            RequestException=RuntimeError
            def __init__(self): self.calls=0
            def post(self,url,**kwargs):
                self.calls+=1
                assert kwargs['allow_redirects'] is False
                class Response:
                    status_code=503
                    headers={'x-request-id':'local-stub','authorization':'MUST_NOT_LOG'}
                    text='full-error-'+'x'*5000
                return Response()
        http=HTTP(); trace=TraceHTTP(http,self.root/'trace')
        trace.post('https://synthetic.invalid',data=b'{"model":"synthetic-only"}',headers={'Authorization':'MUST_NOT_LOG'},timeout=1)
        self.assertEqual(http.calls,1)
        r=json.loads((self.root/'trace/wire-001-response.json').read_text())
        self.assertEqual(len(r['body']),5011)
        self.assertNotIn('MUST_NOT_LOG', ''.join(p.read_text() for p in (self.root/'trace').glob('*.json')))

    def test_one_provider_attempt_and_wrong_returned_model(self):
        src, baseline = self.source()
        for failure, category in [('provider', 'provider'), ('wrong_model', 'wrong_model')]:
            client = ScriptedClient(failure=failure)
            a = Agent(self.task, baseline, Sandbox(src), None, 'code-only', self.root / failure, lambda *args: client).run()
            self.assertEqual(a['faults'][0]['category'], category); self.assertEqual(client.calls, 1)

    def test_missing_image_invalid_not_model_failure(self):
        src, baseline = self.source()
        class MissingImage:
            def act(self, action): return None
        client = ScriptedClient('cua')
        a = Agent(self.task, baseline, Sandbox(src), MissingImage(), 'cua', self.root / 'agent', lambda *args: client).run()
        self.assertEqual(a['faults'][0]['category'], 'image_delivery')

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_pixel_bridge_only_actions_sync_and_preservation(self):
        src, baseline = self.source()
        runtime = PixelRuntime(self.task, self.root / 'runtime', baseline)
        try:
            self.assertTrue(Path(runtime.control_image['evidence']['path']).is_file())
            for action in ({'type':'evaluate','script':'document.body'}, {'type':'click','selector':'body'}, {'type':'screenshot','url':'http://elsewhere'}, {'type':'press','key':'Ctrl+L'}):
                self.assertFalse(action_valid(action))
                with self.assertRaises(ValueError): runtime.act(action)
            (src / 'value.txt').write_text('-2\n'); (src / 'added').mkdir(); (src / 'added/a').write_text('added')
            runtime.sync(extract(self.task, baseline, src))
            self.assertEqual((runtime.workspace / 'value.txt').read_text(), '-2\n')
            self.assertTrue((runtime.workspace / 'added/a').exists())
            (src / 'added/a').unlink(); runtime.sync(extract(self.task, baseline, src))
            self.assertFalse((runtime.workspace / 'added/a').exists())
        finally: runtime.close()
        self.assertIsNotNone(runtime.p.poll())

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_full_no_paid_preflight_and_artifact_integrity(self):
        r = preflight(self.root / 'preflight')
        self.assertTrue(r['passed']); self.assertFalse(r['provider_called'])
        for condition in ('code-only', 'cua'):
            a = json.loads(Path(r['controls'][condition]['attempt']['path']).read_text())
            self.assertTrue(validate_evidence(a))
            if condition == 'cua':
                self.assertEqual(len(a['agent']['images_delivered']), 1)
                delivery = a['agent']['images_delivered'][0]
                req = json.loads(Path(delivery['request']['path']).read_text())
                image = [c for x in req['input'] for c in x.get('content', []) if c.get('type')=='input_image'][0]
                self.assertEqual(base64.b64decode(image['image_url'].split(',')[1]), Path(delivery['image']['path']).read_bytes())
        ledger = self.root / 'ledger.jsonl'
        ref = r['controls']['cua']['attempt']; append_ledger(ledger, ref)
        self.assertEqual(len(ledger_attempts(ledger)), 1)
        with self.assertRaises(Fault): append_ledger(ledger, ref)
        a = ledger_attempts(ledger)[0]
        Path(a['agent']['requests'][0]['request']['path']).write_text('{}')
        self.assertFalse(validate_evidence(a))

# Strict aggregation mechanics are unit fixtures, not actual admission records.
class AdmissionControls(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / self._testMethodName; self.root.mkdir()
        self.task = fixture(self.root / 'fixture')
        self.note = self.root / 'UNIT-TEST-ONLY.txt'; self.note.write_text('Fabricated admission unit fixtures; not task evidence.')
        self.ref = evidence(self.note)

    def history(self, band):
        identity = {'UNIT_TEST_ONLY': 'no-admission-evidence'}
        attempts = []
        for phase, slots in [('development', [1]), ('confirmation', [1,2,3])]:
            for condition in ('code-only', 'cua'):
                for slot in slots:
                    correct = condition == 'cua' and phase == 'confirmation' and slot <= band
                    agent = agent_state(used=condition=='cua')
                    a = {'attempt_id': f'{phase}-{condition}-{slot}', 'session_id': f'session-{phase}-{condition}-{slot}', 'phase': phase, 'condition':condition, 'slot':slot,
                         'identity': identity, 'synthetic':False, 'protocol': Protocol().record(), 'health':healthy(), 'grade':{'correct':correct}, 'agent':agent,
                         'classification':classify(agent, {'correct':correct}, healthy()), 'artifacts':[self.ref], '_ref':self.ref}
                    attempts.append(a)
        gates = ('deterministic_controls provenance custody source_context_complete pixel_only_isolation harness_controls independent_classification_review complete_revision_history task_soundness diagnostic_evidence_accessible gold_stability verifier_fairness budget_opportunity instruction_complete').split()
        review = {'identity':identity, 'gates':dict.fromkeys(gates, True), 'evidence':[self.ref], 'attempts':{a['attempt_id']:{'result':self.ref,'classification_validated':True,'scope_clean':True,'evidence':[self.ref],'grounded_cua_repair':True} for a in attempts}}
        return attempts, review

    def aggregate_unit(self, attempts, review):
        # Evidence validator is separately integration-tested above; these fabricated unit records cannot pass it.
        with patch('cua_swe_bench.mobile_evaluation.admission.validate_evidence', return_value=True):
            return aggregate(attempts, review)

    def test_all_cua_bands_including_zero_admitted(self):
        for band in range(4):
            a,r = self.history(band); result = self.aggregate_unit(a,r)
            self.assertTrue(result['admitted'], result)
            self.assertEqual(result['cua_band'], f'{band}/3')
            self.assertEqual(result['role'], 'upper_anchor' if band==0 else 'lower_anchor')

    def test_wrong_model_mixed_revisions_duplicates_invalid_and_missing_evidence(self):
        for kind in ('wrong_model','mixed','duplicate','invalid','missing_review','missing_trial','missing_development','synthetic'):
            a,r = self.history(1)
            if kind=='wrong_model': a[0]['agent']['returned_models']=['other']
            elif kind=='mixed': a[0]['identity']={'different':'revision'}
            elif kind=='duplicate': a.append(copy.deepcopy(a[-1]))
            elif kind=='invalid': a[-1]['classification']=classify({},None,{})
            elif kind=='missing_review': r['gates'].pop('task_soundness')
            elif kind=='missing_trial': a.pop()
            elif kind=='missing_development': a=a[2:]
            else: a[-1]['synthetic']=True
            self.assertFalse(self.aggregate_unit(a,r)['admitted'], kind)
        a,r=self.history(1)
        self.assertFalse(aggregate(a,r)['admitted'], 'fabricated unit evidence must fail real validator')

    def test_success_without_cua_in_development_or_cua_disqualifies(self):
        for index in (0, 1, -1):
            a,r=self.history(0); trial=a[index]
            trial['agent']=agent_state(used=False); trial['grade']={'correct':True}; trial['classification']=classify(trial['agent'],trial['grade'],healthy())
            result=self.aggregate_unit(a,r)
            self.assertFalse(result['admitted']); self.assertIn('success_without_visual_observation',result['reasons'])

    def test_valid_retries_and_ungrounded_cua_success_rejected(self):
        a,r=self.history(3); duplicate=copy.deepcopy(a[-1]); duplicate['attempt_id']='retry'; duplicate['session_id']='retry-session'; a.append(duplicate)
        result=self.aggregate_unit(a,r)
        self.assertIn('valid_trial_retried',result['reasons'])
        a,r=self.history(1); r['attempts']['confirmation-cua-1']['grounded_cua_repair']=False
        self.assertIn('ungrounded_cua_success',self.aggregate_unit(a,r)['reasons'])

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_dispatch_refuses_unapproved_native_and_valid_retry(self):
        from cua_swe_bench.mobile_evaluation.dispatch import validate_approval,dispatch_lock
        a,r=self.history(0)
        with self.assertRaises(Fault): validate_approval(self.task,self.ref,{})
        trial=a[-1]; trial['identity']={'task_digest':self.task.id}
        ref=write_json(self.root/'existing-attempt.json',trial)
        ledger=self.root/'ledger.jsonl'; append_ledger(ledger,ref)
        with self.assertRaises(Fault):
            with dispatch_lock(ledger,self.task,'confirmation','cua',3): pass

    def test_usability_controls_cannot_enter_admission_or_candidate_phases(self):
        from cua_swe_bench.mobile_evaluation.dispatch import validate_phase
        config = copy.deepcopy(self.task.c)
        config['purpose'] = 'usability-control'
        control = Task(config)
        validate_phase(control, 'usability', 1)
        for task, phase, slot in [(control, 'confirmation', 1), (control, 'development', 1),
                                  (self.task, 'usability', 1), (control, 'usability', 2)]:
            with self.assertRaises(Fault):
                validate_phase(task, phase, slot)
        attempts, review = self.history(0)
        for attempt in attempts:
            attempt['purpose'] = 'usability-control'
        result = self.aggregate_unit(attempts, review)
        self.assertFalse(result['admitted'])
        self.assertIn('usability_control_not_admission', result['reasons'])

    @pytest.mark.skipif(sys.platform != "linux" or not os.environ.get("CUA_MOBILE_CONFIG"),
                        reason="requires the configured Linux Mobile namespace and toolchain")
    def test_fixture_certificate_only_authorizes_explicit_usability_control(self):
        from cua_swe_bench.mobile_evaluation.dispatch import validate_approval
        from cua_swe_bench.mobile_evaluation.core import CLIENT_SHA
        for purpose in ('candidate', 'usability-control'):
            config = copy.deepcopy(self.task.c)
            config['purpose'] = purpose
            task = Task(config)
            expected = {'task_digest': task.id, 'protocol_digest': digest(Protocol().record()),
                        'harness_digest': digest(harness_identity())}
            root = self.root / purpose
            route = write_json(root / 'route.json', {'passed': True, 'model': Protocol().model,
                               'provider': Protocol().provider,
                               'client_sha256': CLIENT_SHA})
            harness = write_json(root / 'harness.json', {'passed': True,
                                 'harness_digest': expected['harness_digest'], 'provider_called': False})
            native = write_json(root / 'native.json', {**expected, 'passed': True,
                                'purpose': purpose, 'native_fixture_certified': True,
                                'native_mobile_certified': False})
            approval = {**expected, 'purpose': purpose, 'approved': True,
                        'route_control': route, 'harness_control': harness, 'native_control': native}
            ref = write_json(root / 'approval.json', approval)
            if purpose == 'candidate':
                with self.assertRaises(Fault):
                    validate_approval(task, ref, approval)
            else:
                self.assertEqual(validate_approval(task, ref, approval), expected)

    def test_scope_violations_are_not_upper_anchor_difficulty(self):
        a,r=self.history(0); a[-1]['classification']=classify(a[-1]['agent'],a[-1]['grade'],healthy(),[{'category':'scope'}])
        self.assertIn('scope_violation_not_difficulty',self.aggregate_unit(a,r)['reasons'])

if __name__ == '__main__':
    print('Retained test artifacts:', ROOT)
    run = unittest.main(verbosity=2, exit=False).result
    summary = {'passed': run.wasSuccessful(), 'tests_run': run.testsRun, 'failures': [(str(t), msg) for t,msg in run.failures], 'errors': [(str(t), msg) for t,msg in run.errors], 'artifact_root': str(ROOT), 'synthetic_only': True}
    write_json(ROOT / 'test-result.json', summary)
    print('TEST_RESULT_JSON=' + str(ROOT / 'test-result.json'))
    raise SystemExit(0 if run.wasSuccessful() else 1)
