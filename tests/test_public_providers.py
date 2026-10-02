"""Exercise native wire payloads and the complete tool/image continuation over HTTP."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from provider_client import ProviderClient, ProviderConfig, ProviderError
from provider_relay import relay
from run_evaluation import parser, make_plan, select_tasks

TOOLS = [{'type': 'function', 'name': 'browser', 'description': 'View application',
          'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]
IMAGE = 'data:image/png;base64,aW1hZ2U='


def reply(provider, turn):
    call = turn == 1
    if provider == 'responses':
        return {'id': f'r{turn}', 'status': 'completed', 'model': 'resolved-model',
                'output': [{'type': 'function_call', 'name': 'browser', 'call_id': 'tool1', 'arguments': '{}'}] if call else
                [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Done'}]}],
                'usage': {'input_tokens': 2, 'output_tokens': 3}}
    if provider == 'chat-completions':
        return {'id': f'r{turn}', 'model': 'resolved-model', 'choices': [{'finish_reason': 'tool_calls' if call else 'stop',
                'message': {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'tool1', 'type': 'function', 'function': {'name': 'browser', 'arguments': '{}'}}]} if call else {'role': 'assistant', 'content': 'Done'}}],
                'usage': {'prompt_tokens': 2, 'completion_tokens': 3}}
    if provider == 'anthropic':
        return {'id': f'r{turn}', 'model': 'resolved-model', 'stop_reason': 'tool_use' if call else 'end_turn',
                'content': [{'type': 'tool_use', 'id': 'tool1', 'name': 'browser', 'input': {}}] if call else [{'type': 'text', 'text': 'Done'}], 'usage': {'input_tokens': 2, 'output_tokens': 3}}
    return {'stopReason': 'tool_use' if call else 'end_turn', 'output': {'message': {'role': 'assistant', 'content':
            [{'toolUse': {'toolUseId': 'tool1', 'name': 'browser', 'input': {}}}] if call else [{'text': 'Done'}]}}, 'usage': {'inputTokens': 2, 'outputTokens': 3}}


@contextmanager
def server(provider, status=200):
    records = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            records.append({'path': self.path, 'headers': dict(self.headers), 'body': body})
            self.send_response(status); self.send_header('x-request-id', f'req{len(records)}'); self.end_headers()
            self.wfile.write(json.dumps(reply(provider, len(records))).encode())
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{http.server_port}', records
    finally: http.shutdown(); http.server_close(); thread.join()


@pytest.mark.parametrize('provider', ['responses', 'chat-completions', 'anthropic', 'bedrock'])
def test_real_http_multiturn_tool_and_screenshot(provider, tmp_path):
    with server(provider) as (url, records):
        config = ProviderConfig(provider, 'model/alias', url, region='test-region-1')
        # The same relay used by actual TaskBundle jobs keeps the key outside the agent.
        with relay(config, 'test-secret') as (local, lease_token):
            assert local.api_key_env == 'CUA_SWE_GATEWAY_TOKEN'
            client = ProviderClient(local, TOOLS, token=lease_token, trace_dir=tmp_path)
            first = client.create([{'role': 'user', 'content': 'Please inspect the application'}])
            assert first['output'][0]['call_id'] == 'tool1'
            second = client.create([
                {'type': 'function_call_output', 'call_id': 'tool1', 'output': 'screenshot'},
                {'role': 'user', 'content': [{'type': 'input_image', 'image_url': IMAGE}]}], previous_response_id=first['id'])
    assert second['usage']['input_tokens'] == 2
    assert second['usage']['output_tokens'] == 3
    assert second['model'] == 'model/alias'
    assert second['output'][0]['content'][0]['text'] == 'Done'
    assert len(records) == 2
    body = records[1]['body']
    if provider == 'responses':
        assert body['input'][1]['call_id'] == 'tool1'
        assert body['input'][-1]['content'][0]['image_url'] == IMAGE
    elif provider == 'chat-completions':
        assert body['messages'][2] == {'role': 'tool', 'tool_call_id': 'tool1', 'content': 'screenshot'}
        assert body['messages'][-1]['content'][0]['image_url']['url'] == IMAGE
    elif provider == 'anthropic':
        assert body['messages'][-1]['content'][0]['tool_use_id'] == 'tool1'
        assert body['messages'][-1]['content'][1]['source']['data'] == 'aW1hZ2U='
        assert records[0]['headers']['x-api-key'] == 'test-secret'
    else:
        assert records[0]['path'] == '/model/model%2Falias/converse'
        assert body['messages'][-1]['content'][0]['toolResult']['toolUseId'] == 'tool1'
        assert body['messages'][-1]['content'][1]['image']['source']['bytes'] == 'aW1hZ2U='
    if provider != 'anthropic':
        assert records[0]['headers']['Authorization'] == 'Bearer test-secret'
    traces = ''.join(p.read_text() for p in tmp_path.glob('*.json'))
    assert 'test-secret' not in traces and lease_token not in traces


def test_openai_token_parameter_survives_relay():
    config = ProviderConfig('chat-completions', 'example', 'https://api.openai.com/v1')
    with relay(config, 'test-secret') as (local, lease_token):
        payload = ProviderClient(local, TOOLS, token=lease_token)._payload()
        assert 'max_completion_tokens' in payload and 'max_tokens' not in payload


@pytest.mark.parametrize('status', [302, 401, 429, 500])
def test_error_has_no_retry_or_credentials(status):
    with server('responses', status) as (url, records):
        client = ProviderClient(ProviderConfig('responses', 'example', url), TOOLS, token='test-secret')
        with pytest.raises(ProviderError, match=f'HTTP {status}'):
            client.create([{'role': 'user', 'content': 'go'}])
    assert len(records) == 1


def test_wrong_continuation_does_not_send_request():
    with server('responses') as (url, records):
        client = ProviderClient(ProviderConfig('responses', 'example', url, 'NONE'), TOOLS)
        first = client.create([{'role': 'user', 'content': 'go'}])
        with pytest.raises(ProviderError, match='tool results'):
            client.create([{'role': 'user', 'content': 'skip tool'}], previous_response_id=first['id'])
        with pytest.raises(ProviderError, match='continuation'):
            client.create([], previous_response_id='wrong')
    assert len(records) == 1


@pytest.mark.parametrize('domain,count', [('web',36), ('game',29), ('mobile',20), ('devops',20)])
def test_plans_select_release_manifest_without_credentials(domain, count, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    args = parser().parse_args(['plan', '--domain', domain, '--scope', 'full', '--provider', 'responses', '--model', 'new-model'])
    plan = make_plan(args)
    assert plan['task_count'] == count
    assert select_tasks(domain, 'gate')[0] == plan['tasks'][:10]
    selected = plan['tasks'][-1]
    assert select_tasks(domain, 'gate', [selected['task_id']])[0] == [selected]
    with pytest.raises(ValueError, match='absent'):
        select_tasks(domain, 'full', ['invented-task'])


@pytest.mark.parametrize('domain', ['web', 'game', 'devops'])
@pytest.mark.parametrize('condition', ['cua', 'code-only'])
def test_taskbundle_isolated_packet_and_real_parser(domain, condition, tmp_path):
    # Frozen Web imports require a fresh process.
    code = '''
import json, sys
from pathlib import Path
from run_evaluation import parser, make_plan
from public_taskbundle import load_harness, install, runner_args
args = parser().parse_args(['plan', '--domain', sys.argv[1], '--provider', 'responses', '--model', 'new-model', '--condition', sys.argv[2], '--output-root', sys.argv[3]])
plan = make_plan(args)
h = load_harness(args.domain)
base = h._evaluation_harness_digest()
import os
os.environ['CUA_SWE_PROVIDER_CONFIG'] = '{"provider": "responses"}'
os.environ['CUA_SWE_GATEWAY_TOKEN'] = 'lease-fixture-token'
identity = install(h, plan)
assert 'CUA_SWE_GATEWAY_TOKEN' not in os.environ and 'CUA_SWE_PROVIDER_CONFIG' not in os.environ
with h._provider_lease('responses', 'new-model') as lease_env:
    assert lease_env == {'CUA_SWE_PROVIDER_CONFIG': '{"provider": "responses"}', 'CUA_SWE_GATEWAY_TOKEN': 'lease-fixture-token'}
    assert h.run_agent_command('echo "$CUA_SWE_GATEWAY_TOKEN"', cwd=Path(sys.argv[3]), timeout_sec=10, lease_environment=lease_env).stdout.strip() == 'lease-fixture-token'
assert h._require_provider_route('responses') == 'responses'
p = h._copy_isolated_tools(Path(sys.argv[3]), args.condition, 'responses')
assert set(h._expected_tool_names(args.condition, 'responses')) == {x.name for x in p.iterdir()}
assert 'ProviderClient' in (p / 'run_responses_agent.py').read_text()
assert h._evaluation_harness_digest() != base
assert h._tool_source_digest(p.parent) == h._expected_tool_packet_digest(args.condition, 'responses')
sys.argv = runner_args(plan)
parsed = h.parse_args()
assert h.selected_models(parsed)[0].model_id == 'new-model'
assert len(h.selected_task_inputs(parsed)) == 10
'''
    proc = subprocess.run([sys.executable, '-c', code, domain, condition, str(tmp_path)],
                          env={**__import__('os').environ, 'PYTHONPATH': str(ROOT / 'scripts')}, cwd=ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_mobile_runtime_rebinding_preserves_released_sources(tmp_path):
    from public_mobile import materialize_task
    from cua_swe_bench.mobile_evaluation.core import digest, sha
    row = select_tasks('mobile', 'full')[0][0]
    original = json.loads((ROOT / row['task_file']).read_text())
    task = materialize_task(row, tmp_path / 'task', 'local-browser-sha')
    assert task.c['backend']['browser_sha256'] == 'local-browser-sha'
    assert task.c['editable'] == original['editable']
    for name, ref in task.c['public_files'].items():
        assert ref['sha256'] == original['public_files'][name]['sha256'] == sha(ref['path'])
    for ref in task.c['controls'].values():
        patch = json.loads(Path(ref['patch']['path']).read_text())
        assert patch['task_digest'] == task.id
        assert ref['patch']['sha256'] == sha(ref['patch']['path'])
    lineage = json.loads((tmp_path / 'task/lineage.json').read_text())
    assert lineage['evaluated_task_digest'] == row['evaluated_task_digest']
    assert lineage['runtime_task_digest'] == task.id


def test_mobile_selected_protocol_and_factory(monkeypatch, tmp_path):
    # Isolate global protocol bindings changed by the extension.
    code = '''
import json, os, sys
from pathlib import Path
from run_evaluation import parser, make_plan
from public_mobile import install
from cua_swe_bench.mobile_evaluation import agent, admission, core, runner
args = parser().parse_args(['plan', '--domain', 'mobile', '--provider', 'anthropic', '--model', 'new-model'])
plan = make_plan(args)
plan['output_root'] = sys.argv[1]
os.environ['CUA_SWE_PROVIDER_TOKEN'] = 'fixture-token'
factory = install(plan)
protocol = runner.Protocol()
assert protocol.model == 'new-model' and protocol.provider == 'anthropic'
assert protocol.responses == 60 and protocol.active_seconds == 2700
assert agent.Protocol() == admission.Protocol() == protocol
client = factory(protocol, [agent.SHELL, agent.FINISH, agent.BROWSER], Path(sys.argv[1]))
assert client.token == 'fixture-token'
assert 'CUA_SWE_PROVIDER_TOKEN' not in os.environ
assert client.config.model == 'new-model'
'''
    proc = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                          env={**__import__('os').environ, 'PYTHONPATH': str(ROOT / 'scripts')}, cwd=ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_planner_rejects_unsupported_parallelism():
    for domain in ('mobile', 'devops'):
        args = parser().parse_args(['plan', '--domain', domain, '--provider', 'responses', '--model', 'x', '--max-workers', '2'])
        with pytest.raises(ValueError, match='max-workers 1'):
            make_plan(args)


def test_terminal_notice_preserves_real_post_exit_actions():
    from types import SimpleNamespace
    from public_taskbundle import terminal_notice_errors
    h = SimpleNamespace(_strace_pid=lambda s: s.split(' ', 1)[0],
                        _strace_body=lambda s: s.split(' ', 1)[1])
    error = 'PID 10 produced events after exit'
    trace = SimpleNamespace(lines=('10 exit_group(0) = ?', '10 +++ killed by SIGKILL +++'),
                            audit_errors=(error, 'other integrity error'))
    assert terminal_notice_errors(trace, h) == ('other integrity error',)
    trace.lines += ('10 execve("/bin/sh", ["sh"], []) = 0',)
    assert terminal_notice_errors(trace, h) == (error, 'other integrity error')
