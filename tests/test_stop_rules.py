"""Stop rule tests: turn cap, token budget and stall detection.

Unit tests build transcripts by hand. Integration tests run the real loop with
a fake user or a tiny budget, using the stub model.
"""

import json

import pytest

from harness import orchestrator
from harness.agents import STUB_REPLIES
from harness.orchestrator import load_config, load_personas, run_interview, stop_rule_hit
from harness.schemas import InterviewPrep
from harness.transcript import Transcript

CONFIG = load_config()
PERSONA = load_personas(CONFIG["paths"]["personas"], ["p01"])[0]
PREP = InterviewPrep.model_validate(STUB_REPLIES["prep"] | {"persona_id": PERSONA.id})
LONG_ANSWER = "I used the app on my phone and then asked my neighbor to look at it."
SHORT_ANSWER = "Yes, I did."


def transcript_with(tmp_path, answers: list[str]) -> Transcript:
    """A transcript with one question before each answer."""
    transcript = Transcript(tmp_path / "transcript.jsonl")
    for answer in answers:
        transcript.add("interviewer", "And then?")
        transcript.add("user", answer)
    return transcript


@pytest.fixture
def config(tmp_path):
    return CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}}


def test_no_rule_fires_on_a_healthy_interview(tmp_path):
    assert stop_rule_hit(transcript_with(tmp_path, [LONG_ANSWER] * 5), 1_000, CONFIG) is None


def test_turn_cap(tmp_path):
    cap = CONFIG["interview"]["max_interviewer_turns"]
    assert stop_rule_hit(transcript_with(tmp_path, [LONG_ANSWER] * cap), 0, CONFIG) == "turn cap"


def test_token_budget(tmp_path):
    budget = CONFIG["interview"]["token_budget_per_interview"]
    assert stop_rule_hit(transcript_with(tmp_path, [LONG_ANSWER]), budget, CONFIG) == "token budget"
    assert stop_rule_hit(transcript_with(tmp_path, [LONG_ANSWER]), budget - 1, CONFIG) is None


def test_three_short_answers_in_a_row_is_a_stall(tmp_path):
    assert stop_rule_hit(transcript_with(tmp_path, [LONG_ANSWER] + [SHORT_ANSWER] * 3), 0, CONFIG) == "stalled"


@pytest.mark.parametrize("answers", [
    [SHORT_ANSWER] * 2,  # only two
    [SHORT_ANSWER, LONG_ANSWER, SHORT_ANSWER, SHORT_ANSWER],  # not in a row
])
def test_short_answers_that_are_not_a_stall(tmp_path, answers):
    assert stop_rule_hit(transcript_with(tmp_path, answers), 0, CONFIG) is None


def test_a_terse_user_stalls_the_real_loop(config, monkeypatch):
    real_call_agent = orchestrator.call_agent

    def terse_user(agent, *args, **kwargs):
        return SHORT_ANSWER if agent == "user" else real_call_agent(agent, *args, **kwargs)

    monkeypatch.setattr(orchestrator, "call_agent", terse_user)
    monkeypatch.setitem(STUB_REPLIES, "interviewer", [{"action": "ask", "question": "Tell me more?"}])

    interview = run_interview(PERSONA, PREP, config, dry_run=True)

    assert interview.stopped_by == "stalled"
    assert [t.speaker for t in interview.transcript.turns].count("user") == 3


def test_a_tiny_budget_stops_the_real_loop(config):
    config = config | {"interview": config["interview"] | {"token_budget_per_interview": 1}}
    interview = run_interview(PERSONA, PREP, config, dry_run=True)
    # One full exchange runs before the budget is checked again.
    assert interview.stopped_by == "token budget"
    assert len(interview.transcript.turns) == 2


def test_summary_records_the_stop_rule_and_tokens(config):
    interview = run_interview(PERSONA, PREP, config, dry_run=True)
    summary = json.loads((interview.transcript.path.parent / "summary.json").read_text())
    assert summary["stopped_by"] == "interviewer ended"
    assert summary["tokens"] == interview.tokens > 0
    assert all(t.tokens > 0 for t in interview.transcript.turns)
