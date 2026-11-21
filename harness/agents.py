"""call_agent(): the one place in the harness that talks to a model.

Routing every model call through one function gives us one place to log,
one place to swap in a stub for --dry-run, and one place to add retries.
If you find a model call anywhere else, it's a bug.
"""

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from types import SimpleNamespace

import anthropic
from pydantic import BaseModel

from harness.schemas import describe_error, parse_reply


class AgentError(Exception):
    """A model call returned something we can't use."""


class TokenMeter:
    """Counts the tokens one interview has spent, so the budget rule can stop it.

    Pass the same meter to every call in an interview. Retries count too:
    a retry costs real money.
    """

    def __init__(self):
        self.used = 0
        self.last_output_tokens = 0

    def add(self, usage) -> None:
        self.used += usage.input_tokens + usage.output_tokens
        self.last_output_tokens = usage.output_tokens


class OutputInvalid(AgentError):
    """The reply failed validation on the first try and on the retry."""

    def __init__(self, agent: str, error: ValueError, replies: list[str]):
        super().__init__(f"{agent}: reply failed validation twice. Last error:\n{describe_error(error)}")
        self.agent = agent
        self.error = error
        self.replies = replies


def call_agent_json(
    agent: str,
    user_message: str,
    schema: type[BaseModel],
    config: dict,
    log_dir: Path,
    dry_run: bool = False,
    known_fields: dict | None = None,
    meter: TokenMeter | None = None,
    check: Callable[[BaseModel], None] | None = None,
) -> BaseModel:
    """Call an agent and return its reply as a validated `schema` object.

    If the reply doesn't validate, ask once more and show the model its own
    reply and the exact error. Models fix their mistakes far more reliably
    when told what went wrong than when simply asked again. A second failure
    raises OutputInvalid: retrying forever hides a broken prompt.

    `check` is an optional extra test that needs context the schema can't
    see, such as the transcript. It raises ValueError, and gets the same retry.
    """
    message = user_message
    replies = []
    for _ in range(2):  # the first try plus one retry
        reply = call_agent(agent, message, config, log_dir, dry_run, meter)
        replies.append(reply)
        try:
            result = parse_reply(reply, schema, known_fields)
            if check:
                check(result)
            return result
        except ValueError as error:
            last_error = error
            message = (
                f"{user_message}\n\n---\n"
                f"Your previous reply could not be used.\n\n"
                f"Your previous reply:\n{reply}\n\n"
                f"What was wrong:\n{describe_error(error)}\n\n"
                f"Reply again with corrected JSON only."
            )
    raise OutputInvalid(agent, last_error, replies)


# Server tools an agent may use. config.yaml decides which agent gets which,
# and only the devil's advocate gets one. Anthropic runs these tools, not us.
TOOLS = {"web_search": {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}}
MAX_CONTINUATIONS = 3


def call_agent(agent: str, user_message: str, config: dict, log_dir: Path, dry_run: bool = False,
               meter: TokenMeter | None = None) -> str:
    """Send one request to the model configured for `agent` and return its text.

    The system prompt is read from prompts/<agent>.md, so prompts can be
    improved without touching code. Each call is built from scratch: no agent
    carries a conversation history between calls.
    """
    model = config["models"][agent]
    system = (Path(config["paths"]["prompts"]) / f"{agent}.md").read_text()
    messages = [{"role": "user", "content": user_message}]
    tools = [TOOLS[name] for name in config.get("tools", {}).get(agent, [])]
    request = {"model": model, "max_tokens": config["max_tokens"], "system": system}
    if tools:
        request["tools"] = tools
    client = StubClient(agent) if dry_run else _real_client()

    start = time.monotonic()
    response = client.messages.create(messages=messages, **request)
    calls, assistant_so_far = [response], []
    # A long run of searches can pause. Sending back what came so far resumes it.
    while response.stop_reason == "pause_turn" and len(calls) <= MAX_CONTINUATIONS:
        assistant_so_far += response.content
        response = client.messages.create(
            messages=messages + [{"role": "assistant", "content": assistant_so_far}], **request)
        calls.append(response)
    latency = time.monotonic() - start

    text = _final_text(response.content)
    usage = SimpleNamespace(input_tokens=sum(c.usage.input_tokens for c in calls),
                            output_tokens=sum(c.usage.output_tokens for c in calls))
    _log_call(log_dir, agent, response.model, usage, latency, response.stop_reason, system, messages, text,
              [t["name"] for t in tools])
    if meter:
        meter.add(usage)

    # Log first, then fail: a failed call is exactly the one you'll want to read.
    if response.stop_reason == "refusal":
        raise AgentError(f"{agent}: the model declined this request. See {log_dir}/calls.jsonl")
    if response.stop_reason == "max_tokens":
        raise AgentError(f"{agent}: reply was cut off at max_tokens. Raise max_tokens in config.yaml")
    if response.stop_reason == "pause_turn":
        raise AgentError(f"{agent}: still searching after {MAX_CONTINUATIONS} continuations")
    return text


def _final_text(content: list) -> str:
    """Return the reply's text after its last tool result.

    With web search, a model may write notes between searches. Only the text
    after the last search is its answer.
    """
    last_result = max((i for i, b in enumerate(content) if b.type.endswith("_tool_result")), default=-1)
    return "".join(b.text for b in content[last_result + 1:] if b.type == "text")


@cache
def _real_client() -> anthropic.Anthropic:
    """Create the API client once and reuse it, so calls share one connection pool."""
    return anthropic.Anthropic()


def _log_call(log_dir: Path, agent: str, model: str, usage, latency: float, stop_reason: str,
              system: str, messages: list, output: str, tools: list[str]) -> None:
    """Append one line to calls.jsonl with everything needed to replay the call.

    The exact prompt is logged on purpose. The log doubles as the isolation
    audit: tests/test_isolation.py reads it to prove what each agent saw.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent,
        "model": model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "latency_s": round(latency, 2),
        "stop_reason": stop_reason,
        "tools": tools,
        "system": system,
        "messages": messages,
        "output": output,
    }
    with open(log_dir / "calls.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Dry-run stub -----------------------------------------------------------
# The stub copies the shape of anthropic.Anthropic() just closely enough that
# call_agent() can't tell the difference. No network, no API key, no cost.

STUB_REPLIES = json.loads((Path(__file__).parent / "stub_replies.json").read_text())

# How the stub tells how far an interview has got: it counts this speaker's
# earlier turns in the rendered transcript (see Transcript.render()).
STUB_TURN_MARKERS = {"interviewer": "] Interviewer: ", "user": "] Interviewee: "}


class StubClient:
    """Stands in for anthropic.Anthropic() during --dry-run."""

    def __init__(self, agent: str):
        self.messages = _StubMessages(agent)


class _StubMessages:
    def __init__(self, agent: str):
        self.agent = agent

    def create(self, *, model: str, max_tokens: int, system: str, messages: list, tools: list | None = None):
        """Return a canned reply in the same shape as a real Message."""
        text = _pick_stub_reply(self.agent, messages[-1]["content"])
        prompt_chars = len(system) + sum(len(m["content"]) for m in messages)
        return SimpleNamespace(
            model=f"stub:{model}",
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            # Rough estimate (about 4 characters per token) so token logs look realistic.
            usage=SimpleNamespace(input_tokens=prompt_chars // 4, output_tokens=len(text) // 4),
        )


def _pick_stub_reply(agent: str, prompt: str) -> str:
    """Pick the canned reply for this point in the conversation.

    A list of replies is played in order: the Nth reply for the Nth turn by
    this speaker. The last item repeats if the conversation runs longer.
    """
    reply = STUB_REPLIES[agent]
    if isinstance(reply, list):
        earlier_turns = prompt.count(STUB_TURN_MARKERS[agent])
        reply = reply[min(earlier_turns, len(reply) - 1)]
    return reply if isinstance(reply, str) else json.dumps(reply)
