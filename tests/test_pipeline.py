"""Pipeline tests: debrief, evidence checks, repeat runs, parallel personas and rendering.

All on the stub model, no API key needed.
"""

import json
import sys

import pytest

from harness import agents, orchestrator
from harness.agents import STUB_REPLIES
from harness.orchestrator import RunSpend, load_config, load_personas, run_persona
from harness.render import BANNER
from harness.schemas import UserDebrief, check_evidence
from harness.transcript import Transcript

CONFIG = load_config()
PERSONA = load_personas(CONFIG["paths"]["personas"], ["p03"])[0]


@pytest.fixture
def config(tmp_path):
    return CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}}


def debrief_citing(turns: list[int]) -> UserDebrief:
    data = STUB_REPLIES["debrief"] | {"persona_id": "p03", "run": 1, "name": "Priya Nair"}
    data["most_pressing_needs"] = [{"need": "x", "evidence_turns": turns}]
    return UserDebrief.model_validate(data)


def six_turns(tmp_path) -> list:
    transcript = Transcript(tmp_path / "t.jsonl")
    for n in range(3):
        transcript.add("interviewer", f"Question {n}?")
        transcript.add("user", f"Answer {n}.")
    return transcript.turns


def test_three_runs_each_get_a_transcript_and_a_debrief(config):
    results = run_persona(PERSONA, config, RunSpend(10**9), dry_run=True)

    assert [ok for ok, _ in results] == [True, True, True]
    persona_dir = config["paths"]["runs"] / PERSONA.id
    for run in (1, 2, 3):
        debrief = UserDebrief.model_validate_json((persona_dir / f"run-{run}" / "debrief.json").read_text())
        assert (debrief.persona_id, debrief.run, debrief.name) == (PERSONA.id, run, PERSONA.name)


def test_every_rendered_file_starts_with_the_banner(config):
    run_persona(PERSONA, config, RunSpend(10**9), dry_run=True)
    rendered = list(config["paths"]["runs"].rglob("*.md"))
    assert len(rendered) == 4  # one prep, three debriefs
    for path in rendered:
        assert path.read_text().startswith(BANNER)


def test_debrief_sees_the_transcript_and_nothing_else(config):
    run_persona(PERSONA, config, RunSpend(10**9), dry_run=True)
    calls = [json.loads(line) for line in (config["paths"]["runs"] / PERSONA.id / "run-1" / "calls.jsonl").open()]
    (prompt,) = [c["messages"][0]["content"] for c in calls if c["agent"] == "debrief"]
    assert prompt.startswith("Transcript:")
    for secret in [PERSONA.name, PERSONA.job_hypothesis, PERSONA.segment, *PERSONA.objections]:
        assert secret not in prompt


def test_evidence_must_point_at_an_answer(tmp_path):
    turns = six_turns(tmp_path)
    check_evidence(debrief_citing([2, 4]), turns)  # answers: fine
    with pytest.raises(ValueError, match=r"\[3\] are not interviewee answers"):
        check_evidence(debrief_citing([3]), turns)  # a question
    with pytest.raises(ValueError, match=r"\[99\]"):
        check_evidence(debrief_citing([99]), turns)  # doesn't exist


def test_bad_evidence_gets_the_retry(config, monkeypatch):
    bad = json.loads(json.dumps(STUB_REPLIES["debrief"]))
    bad["main_insights"][0]["evidence_turns"] = [99]
    debrief_replies = [json.dumps(bad), json.dumps(STUB_REPLIES["debrief"])]
    real_call_agent = agents.call_agent

    def fake(agent, *args, **kwargs):
        return debrief_replies.pop(0) if agent == "debrief" else real_call_agent(agent, *args, **kwargs)

    monkeypatch.setattr(agents, "call_agent", fake)
    results = run_persona(PERSONA, config | {"runs_per_persona": 1}, RunSpend(10**9), dry_run=True)

    assert results[0][0] is True
    assert debrief_replies == []  # both replies were used: the bad one, then the retry


def test_run_token_cap_skips_the_remaining_runs(config):
    spend = RunSpend(cap=1)  # the first interview spends more than this
    results = run_persona(PERSONA, config, spend, dry_run=True)
    assert [ok for ok, _ in results] == [True, False, False]
    assert "SKIPPED" in results[1][1]


def test_main_runs_personas_in_parallel(config, monkeypatch, capsys):
    monkeypatch.setattr(orchestrator, "load_config", lambda: config | {"runs_per_persona": 1})
    monkeypatch.setattr(sys, "argv", ["orchestrator", "--dry-run", "--personas", "p01,p02,p03"])
    orchestrator.main()
    assert "3 of 3 runs completed" in capsys.readouterr().out
