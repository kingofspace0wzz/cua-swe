# API providers

[`run_evaluation.py`](../scripts/run_evaluation.py) runs the released Web, Game, Mobile, and DevOps tasks with a configurable model endpoint. Each run records its provider configuration, task selection, evaluator revision, and native verification results.

## Supported interfaces

| `--provider` | Wire endpoint | Default credential variable | Default base URL |
| --- | --- | --- | --- |
| `responses` | `POST /responses` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `chat-completions` | `POST /chat/completions` | `OPENAI_API_KEY` | Set `--base-url` |
| `anthropic` | `POST /messages` | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1` |
| `bedrock` | `POST /model/{model-id}/converse` | `AWS_BEARER_TOKEN_BEDROCK` | `https://bedrock-runtime.{region}.amazonaws.com` |

For the direct **Claude API**, select `--provider anthropic`, set
`ANTHROPIC_API_KEY`, and pass a Claude model ID with `--model`. Requests use
Anthropic's Messages API at `https://api.anthropic.com/v1/messages`. This
configuration works with the Web, Game, Mobile, and DevOps domain commands.

Use `--model` with the model or deployment identifier accepted by that endpoint. The adapter translates function schemas, tool calls, tool results, images, and multi-turn history. CUA requires image input and function calling; code-only requires function calling. A compatible local server can use `--api-key-env NONE`.

Base URLs include the API prefix, such as `/v1`, and omit the final operation name. `--api-key-env` takes an **environment variable name**. Credentials are read at execution; planning requires none. The evaluator uses HTTPS for remote endpoints and permits HTTP for localhost.

See the [README provider examples](../README.md#choose-your-api-provider) for complete configurations.

## Bedrock options

The `bedrock` adapter uses the standard Converse API with bearer API-key authentication. Set `AWS_BEARER_TOKEN_BEDROCK` to your own Bedrock API key and pass `--region`. Model IDs and inference-profile IDs are URL-encoded by the client.

For models supporting Bedrock's OpenAI-compatible Chat Completions API:

```bash
API=(--provider chat-completions --model "$MODEL"
     --base-url "https://bedrock-runtime.${AWS_REGION}.amazonaws.com/openai/v1"
     --api-key-env AWS_BEARER_TOKEN_BEDROCK)
```

For a Bedrock Mantle Chat Completions endpoint:

```bash
API=(--provider chat-completions --model "$MODEL"
     --base-url "https://bedrock-mantle.${AWS_REGION}.api.aws/v1"
     --api-key-env AWS_BEARER_TOKEN_BEDROCK)
```

Use the endpoint and model combination supported in your Bedrock region. The public API-key route uses account credentials you supply through the environment.

## Request behavior

- `--max-output-tokens` defaults to **16,384**; reduce it for models with a smaller output limit.
- `--request-timeout` defaults to **600 seconds**. Mobile also bounds requests by the remaining per-task active time.
- Each model turn makes one provider request. A transport error ends that attempt and is recorded with the evaluator outcome.
- Sampling and reasoning use provider defaults. OpenAI Chat Completions uses `max_completion_tokens`; other Chat Completions endpoints use `max_tokens`.
- Tool results retain their call IDs. The client sends the complete conversation and the image bytes needed for subsequent turns.
- Raw provider response bodies preserve returned model identifiers; the normalized agent interface also records the requested model ID.

Web, Game, and DevOps use a temporary localhost relay owned by the evaluation controller. It attaches the provider credential upstream, so the sandboxed agent receives no cloud API key. Mobile calls the provider from its host controller while source/build tools run in their separate namespace. Request artifacts include payloads and response bodies; authentication headers are excluded.

## Routing the evaluator agents

Every model call goes through the shared provider layer. The evaluation controller runs the authenticated gateway in [`provider_relay.py`](../scripts/provider_relay.py), which holds the API credentials. For each trial it issues a lease: a random token valid for one wire protocol and one model, revoked when the trial ends. The agent receives the loopback gateway URL and the lease token in its environment (never on its command line or in result records) and presents the token where an API key would go. The gateway rejects requests for another protocol or model, replaces the token with the routed credential, and streams the reply back. This applies to the retained Web, Game and DevOps agents (Responses, Claude Messages and Chat Completions agents, plus the Codex and Claude Code CLIs) and to the public agent. Native agents remove the routing and token from their environment before starting tools. Mobile calls the same layer from its host controller, where the agent loop runs; its CLI sandbox has no network and reaches the host through a Unix-socket broker.

By default the gateway sends `responses` traffic to `https://api.openai.com/v1` with `OPENAI_API_KEY` and `anthropic` traffic to `https://api.anthropic.com/v1` with `ANTHROPIC_API_KEY`. To use another compatible endpoint, set `CUA_SWE_PROVIDER_ROUTES` on the controller to a JSON object keyed by wire protocol:

```bash
export CUA_SWE_PROVIDER_ROUTES='{
  "responses": {"base_url": "https://example.com/openai/v1", "api_key_env": "MY_RESPONSES_KEY"},
  "chat-completions": {"base_url": "http://127.0.0.1:8000/v1", "api_key_env": "NONE"}
}'
```

Each route accepts `base_url`, `api_key_env`, `region` and `chat_token_limit`, with the same validation as the command-line options. A protocol whose key variable is unset is not served. Mobile reads a `providers` entry for each route from its private runtime configuration; see the [Mobile evaluation guide](../dataset/mobile/evaluation/README.md).

The Codex and Claude Code CLIs keep the lease token in their own environment because they authenticate with it, so their tool commands can also reach the gateway, but only for the same model and only until the trial ends. To run the Web launchers outside a runner, set `CUA_SWE_CODEX_BASE_URL` with `CUA_SWE_CODEX_API_KEY_ENV` (or `NONE` for an unauthenticated local endpoint), and `CUA_SWE_CLAUDE_BASE_URL` with `CUA_SWE_GATEWAY_TOKEN`; without a base URL the CLIs use their standard providers and keys.

## Extending the transport

[`ProviderClient`](../scripts/provider_client.py) accepts a `ProviderConfig`, the domain's tool schemas, and a trace directory. Its `create(input_items, previous_response_id=...)` method consumes Responses-style input items and returns message/function-call items, response identity, termination status, and usage. The adapters preserve native provider receipts alongside that normalized interface.

For an additional protocol, implement its request translation, response translation, image format, and credential headers, then add a local HTTP fixture to [`test_public_providers.py`](../tests/test_public_providers.py). To replace the agent loop itself, follow [Integrating your agent](agents.md).

## API references

- [OpenAI Responses and function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create)
- [Amazon Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
- [Amazon Bedrock Chat Completions](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions.html)
