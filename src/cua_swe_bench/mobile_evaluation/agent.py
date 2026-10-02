from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import time
from .core import CLIENT, CLIENT_SHA, Fault, Protocol, digest, evidence, sha, write_json
from .workspace import extract

SHELL = {'type': 'function', 'name': 'shell', 'description': 'Run an ordinary source/build/test shell in /workspace. No network, private runtime, grader or host access.',
         'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}, 'timeout_sec': {'type': 'integer', 'minimum': 1, 'maximum': 170}}, 'required': ['command'], 'additionalProperties': False}}
FINISH = {'type': 'function', 'name': 'finish', 'description': 'Submit the current permitted source changes.',
          'parameters': {'type': 'object', 'properties': {'summary': {'type': 'string'}}, 'required': ['summary'], 'additionalProperties': False}}
BROWSER = {'type': 'function', 'name': 'browser', 'description': 'Observe/action the approved app through pixels only. type=screenshot; reload current app without reseeding data; click x,y; long_press x,y,duration_ms (400..2000); drag from_x,from_y,to_x,to_y,duration_ms (100..2000); type text; press key; scroll dx,dy. No URLs, selectors, DOM, HTTP or scripts. Returns screenshot pixels directly.',
           'parameters': {'type': 'object', 'properties': {'action': {'type': 'object', 'properties': {'type': {'type': 'string', 'enum': ['screenshot', 'reload', 'click', 'long_press', 'drag', 'type', 'press', 'scroll']}, 'x': {'type': 'integer'}, 'y': {'type': 'integer'}, 'from_x': {'type': 'integer'}, 'from_y': {'type': 'integer'}, 'to_x': {'type': 'integer'}, 'to_y': {'type': 'integer'}, 'duration_ms': {'type': 'integer'}, 'dx': {'type': 'integer'}, 'dy': {'type': 'integer'}, 'text': {'type': 'string'}, 'key': {'type': 'string'}}, 'required': ['type'], 'additionalProperties': False}}, 'required': ['action'], 'additionalProperties': False}}


class TraceHTTP:
    """Private transport facade: no redirects/retries; preserve full unsigned payload and raw reply.
    Deliberately NEVER records Authorization or API-key request headers.
    """
    def __init__(self, http, root):
        self.http, self.root, self.index = http, Path(root), 0
        self.RequestException = http.RequestException
        self.last_error = None

    def post(self, url, **kwargs):
        self.index += 1
        self.last_error = None
        write_json(self.root / f'wire-{self.index:03}-request.json',
                   {'url': url, 'body': json.loads(kwargs['data']), 'timeout': kwargs.get('timeout'),
                    'transport_attempt': 1, 'allow_redirects': False})
        try:
            response = self.http.post(url, **kwargs, allow_redirects=False)
        except Exception as exc:
            self.last_error = exc
            write_json(self.root / f'wire-{self.index:03}-error.json',
                       {'error': repr(exc), 'error_type': type(exc).__name__,
                        'error_module': type(exc).__module__, 'transport_attempt': 1})
            raise
        headers = {k: v for k, v in response.headers.items() if k.lower() in ('x-request-id', 'request-id', 'content-type')}
        write_json(self.root / f'wire-{self.index:03}-response.json',
                   {'status_code': response.status_code, 'headers': headers, 'body': response.text})
        return response


def responses_client(protocol, tools, root):
    """Only the maintained transport class is imported, explicitly pinned. Never its agent/inventory."""
    if sha(CLIENT) != CLIENT_SHA:
        raise Fault('provider', 'Responses transport digest mismatch')
    from .settings import provider_transport
    # Host-side routing: endpoint and key come from the private runtime config and host environment.
    try:
        transport = provider_transport(getattr(protocol, 'route_id', 'gpt6-astra'), 'responses', protocol.model)
    except Exception as exc:
        raise Fault('provider', f'provider route unavailable: {exc}') from None
    spec = importlib.util.spec_from_file_location('mobile_reconstruction_pinned_responses', CLIENT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.requests = TraceHTTP(module.requests, root)
    client = module.ResponsesClient(model=protocol.model, transport=transport,
                request_timeout_seconds=protocol.request_timeout_seconds, request_attempts=1,
                max_output_tokens=protocol.max_output_tokens, reasoning_effort=protocol.reasoning)
    client.trace_http = module.requests
    client.tools = tools
    client.failure_log_path = Path(root) / 'transport-failures.jsonl'
    return client


def deadline_read_timeout(client, error, timeout, configured_timeout, elapsed, budget):
    """Only a deadline-shortened read timeout at the frozen budget boundary is a cap.

    int(remaining) rounds down by less than one second. A full request timeout,
    an early timeout, and other transport failures remain provider faults.
    The pinned GPT client wraps its transport exception; retain the typed original
    on the private transport facade rather than inspecting exception text.
    """
    if not 0 < timeout < configured_timeout or elapsed < budget - 1:
        return False
    import requests
    trace = getattr(client, 'trace_http', None)
    if trace is None:
        trace = getattr(client, 'http', None)
    transport_error = trace.last_error if isinstance(trace, TraceHTTP) else error
    return isinstance(transport_error, requests.exceptions.ReadTimeout)


class Agent:
    """Identical direct Responses implementation; CUA changes only one function capability."""
    def __init__(self, task, baseline, sandbox, runtime, condition, root, client_factory=responses_client):
        if condition not in ('code-only', 'cua'): raise Fault('configuration', 'unknown condition')
        self.task, self.baseline, self.sandbox, self.runtime = task, baseline, sandbox, runtime
        self.condition, self.root = condition, Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.protocol = Protocol()
        self.tools = [SHELL, FINISH] + ([BROWSER] if condition == 'cua' else [])
        self.factory = client_factory
        self.state = {'responses': 0, 'usage': [], 'requests': [], 'images_created': [], 'images_delivered': [],
                      'tool_seconds': 0.0, 'model_seconds': 0.0, 'termination': None, 'returned_models': [], 'faults': []}

    def run(self):
        start = time.monotonic()
        try:
            self._loop(start)
        except Fault as exc:
            self.state['faults'].append({'category': exc.category, 'message': str(exc)})
            self.state['termination'] = exc.category
        except Exception as exc:
            self.state['faults'].append({'category': 'harness', 'message': repr(exc)})
            self.state['termination'] = 'harness'
        finally:
            self.state['active_seconds'] = time.monotonic() - start
            write_json(self.root / 'agent.json', self.state)
        return self.state

    def _loop(self, start):
        p = self.protocol
        instruction = (self.sandbox.workspace / 'TASK.md').read_text()
        if sha(self.sandbox.workspace / 'TASK.md') != self.task.c['instruction']['sha256']:
            raise Fault('missing_instruction', 'delivered instruction differs from frozen task')
        # Exactly same ordinary instruction/context; tool availability is the only treatment switch.
        prompt = ('Repair the application described below. Public instruction is /workspace/TASK.md. '
                  'Ordinary source, dependencies, and nonvisual builds/tests are available. '
                  'Modify only: ' + json.dumps(self.task.c['editable']) + '. '
                  'Protected verifiers, host files and private runtime interfaces are forbidden. '
                  'If browser is available use only that pixel/action function for runtime observation. '
                  'Use finish to submit. Budget: 60 responses, 45 minutes active time.\n\n' + instruction +
                  '\n\nOrdinary public source contains ' + str(len(self.baseline)) +
                  ' files. Inspect it with shell commands or git ls-files. Top-level paths: ' +
                  ', '.join(sorted({name.split('/')[0] for name in self.baseline})) + '.')
        write_json(self.root / 'prompt.json', {'prompt': prompt, 'instruction_sha256': sha(self.sandbox.workspace / 'TASK.md')})
        items = [{'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}]}]
        pending_images = []
        previous = None
        client = self.factory(p, self.tools, self.root)
        last_patch = digest({'schema': 1, 'task_digest': self.task.id,
                             'baseline_digest': digest(self.baseline), 'changes': []})
        for turn in range(1, p.responses + 1):
            remaining = p.active_seconds - (time.monotonic() - start)
            if remaining <= 0:
                self.state['termination'] = 'time_cap'; return
            # Bound transport by remaining active time as well as the frozen per-request limit.
            client.request_timeout_seconds = max(1, min(p.request_timeout_seconds, int(remaining)))
            request = {'model': p.model, 'input': items, 'previous_response_id': previous,
                       'tools': self.tools, 'tool_choice': 'auto', 'max_output_tokens': p.max_output_tokens,
                       'reasoning': {'effort': p.reasoning}, 'transport_attempts': 1,
                       'timeout_seconds': client.request_timeout_seconds}
            reqref = write_json(self.root / f'{turn:03}-request.json', request)
            before = time.monotonic()
            try:
                response = client.create(items, previous_response_id=previous)
            except Exception as exc:
                elapsed = time.monotonic() - start
                if deadline_read_timeout(client, exc, client.request_timeout_seconds,
                                         p.request_timeout_seconds, elapsed, p.active_seconds):
                    write_json(self.root / f'{turn:03}-deadline.json', {
                        'error': repr(exc), 'request': reqref, 'transport_attempts': 1,
                        'timeout_seconds': client.request_timeout_seconds,
                        'configured_timeout_seconds': p.request_timeout_seconds,
                        'elapsed_seconds': elapsed, 'active_budget_seconds': p.active_seconds,
                        'termination': 'time_cap', 'rounding_tolerance_seconds': 1})
                    self.state['termination'] = 'time_cap'
                    return
                write_json(self.root / f'{turn:03}-provider-error.json', {'error': repr(exc), 'request': reqref, 'transport_attempts': 1})
                raise Fault('provider', f'one transport attempt failed: {exc}') from exc
            finally:
                self.state['model_seconds'] += time.monotonic() - before
            resref = write_json(self.root / f'{turn:03}-response.json', response)
            self.state['requests'].append({'request': reqref, 'response': resref, 'response_id': response.get('id')})
            if response.get('model') != p.model:
                raise Fault('wrong_model', f"returned model {response.get('model')!r}")
            self.state['returned_models'].append(response['model'])
            if response.get('error') or response.get('status') not in ('completed', 'incomplete') or not response.get('id'):
                raise Fault('provider', 'response failed or missing receipt/status')
            if response['status'] == 'incomplete' and response.get('incomplete_details', {}).get('reason') != 'max_output_tokens':
                raise Fault('provider', 'unrecognized incomplete response reason')
            for image in pending_images:
                if not any(c.get('type') == 'input_image' and c.get('image_url') == image['data_url'] for i in items for c in i.get('content', [])):
                    raise Fault('image_delivery', 'screenshot not attached to subsequent request')
                self.state['images_delivered'].append({'image': image['evidence'], 'request': reqref, 'response': resref, 'response_id': response['id']})
            pending_images = []
            previous = response['id']
            self.state['responses'] += 1
            self.state['usage'].append(response.get('usage'))
            output = response.get('output')
            if not isinstance(output, list): raise Fault('provider', 'invalid Responses output schema')
            calls = [x for x in output if x.get('type') == 'function_call']
            if not calls:
                if response['status'] == 'incomplete':
                    items = [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'Continue and submit using finish.'}]}]; continue
                self.state['termination'] = 'submitted'; return
            items = []
            finish = False
            for index, call in enumerate(calls):
                if time.monotonic() - start >= p.active_seconds:
                    self.state['termination'] = 'time_cap'; return
                cid, name = call.get('call_id'), call.get('name')
                if not cid: raise Fault('provider', 'tool call missing call_id')
                before = time.monotonic()
                image = None
                try:
                    args = json.loads(call.get('arguments', '{}'))
                    if not isinstance(args, dict): raise ValueError('tool arguments must be an object')
                    if name == 'shell':
                        if set(args) - {'command', 'timeout_sec'}: raise ValueError('unknown shell argument')
                        timeout = args.get('timeout_sec', 170)
                        if type(timeout) is not int or not 1 <= timeout <= 170: raise ValueError('invalid timeout')
                        timeout = max(1, min(timeout, int(p.active_seconds - (time.monotonic() - start))))
                        result = self.sandbox.shell(args['command'], timeout, self.root / f'{turn:03}-{index:02}-shell.json')
                        patch = extract(self.task, self.baseline, self.sandbox.workspace)
                        if self.runtime and digest(patch) != last_patch:
                            runtime_result = self.runtime.sync(patch)
                            # Private runtime logs must NEVER become a text/HTTP/source side channel.
                            result['runtime_sync'] = {'status': runtime_result.get('status')}
                            last_patch = digest(patch)
                    elif name == 'browser' and self.condition == 'cua':
                        if set(args) != {'action'}: raise ValueError('browser accepts only action')
                        if self.runtime is None: raise Fault('runtime', 'promised browser absent')
                        image = self.runtime.act(args['action'])
                        if not image or not image.get('data_url', '').startswith('data:image/png;base64,'):
                            raise Fault('image_delivery', 'adapter omitted pixels')
                        self.state['images_created'].append(image['evidence'])
                        result = {'pixels': image['evidence']['sha256']}
                    elif name == 'finish':
                        if set(args) != {'summary'} or not isinstance(args['summary'], str): raise ValueError('finish requires summary text')
                        result = {'submitted': True, 'summary': args['summary']}; finish = True
                    else:
                        raise ValueError('unknown/unavailable tool')
                except (ValueError, KeyError, TypeError) as exc:
                    result = {'tool_argument_error': str(exc)}
                finally:
                    self.state['tool_seconds'] += time.monotonic() - before
                # Entire tool output and raw shell envelope are preserved; no command-string validity oracle.
                toolref = write_json(self.root / f'{turn:03}-{index:02}-tool.json', {'call': call, 'result': result})
                items.append({'type': 'function_call_output', 'call_id': cid, 'output': json.dumps(result)})
                if image:
                    pending_images.append(image)
                    items.append({'role': 'user', 'content': [{'type': 'input_text', 'text': 'Current app screenshot from browser tool ' + cid}, {'type': 'input_image', 'image_url': image['data_url']}]})
            if finish:
                self.state['termination'] = 'submitted'; return
        self.state['termination'] = 'response_cap'
