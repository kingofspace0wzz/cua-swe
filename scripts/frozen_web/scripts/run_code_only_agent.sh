#!/usr/bin/env bash
set -euo pipefail

: "${CUA_SWE_AGENT_ROLLOUT_DIR:?set CUA_SWE_AGENT_ROLLOUT_DIR}"
: "${CUA_SWE_TASK_ID:?set CUA_SWE_TASK_ID}"
: "${CUA_SWE_TASK_INSTRUCTION:?set CUA_SWE_TASK_INSTRUCTION}"
: "${CUA_SWE_BUILD_COMMAND:?set CUA_SWE_BUILD_COMMAND}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CUA_SWE_AGENT_RUNTIME="${CUA_SWE_AGENT_RUNTIME:-codex}"
CUA_SWE_AGENT_PYTHON="${CUA_SWE_AGENT_PYTHON:-${CUA_SWE_PYTHON:-python3}}"
CUA_SWE_CODEX_MODEL="${CUA_SWE_CODEX_MODEL:-gpt-5.6-luna}"
CUA_SWE_CODEX_BIN="${CUA_SWE_CODEX_BIN:-codex}"
CUA_SWE_CODEX_NODE="${CUA_SWE_CODEX_NODE:-}"
CUA_SWE_CODEX_BASE_URL="${CUA_SWE_CODEX_BASE_URL:-}"
CUA_SWE_CODEX_API_KEY_ENV="${CUA_SWE_CODEX_API_KEY_ENV:-OPENAI_API_KEY}"
CUA_SWE_CODEX_REASONING_EFFORT="${CUA_SWE_CODEX_REASONING_EFFORT:-medium}"
CUA_SWE_ANTHROPIC_AGENT="${CUA_SWE_ANTHROPIC_AGENT:-$SCRIPT_DIR/run_anthropic_cua_agent.py}"
CUA_SWE_ANTHROPIC_MODEL="${CUA_SWE_ANTHROPIC_MODEL:-claude-opus-4-8}"
CUA_SWE_RESPONSES_AGENT="${CUA_SWE_RESPONSES_AGENT:-$SCRIPT_DIR/run_responses_agent.py}"
CUA_SWE_RESPONSES_MODEL="${CUA_SWE_RESPONSES_MODEL:-gpt-5.6-sol}"
CUA_SWE_KIMI_AGENT="${CUA_SWE_KIMI_AGENT:-$SCRIPT_DIR/run_kimi_cua_agent.py}"
CUA_SWE_KIMI_MODEL="${CUA_SWE_KIMI_MODEL:-kimi-k2.5}"

# Codex uses its builtin "openai" provider unless a Responses endpoint is supplied
# through CUA_SWE_CODEX_BASE_URL. Evaluation runners point it at the controller's
# provider gateway and set CUA_SWE_CODEX_API_KEY_ENV=CUA_SWE_GATEWAY_TOKEN, so Codex
# presents only its trial lease. NONE configures an unauthenticated local endpoint.
CODEX_PROVIDER_ARGS=()
if [ -n "$CUA_SWE_CODEX_BASE_URL" ]; then
  CODEX_PROVIDER_ARGS=(
    --config 'model_provider="cua_swe"'
    --config 'model_providers.cua_swe.name="cua-swe"'
    --config "model_providers.cua_swe.base_url=\"$CUA_SWE_CODEX_BASE_URL\""
    --config 'model_providers.cua_swe.wire_api="responses"'
  )
  if [ "$CUA_SWE_CODEX_API_KEY_ENV" = "NONE" ]; then
    CODEX_PROVIDER_ARGS+=(--config 'model_providers.cua_swe.requires_openai_auth=false')
  else
    CODEX_PROVIDER_ARGS+=(--config "model_providers.cua_swe.env_key=\"$CUA_SWE_CODEX_API_KEY_ENV\"")
  fi
fi

mkdir -p "$CUA_SWE_AGENT_ROLLOUT_DIR"

cleanup() {
  while IFS= read -r pid_file; do
    kill "$(cat "$pid_file")" >/dev/null 2>&1 || true
  done < <(find "$CUA_SWE_AGENT_ROLLOUT_DIR" -maxdepth 2 -type f -name '*.pid' 2>/dev/null)
}
trap cleanup EXIT

PROMPT="$(
  "$CUA_SWE_AGENT_PYTHON" "$SCRIPT_DIR/render_web_agent_prompt.py" \
    --condition code-only \
    --task-id "$CUA_SWE_TASK_ID" \
    --task-instruction "$CUA_SWE_TASK_INSTRUCTION" \
    --prompt-revision "${CUA_SWE_PROMPT_REVISION:-original-web-20260906}" \
    --build-command "$CUA_SWE_BUILD_COMMAND"
)"

case "$CUA_SWE_AGENT_RUNTIME" in
  codex)
    # Codex reads its own provider variables; the routing table is for native agents.
    unset CUA_SWE_PROVIDER_ROUTES
    CODEX_ARGS=(
      exec
      --json
      --ephemeral
      --ignore-user-config
      --ignore-rules
      --strict-config
      --disable plugins
      --model "$CUA_SWE_CODEX_MODEL"
      ${CODEX_PROVIDER_ARGS[@]+"${CODEX_PROVIDER_ARGS[@]}"}
      --config "model_reasoning_effort=\"$CUA_SWE_CODEX_REASONING_EFFORT\""
      --dangerously-bypass-approvals-and-sandbox
      --cd "$PWD"
      --output-last-message "$CUA_SWE_AGENT_ROLLOUT_DIR/codex_last_message.txt"
      "$PROMPT"
    )
    if [ -n "$CUA_SWE_CODEX_NODE" ]; then
      "$CUA_SWE_CODEX_NODE" "$CUA_SWE_CODEX_BIN" "${CODEX_ARGS[@]}" \
        > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" \
        2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    else
      "$CUA_SWE_CODEX_BIN" "${CODEX_ARGS[@]}" \
        > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" \
        2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    fi
    ;;
  anthropic)
    "$CUA_SWE_AGENT_PYTHON" "$CUA_SWE_ANTHROPIC_AGENT" --code-only --model "$CUA_SWE_ANTHROPIC_MODEL" --workspace "$PWD" --rollout-dir "$CUA_SWE_AGENT_ROLLOUT_DIR" --prompt "$PROMPT" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  responses)
    "$CUA_SWE_AGENT_PYTHON" "$CUA_SWE_RESPONSES_AGENT" --code-only --model "$CUA_SWE_RESPONSES_MODEL" --workspace "$PWD" --rollout-dir "$CUA_SWE_AGENT_ROLLOUT_DIR" --prompt "$PROMPT" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  kimi)
    "$CUA_SWE_AGENT_PYTHON" "$CUA_SWE_KIMI_AGENT" --code-only --model "$CUA_SWE_KIMI_MODEL" --workspace "$PWD" --rollout-dir "$CUA_SWE_AGENT_ROLLOUT_DIR" --prompt "$PROMPT" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  *)
    echo "Unsupported CUA_SWE_AGENT_RUNTIME: $CUA_SWE_AGENT_RUNTIME" >&2
    exit 2
    ;;
esac
