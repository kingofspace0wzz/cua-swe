#!/usr/bin/env bash
set -euo pipefail

: "${CUA_SWE_AGENT_ROLLOUT_DIR:?set CUA_SWE_AGENT_ROLLOUT_DIR}"
: "${CUA_SWE_TASK_ID:?set CUA_SWE_TASK_ID}"
: "${CUA_SWE_TASK_INSTRUCTION:?set CUA_SWE_TASK_INSTRUCTION}"
: "${CUA_SWE_BUILD_COMMAND:?set CUA_SWE_BUILD_COMMAND}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CUA_SWE_WEB_CUA_TOOL="${CUA_SWE_WEB_CUA_TOOL:-$SCRIPT_DIR/web_cua_tool.py}"
CUA_SWE_WEB_CUA_PYTHON="${CUA_SWE_WEB_CUA_PYTHON:-${CUA_SWE_PYTHON:-${CUA_SWE_MOBILEGYM_PYTHON:-python3}}}"
CUA_SWE_WEB_CUA_LAUNCHER="${CUA_SWE_WEB_CUA_LAUNCHER:-$SCRIPT_DIR/../bin/web_cua_launcher}"
CUA_SWE_WEB_CUA_SESSION="$CUA_SWE_AGENT_ROLLOUT_DIR/cua-session.json"
CUA_SWE_CODEX_MODEL="${CUA_SWE_CODEX_MODEL:-gpt-5.6-luna}"
CUA_SWE_CODEX_BIN="${CUA_SWE_CODEX_BIN:-codex}"
CUA_SWE_CODEX_NODE="${CUA_SWE_CODEX_NODE:-}"
CUA_SWE_CODEX_BASE_URL="${CUA_SWE_CODEX_BASE_URL:-}"
CUA_SWE_CODEX_API_KEY_ENV="${CUA_SWE_CODEX_API_KEY_ENV:-OPENAI_API_KEY}"
CUA_SWE_CODEX_PROFILE="${CUA_SWE_CODEX_PROFILE:-}"
CUA_SWE_CODEX_REASONING_EFFORT="${CUA_SWE_CODEX_REASONING_EFFORT:-medium}"
CUA_SWE_AGENT_RUNTIME="${CUA_SWE_AGENT_RUNTIME:-codex}"
CUA_SWE_WEB_PORT="${CUA_SWE_WEB_PORT:-4173}"
CUA_SWE_WEB_URL="${CUA_SWE_WEB_URL:-http://127.0.0.1:$CUA_SWE_WEB_PORT}"
CUA_SWE_WEB_VIEWPORT="${CUA_SWE_WEB_VIEWPORT:-1280x720}"
CUA_SWE_WEB_OBSERVATION_MODE="${CUA_SWE_WEB_OBSERVATION_MODE:-structured}"
CUA_SWE_CLAUDE_BIN="${CUA_SWE_CLAUDE_BIN:-claude}"
CUA_SWE_CLAUDE_MODEL="${CUA_SWE_CLAUDE_MODEL:-claude-opus-5}"
CUA_SWE_CLAUDE_BASE_URL="${CUA_SWE_CLAUDE_BASE_URL:-}"
CUA_SWE_CLAUDE_MAX_BUDGET_USD="${CUA_SWE_CLAUDE_MAX_BUDGET_USD:-10.00}"
CUA_SWE_RESPONSES_AGENT="${CUA_SWE_RESPONSES_AGENT:-$SCRIPT_DIR/run_responses_agent.py}"
CUA_SWE_RESPONSES_MODEL="${CUA_SWE_RESPONSES_MODEL:-gpt-5.6-sol}"
CUA_SWE_KIMI_AGENT="${CUA_SWE_KIMI_AGENT:-$SCRIPT_DIR/run_kimi_cua_agent.py}"
CUA_SWE_KIMI_MODEL="${CUA_SWE_KIMI_MODEL:-kimi-k2.5}"
CUA_SWE_QWEN_AGENT="${CUA_SWE_QWEN_AGENT:-$SCRIPT_DIR/run_qwen_cua_agent.py}"
CUA_SWE_QWEN_MODEL="${CUA_SWE_QWEN_MODEL:-qwen3-vl-235b-a22b-instruct}"
CUA_SWE_ANTHROPIC_AGENT="${CUA_SWE_ANTHROPIC_AGENT:-$SCRIPT_DIR/run_anthropic_cua_agent.py}"
CUA_SWE_ANTHROPIC_MODEL="${CUA_SWE_ANTHROPIC_MODEL:-claude-opus-4-8}"

CUA_SWE_VISUAL_TRANSPORT=mcp
case "$CUA_SWE_AGENT_RUNTIME" in
  responses|anthropic|kimi|qwen)
    CUA_SWE_VISUAL_TRANSPORT=shell
    ;;
esac

export CUA_SWE_WEB_CUA_TOOL
export CUA_SWE_WEB_CUA_PYTHON
export CUA_SWE_WEB_CUA_LAUNCHER
export CUA_SWE_WEB_CUA_SESSION
export CUA_SWE_WEB_PORT
export CUA_SWE_WEB_URL
export CUA_SWE_WEB_VIEWPORT
export CUA_SWE_WEB_OBSERVATION_MODE
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
if [ ! -x "$CUA_SWE_WEB_CUA_LAUNCHER" ]; then
  echo "Protected CUA launcher is unavailable: $CUA_SWE_WEB_CUA_LAUNCHER" >&2
  exit 2
fi

cleanup() {
  while IFS= read -r pid_file; do
    kill "$(cat "$pid_file")" >/dev/null 2>&1 || true
  done < <(find "$CUA_SWE_AGENT_ROLLOUT_DIR" -maxdepth 2 -type f -name '*.pid' 2>/dev/null)
}
trap cleanup EXIT

PROMPT="$(
  "$CUA_SWE_WEB_CUA_PYTHON" "$SCRIPT_DIR/render_web_agent_prompt.py" \
    --condition browser \
    --task-id "$CUA_SWE_TASK_ID" \
    --task-instruction "$CUA_SWE_TASK_INSTRUCTION" \
    --build-command "$CUA_SWE_BUILD_COMMAND" \
    --prompt-revision "${CUA_SWE_PROMPT_REVISION:-original-web-20260906}" \
    --launcher "$CUA_SWE_WEB_CUA_LAUNCHER" \
    --session-file "$CUA_SWE_WEB_CUA_SESSION" \
    --artifacts-dir "$CUA_SWE_AGENT_ROLLOUT_DIR/cua-adapter" \
    --url "$CUA_SWE_WEB_URL" \
    --viewport "$CUA_SWE_WEB_VIEWPORT" \
    --observation-mode "$CUA_SWE_WEB_OBSERVATION_MODE" \
    --visual-transport "$CUA_SWE_VISUAL_TRANSPORT"
)"

CODEX_ARGS=(exec --json --ephemeral --ignore-user-config --ignore-rules --strict-config --disable plugins --model "$CUA_SWE_CODEX_MODEL")
if [ "$CUA_SWE_WEB_OBSERVATION_MODE" = "visual" ]; then
  CODEX_ARGS+=(
    --config "mcp_servers.visual_cua.command=\"$CUA_SWE_WEB_CUA_PYTHON\""
    --config "mcp_servers.visual_cua.args=[\"-I\", \"$SCRIPT_DIR/web_cua_mcp.py\"]"
    --config 'mcp_servers.visual_cua.startup_timeout_sec=30'
    --config 'mcp_servers.visual_cua.tool_timeout_sec=90'
    --config "mcp_servers.visual_cua.env.CUA_SWE_WEB_CUA_LAUNCHER=\"$CUA_SWE_WEB_CUA_LAUNCHER\""
    --config "mcp_servers.visual_cua.env.CUA_SWE_WEB_CUA_SESSION=\"$CUA_SWE_WEB_CUA_SESSION\""
    --config "mcp_servers.visual_cua.env.CUA_SWE_AGENT_ROLLOUT_DIR=\"$CUA_SWE_AGENT_ROLLOUT_DIR\""
    --config "mcp_servers.visual_cua.env.CUA_SWE_WEB_URL=\"$CUA_SWE_WEB_URL\""
    --config "mcp_servers.visual_cua.env.CUA_SWE_WEB_VIEWPORT=\"$CUA_SWE_WEB_VIEWPORT\""
  )
fi
if [ -n "$CUA_SWE_CODEX_PROFILE" ]; then
  CODEX_ARGS+=(--profile "$CUA_SWE_CODEX_PROFILE")
fi
if [ -n "$CUA_SWE_CODEX_BASE_URL" ]; then
  CODEX_ARGS+=("${CODEX_PROVIDER_ARGS[@]}")
fi
if [ -n "$CUA_SWE_CODEX_REASONING_EFFORT" ]; then
  CODEX_ARGS+=(--config "model_reasoning_effort=\"$CUA_SWE_CODEX_REASONING_EFFORT\"")
fi
CODEX_ARGS+=(
  --dangerously-bypass-approvals-and-sandbox
  --cd "$PWD"
  --output-last-message "$CUA_SWE_AGENT_ROLLOUT_DIR/codex_last_message.txt"
  "$PROMPT"
)

case "$CUA_SWE_AGENT_RUNTIME" in
  codex)
    # Codex reads its own provider variables; the routing table is for native agents.
    unset CUA_SWE_PROVIDER_ROUTES
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
  claude)
    if [ ! -x "$CUA_SWE_CLAUDE_BIN" ]; then
      echo "Claude Code executable is not available: $CUA_SWE_CLAUDE_BIN" >&2
      exit 2
    fi
    unset CUA_SWE_PROVIDER_ROUTES
    if [ -n "$CUA_SWE_CLAUDE_BASE_URL" ]; then
      # The provider gateway authenticates upstream; Claude Code presents its trial lease.
      if [ -z "${CUA_SWE_GATEWAY_TOKEN:-}" ]; then
        echo "set CUA_SWE_GATEWAY_TOKEN for CUA_SWE_CLAUDE_BASE_URL" >&2
        exit 2
      fi
      export ANTHROPIC_BASE_URL="$CUA_SWE_CLAUDE_BASE_URL"
      export ANTHROPIC_API_KEY="$CUA_SWE_GATEWAY_TOKEN"
      unset CUA_SWE_GATEWAY_TOKEN
    else
      if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo "set ANTHROPIC_API_KEY or CUA_SWE_CLAUDE_BASE_URL" >&2
        exit 2
      fi
    fi
    export ANTHROPIC_MODEL="$CUA_SWE_CLAUDE_MODEL"
    export ANTHROPIC_DEFAULT_OPUS_MODEL="$CUA_SWE_CLAUDE_MODEL"
    export ANTHROPIC_DEFAULT_SONNET_MODEL="$CUA_SWE_CLAUDE_MODEL"
    export ANTHROPIC_DEFAULT_HAIKU_MODEL="$CUA_SWE_CLAUDE_MODEL"
    export ANTHROPIC_SMALL_FAST_MODEL="$CUA_SWE_CLAUDE_MODEL"
    CLAUDE_ARGS=(--bare -p "$PROMPT" --model "$CUA_SWE_CLAUDE_MODEL" --effort medium --max-budget-usd "$CUA_SWE_CLAUDE_MAX_BUDGET_USD" --dangerously-skip-permissions --no-chrome --no-session-persistence --output-format stream-json --verbose)
    if [ "$CUA_SWE_WEB_OBSERVATION_MODE" = "visual" ]; then
      CLAUDE_MCP_CONFIG="$CUA_SWE_AGENT_ROLLOUT_DIR/claude-mcp.json"
      export CLAUDE_MCP_CONFIG
      export CUA_SWE_MCP_SCRIPT="$SCRIPT_DIR/web_cua_mcp.py"
      "$CUA_SWE_WEB_CUA_PYTHON" - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "mcpServers": {
        "visual_cua": {
            "command": os.environ["CUA_SWE_WEB_CUA_PYTHON"],
            "args": ["-I", os.environ["CUA_SWE_MCP_SCRIPT"]],
            "env": {
                name: os.environ[name]
                for name in (
                    "CUA_SWE_WEB_CUA_LAUNCHER",
                    "CUA_SWE_WEB_CUA_SESSION",
                    "CUA_SWE_AGENT_ROLLOUT_DIR",
                    "CUA_SWE_WEB_URL",
                    "CUA_SWE_WEB_VIEWPORT",
                )
            },
        }
    }
}
Path(os.environ["CLAUDE_MCP_CONFIG"]).write_text(
    json.dumps(payload, sort_keys=True), encoding="utf-8"
)
PY
      CLAUDE_ARGS+=(--mcp-config "$CLAUDE_MCP_CONFIG" --strict-mcp-config)
    fi
    "$CUA_SWE_CLAUDE_BIN" "${CLAUDE_ARGS[@]}" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  anthropic)
    "$CUA_SWE_WEB_CUA_PYTHON" "$CUA_SWE_ANTHROPIC_AGENT" --model "$CUA_SWE_ANTHROPIC_MODEL" --workspace "$PWD" --rollout-dir "$CUA_SWE_AGENT_ROLLOUT_DIR" --prompt "$PROMPT" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  responses)
    RESPONSES_EXTRA_ARGS=()
    if [ "$CUA_SWE_RESPONSES_MODEL" = "gpt-6-astra" ]; then
      RESPONSES_EXTRA_ARGS+=(--reasoning-effort medium --max-turns "${CUA_SWE_RESPONSES_MAX_TURNS:-100}")
    fi
    "$CUA_SWE_WEB_CUA_PYTHON" "$CUA_SWE_RESPONSES_AGENT" --model "$CUA_SWE_RESPONSES_MODEL" --workspace "$PWD" --rollout-dir "$CUA_SWE_AGENT_ROLLOUT_DIR" "${RESPONSES_EXTRA_ARGS[@]}" --prompt "$PROMPT" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  kimi)
    "$CUA_SWE_WEB_CUA_PYTHON" "$CUA_SWE_KIMI_AGENT" --model "$CUA_SWE_KIMI_MODEL" --workspace "$PWD" --rollout-dir "$CUA_SWE_AGENT_ROLLOUT_DIR" --prompt "$PROMPT" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  qwen)
    "$CUA_SWE_WEB_CUA_PYTHON" "$CUA_SWE_QWEN_AGENT" --model "$CUA_SWE_QWEN_MODEL" --workspace "$PWD" --rollout-dir "$CUA_SWE_AGENT_ROLLOUT_DIR" --prompt "$PROMPT" > "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stdout.txt" 2> "$CUA_SWE_AGENT_ROLLOUT_DIR/agent_stderr.txt"
    ;;
  *)
    echo "Unsupported CUA_SWE_AGENT_RUNTIME: $CUA_SWE_AGENT_RUNTIME" >&2
    exit 2
    ;;
esac
