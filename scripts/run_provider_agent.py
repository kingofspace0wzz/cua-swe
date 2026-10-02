#!/usr/bin/env python3
"""Provider-configurable implementation of the retained Responses agent contract."""
import argparse
import json
import os
from pathlib import Path

from provider_client import ProviderClient, ProviderConfig
from baseline_responses_agent import ResponsesAgent, TOOLS


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--rollout-dir', type=Path, required=True)
    p.add_argument('--prompt', required=True)
    p.add_argument('--code-only', action='store_true')
    p.add_argument('--max-turns', type=int, default=100)
    # Accepted for launcher compatibility; public providers use their default reasoning setting.
    p.add_argument('--reasoning-effort', choices=('none', 'low', 'medium', 'high', 'xhigh'))
    args = p.parse_args()
    config = ProviderConfig(**json.loads(os.environ['CUA_SWE_PROVIDER_CONFIG']))
    if args.model != config.model:
        raise ValueError('agent model differs from provider configuration')
    # The gateway lease token arrives in config.api_key_env; remove it and the routing so tools inherit neither.
    token = os.environ.pop('CUA_SWE_PROVIDER_TOKEN', '')
    routed = '' if config.api_key_env == 'NONE' else os.environ.pop(config.api_key_env, '')
    token = token or routed
    for name in ('CUA_SWE_PROVIDER_CONFIG', 'CUA_SWE_PROVIDER_ROUTES'):
        os.environ.pop(name, None)
    tools = [t for t in TOOLS if not args.code_only or t['name'] != 'view_image']
    client = ProviderClient(config, tools, token=token, trace_dir=args.rollout_dir / 'provider')
    agent = ResponsesAgent(client, args.workspace, args.rollout_dir, args.prompt, args.max_turns)
    return agent.run()


if __name__ == '__main__':
    raise SystemExit(main())
