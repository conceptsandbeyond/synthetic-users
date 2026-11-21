"""Module 3 tests: the turn-taking loop and the transcript writer.

All tests use the stub model or a fake, so they need no API key.
"""

import json

import pytest

from harness import orchestrator
from harness.agents import STUB_REPLIES
from harness.orchestrator import load_config, load_personas, run_interview
from harness.schemas import InterviewerTurn, InterviewPrep, parse_reply
from harness.transcript import Transcript

CONFIG = load_config()
PERSONA = load_personas(CONFIG["paths"]["personas"], ["p05"])[0]
PREP = InterviewPrep.model_validate(STUB_REPLIES["prep"] | {"persona_id": PERSONA.id})


@pytest.fixture
def config(tmp_path):
    return CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}}


def test_dry_run_interview_alternates_and_ends(config):
    transcript, stopped_by = run_interview(PERSONA, PREP, config, dry_run=True)

    assert stopped_by == "interviewer ended"
    speakers = [t.speaker for t in transcript.turns]
    assert speakers == ["interviewer", "user"] * 3
    assert [t.turn for t in transcript.turns] == [1, 2, 3, 4, 5, 6]


def test_transcript_on_disk_matches_memory(config):
    transcript, _ = run_interview(PERSONA, PREP, config, dry_run=True)
    assert Transcript.load(transcript.path) == transcript.turns


def test_each_turn_is_written_immediately(tmp_path):
    transcript = Transcript(tmp_path / "transcript.jsonl")
    transcript.add("interviewer", "First question?")
    assert len(transcript.path.read_text().splitlines()) == 1
    transcript.add("user", "First answer.")
    assert len(transcript.path.read_text().splitlines()) == 2


def test_user_talks_about_this_runs_task_without_the_hypothesis(config):
    run_interview(PERSONA, PREP, config, run=2, dry_run=True)
    calls = [json.loads(line) for line in (config["paths"]["runs"] / PERSONA.id / "run-2" / "calls.jsonl").open()]
    user_prompt = next(c for c in calls if c["agent"] == "user")["messages"][0]["content"]

    assert PERSONA.recent_tasks[1] in user_prompt
    assert PERSONA.recent_tasks[0] not in user_prompt
    assert PERSONA.job_hypothesis not in user_prompt


def test_turn_cap_stops_an_interviewer_that_never_ends(config, monkeypatch):
    def always_ask(agent, message, schema, *args, **kwargs):
        return InterviewerTurn(action="ask", question="And then what?")

    monkeypatch.setattr(orchestrator, "call_agent_json", always_ask)
    config = config | {"interview": {"max_interviewer_turns": 2}}

    transcript, stopped_by = run_interview(PERSONA, PREP, config, dry_run=True)

    assert stopped_by == "turn cap"
    assert [t.speaker for t in transcript.turns].count("interviewer") == 2


def test_ask_without_a_question_is_invalid():
    with pytest.raises(ValueError):
        parse_reply('{"action": "ask"}', InterviewerTurn)
    assert parse_reply('{"action": "end"}', InterviewerTurn).action == "end"
