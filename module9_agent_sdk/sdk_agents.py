"""call_agent_sdk(): the same job as harness.agents.call_agent(), done by the Claude Agent SDK.

The Agent SDK runs Claude Code as a subprocess. That brings a full agent
harness with built-in tools, settings files and its own system context. This
harness wants none of that by default, so every option below turns something
off. Each line is a place where isolation now depends on configuration
instead of on code you can read.
"""

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from harness.agents import AgentError, TokenMeter, _log_call
from harness.agents import call_agent as messages_api_call_agent

# The harness's tool names mapped to the SDK's built-in tools.
SDK_TOOLS = {"web_search": "WebSearch"}


def sdk_options(agent: str, config: dict) -> ClaudeAgentOptions:
    """Build the SDK options for one agent call."""
    tools = [SDK_TOOLS[name] for name in config.get("tools", {}).get(agent, [])]
    return ClaudeAgentOptions(
        system_prompt=(Path(config["paths"]["prompts"]) / f"{agent}.md").read_text(),
        model=config["models"][agent],
        tools=tools,           # [] turns off every built-in tool: no Bash, no file reading
        allowed_tools=tools,   # pre-approve the tools we do give, so nothing waits for permission
        setting_sources=[],    # don't load CLAUDE.md or settings files from this repo
        max_turns=6 if tools else 1,  # one reply, or a few rounds of searching
    )


async def _ask(user_message: str, options: ClaudeAgentOptions) -> ResultMessage:
    """Send one prompt and wait for the SDK's final result message."""
    result = None
    async for message in query(prompt=user_message, options=options):
        if isinstance(message, ResultMessage):
            result = message
    if result is None:
        raise AgentError("the Agent SDK ended without a result message")
    return result


def call_agent_sdk(agent: str, user_message: str, config: dict, log_dir: Path, dry_run: bool = False,
                   meter: TokenMeter | None = None) -> str:
    """Drop-in replacement for harness.agents.call_agent(), with the same arguments and return value.

    The log shows the prompt we handed over. Unlike the raw API version, it
    can't show the final request: the Claude Code subprocess builds that.
    """
    if dry_run:  # the same stub serves both engines
        return messages_api_call_agent(agent, user_message, config, log_dir, dry_run=True, meter=meter)

    options = sdk_options(agent, config)
    start = time.monotonic()
    result = asyncio.run(_ask(user_message, options))
    latency = time.monotonic() - start

    used = result.usage or {}
    usage = SimpleNamespace(
        input_tokens=sum(used.get(k, 0) for k in
                         ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
        output_tokens=used.get("output_tokens", 0),
    )
    text = result.result or ""
    _log_call(log_dir, agent, options.model, usage, latency, result.stop_reason or result.subtype,
              options.system_prompt, [{"role": "user", "content": user_message}], text, options.tools)
    if meter:
        meter.add(usage)
    if result.is_error:
        raise AgentError(f"{agent}: the Agent SDK reported an error ({result.subtype}). See {log_dir}/calls.jsonl")
    return text
