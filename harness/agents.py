"""call_agent(): the one place in the harness that talks to a model.

Routing every model call through one function gives us one place to log,
one place to swap in a stub for --dry-run, and (in module 2) one place to
add retries. If you find a model call anywhere else, it's a bug.
"""

import json
import time
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from types import SimpleNamespace

import anthropic


class AgentError(Exception):
    """A model call returned something we can't use."""


def call_agent(agent: str, user_message: str, config: dict, log_dir: Path, dry_run: bool = False) -> str:
    """Send one request to the model configured for `agent` and return its text.

    The system prompt is read from prompts/<agent>.md, so prompts can be
    improved without touching code. Each call is built from scratch: no agent
    carries a conversation history between calls.
    """
    model = config["models"][agent]
    system = (Path(config["paths"]["prompts"]) / f"{agent}.md").read_text()
    messages = [{"role": "user", "content": user_message}]
    client = StubClient(agent) if dry_run else _real_client()

    start = time.monotonic()
    response = client.messages.create(
        model=model, max_tokens=config["max_tokens"], system=system, messages=messages
    )
    latency = time.monotonic() - start

    text = "".join(block.text for block in response.content if block.type == "text")
    _log_call(log_dir, agent, response, latency, system, messages, text)

    # Log first, then fail: a failed call is exactly the one you'll want to read.
    if response.stop_reason == "refusal":
        raise AgentError(f"{agent}: the model declined this request. See {log_dir}/calls.jsonl")
    if response.stop_reason == "max_tokens":
        raise AgentError(f"{agent}: reply was cut off at max_tokens. Raise max_tokens in config.yaml")
    return text


@cache
def _real_client() -> anthropic.Anthropic:
    """Create the API client once and reuse it, so calls share one connection pool."""
    return anthropic.Anthropic()


def _log_call(log_dir: Path, agent: str, response, latency: float, system: str, messages: list, output: str) -> None:
    """Append one line to calls.jsonl with everything needed to replay the call.

    The exact prompt is logged on purpose. In module 4 this log becomes the
    isolation audit: search it to prove the interviewer never saw the persona.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent,
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_s": round(latency, 2),
        "stop_reason": response.stop_reason,
        "system": system,
        "messages": messages,
        "output": output,
    }
    with open(log_dir / "calls.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Dry-run stub -----------------------------------------------------------
# The stub copies the shape of anthropic.Anthropic() just closely enough that
# call_agent() can't tell the difference. No network, no API key, no cost.

CANNED_REPLIES = {
    "prep": json.dumps(
        {
            "key_hypotheses": [
                "The job hypothesis describes a real, recent struggle, not a general wish",
                "The current workaround costs time, accuracy or independence",
                "The current workaround is good enough and nothing would change",
            ],
            "interviewee_profile": "Someone in this segment who has done a leveling task in the last month. Screen out anyone who has never done one.",
            "starter_questions": [
                "Tell me about the last time you had to get something level.",
                "What made that the day you did it?",
                "How did you know it was straight?",
            ],
            "contrasting_questions": [
                "Was the bigger problem the time it took or the result?",
                "Why that method rather than asking someone for help?",
            ],
        }
    ),
}


class StubClient:
    """Stands in for anthropic.Anthropic() during --dry-run."""

    def __init__(self, agent: str):
        self.messages = _StubMessages(agent)


class _StubMessages:
    def __init__(self, agent: str):
        self.agent = agent

    def create(self, *, model: str, max_tokens: int, system: str, messages: list):
        """Return a canned reply in the same shape as a real Message."""
        text = CANNED_REPLIES[self.agent]
        prompt_chars = len(system) + sum(len(m["content"]) for m in messages)
        return SimpleNamespace(
            model=f"stub:{model}",
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            # Rough estimate (about 4 characters per token) so token logs look realistic.
            usage=SimpleNamespace(input_tokens=prompt_chars // 4, output_tokens=len(text) // 4),
        )
