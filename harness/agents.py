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

    TODO (module 1): build this function.
      1. Look up the model for `agent` in config["models"].
      2. Read the system prompt from config["paths"]["prompts"] / f"{agent}.md".
      3. Wrap user_message in a messages list: [{"role": "user", "content": ...}].
      4. Pick a client: StubClient(agent) if dry_run, otherwise _real_client().
      5. Call client.messages.create(model=, max_tokens=, system=, messages=)
         and time it with time.monotonic().
      6. Join the text of every block whose .type is "text" into one string.
      7. Log the call with _log_call() before checking for problems.
      8. Raise AgentError if response.stop_reason is "refusal" or "max_tokens".
      9. Return the text.
    """
    raise NotImplementedError("Module 1: build call_agent()")


@cache
def _real_client() -> anthropic.Anthropic:
    """Create the API client once and reuse it, so calls share one connection pool."""
    return anthropic.Anthropic()


def _log_call(log_dir: Path, agent: str, response, latency: float, system: str, messages: list, output: str) -> None:
    """Append one line to calls.jsonl with everything needed to replay the call.

    The exact prompt is logged on purpose. In module 4 this log becomes the
    isolation audit: search it to prove the interviewer never saw the persona.

    TODO (module 1): build this function.
      1. Create log_dir if it doesn't exist.
      2. Build a dict with: ts (UTC time), agent, model (response.model),
         input_tokens and output_tokens (response.usage), latency_s,
         stop_reason, system, messages and output.
      3. Append it to log_dir / "calls.jsonl" as one line of JSON.
    """
    raise NotImplementedError("Module 1: build _log_call()")


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
