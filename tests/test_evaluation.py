"""Evaluation tests: the devil's advocate, the rerun rule, the interviewer check and the search tool.

All on the stub model or fakes, no API key needed.
"""

import json
from types import SimpleNamespace

import pytest

from harness import agents
from harness.agents import STUB_REPLIES, call_agent
from harness.checks import check_questions
from harness.orchestrator import RunSpend, load_config, load_personas, run_persona
from harness.schemas import Critique
from harness.transcript import Transcript

CONFIG = load_config()
PERSONA = load_personas(CONFIG["paths"]["personas"], ["p10"])[0]
LOW = STUB_REPLIES["advocate"] | {"confidence": "low"}


@pytest.fixture
def config(tmp_path):
    return CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}, "runs_per_persona": 2}


def calls_in(run_dir) -> list[dict]:
    return [json.loads(line) for line in (run_dir / "calls.jsonl").open()]


def test_every_run_gets_a_critique_and_an_interviewer_check(config):
    run_persona(PERSONA, config, RunSpend(10**9), dry_run=True)
    for run in (1, 2):
        run_dir = config["paths"]["runs"] / PERSONA.id / f"run-{run}"
        critique = Critique.model_validate_json((run_dir / "critique.json").read_text())
        assert (critique.persona_id, critique.run) == (PERSONA.id, run)
        assert json.loads((run_dir / "interviewer_check.json").read_text()) == []
        assert json.loads((run_dir / "summary.json").read_text())["flagged"] is False


def test_advocate_sees_everything_including_the_other_runs(config):
    run_persona(PERSONA, config, RunSpend(10**9), dry_run=True)
    run_dir = config["paths"]["runs"] / PERSONA.id / "run-1"
    (prompt,) = [c["messages"][0]["content"] for c in calls_in(run_dir) if c["agent"] == "advocate"]
    assert PERSONA.job_hypothesis in prompt
    assert "Transcript:" in prompt and "Debrief of this run:" in prompt
    assert '"run": 2' in prompt  # run 2's debrief, for the consistency check


def test_only_the_advocate_gets_a_tool(config):
    run_persona(PERSONA, config, RunSpend(10**9), dry_run=True)
    for call in calls_in(config["paths"]["runs"] / PERSONA.id / "run-1"):
        assert call["tools"] == (["web_search"] if call["agent"] == "advocate" else [])


def replay_for(agent: str, replies: list[dict]):
    """Return a stub picker that plays `replies` in order for one agent and leaves the rest alone."""
    real_pick = agents._pick_stub_reply
    queue = list(replies)

    def pick(name, prompt):
        return json.dumps(queue.pop(0)) if name == agent else real_pick(name, prompt)

    return pick


def test_one_low_rating_gets_one_rerun(config, monkeypatch):
    # Low on the first critique, medium on the rerun.
    monkeypatch.setattr(agents, "_pick_stub_reply", replay_for("advocate", [LOW, STUB_REPLIES["advocate"]]))
    results = run_persona(PERSONA, config | {"runs_per_persona": 1}, RunSpend(10**9), dry_run=True)

    assert "(rerun)" in results[0][1] and "FLAGGED" not in results[0][1]
    rerun_dir = config["paths"]["runs"] / PERSONA.id / "run-1-rerun"
    assert json.loads((rerun_dir / "summary.json").read_text())["flagged"] is False


def test_two_low_ratings_are_flagged_for_review(config, monkeypatch):
    monkeypatch.setattr(agents, "_pick_stub_reply", replay_for("advocate", [LOW, LOW]))
    results = run_persona(PERSONA, config | {"runs_per_persona": 1}, RunSpend(10**9), dry_run=True)

    assert "FLAGGED for review" in results[0][1]
    rerun_dir = config["paths"]["runs"] / PERSONA.id / "run-1-rerun"
    assert json.loads((rerun_dir / "summary.json").read_text())["flagged"] is True


@pytest.mark.parametrize("question, flags", [
    ("Tell me about the last time you hung a picture.", []),
    ("What happened next?", []),
    ("Wouldn't it be easier with a tool that beeps?", ["leading"]),
    ("That must have been frustrating?", ["leading"]),
    ("Would you buy a level that talks?", ["future"]),
    ("If there were an app for this, how likely are you to use it?", ["future"]),
])
def test_interviewer_check(tmp_path, question, flags):
    transcript = Transcript(tmp_path / "t.jsonl")
    transcript.add("interviewer", question)
    transcript.add("user", "Would you believe it took an hour?")  # answers are never checked
    found = check_questions(transcript.turns)
    assert (found[0]["flags"] if found else []) == flags


def fake_client(*responses):
    """A client whose messages.create() returns `responses` in order and records each request."""
    requests = []

    def create(**request):
        requests.append(request)
        return responses[len(requests) - 1]

    return SimpleNamespace(messages=SimpleNamespace(create=create)), requests


def block(type_, text=""):
    return SimpleNamespace(type=type_, text=text)


def reply(stop_reason, *content, tokens=10):
    return SimpleNamespace(model="fake", stop_reason=stop_reason, content=list(content),
                           usage=SimpleNamespace(input_tokens=tokens, output_tokens=tokens))


def test_a_paused_search_is_resumed_and_only_the_final_answer_is_kept(tmp_path, monkeypatch):
    client, requests = fake_client(
        reply("pause_turn", block("text", "Let me search."), block("server_tool_use")),
        reply("end_turn", block("web_search_tool_result"), block("text", '{"answer": 1}')),
    )
    monkeypatch.setattr(agents, "_real_client", lambda: client)

    text = call_agent("advocate", "Critique this.", CONFIG, tmp_path)

    assert text == '{"answer": 1}'  # the note before the search is dropped
    assert len(requests) == 2
    resumed = requests[1]["messages"]
    assert resumed[-1]["role"] == "assistant" and len(resumed[-1]["content"]) == 2
    assert requests[0]["tools"][0]["name"] == "web_search"
    assert calls_in(tmp_path)[0]["input_tokens"] == 20  # both requests are counted
