"""Review and synthesis tests: the human gate decides what reaches synthesis.

Reviewer input is scripted, and the editor is a function that rewrites the file.
"""

import json

import pytest

from harness.agents import AgentError, OutputInvalid
from harness.orchestrator import (RunSpend, approved_runs, latest_attempts, load_config, load_personas,
                                  run_persona, run_synthesis)
from harness.render import BANNER
from harness.review import edit_debrief, pending_runs, review_run

CONFIG = load_config()


@pytest.fixture
def config(tmp_path):
    """Two personas, one run each, run on the stub."""
    config = CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}, "runs_per_persona": 1}
    for persona in load_personas(CONFIG["paths"]["personas"], ["p01", "p10"]):
        run_persona(persona, config, RunSpend(10**9), dry_run=True)
    return config


def answers(*replies):
    """A scripted reviewer: each call to ask() returns the next reply."""
    queue = list(replies)
    return lambda prompt: queue.pop(0)


def test_approve_and_reject_are_saved(config):
    first, second = pending_runs(config["paths"]["runs"])
    assert review_run(first, ask=answers("a", "")) == "approved"
    assert review_run(second, ask=answers("r", "Too agreeable")) == "rejected"
    assert json.loads((second / "review.json").read_text())["note"] == "Too agreeable"
    assert pending_runs(config["paths"]["runs"]) == []


def test_only_approved_runs_reach_synthesis(config):
    first, second = pending_runs(config["paths"]["runs"])
    review_run(first, ask=answers("a", ""))
    review_run(second, ask=answers("r", "No"))
    (debrief, critique), = approved_runs(config["paths"]["runs"])
    assert debrief.persona_id == critique.persona_id == first.parent.name


def test_flagged_runs_are_reviewed_first(config):
    runs = config["paths"]["runs"]
    last = latest_attempts(runs)[-1]
    summary = json.loads((last / "summary.json").read_text()) | {"flagged": True}
    (last / "summary.json").write_text(json.dumps(summary))
    assert pending_runs(runs)[0] == last


def test_a_valid_edit_is_kept_and_rendered(config):
    run_dir = pending_runs(config["paths"]["runs"])[0]

    def rename_role(path):
        path.write_text(json.dumps(json.loads(path.read_text()) | {"occupation_role": "Retired teacher"}))

    assert review_run(run_dir, ask=answers("e", "a", ""), edit=rename_role) == "approved"
    assert "Retired teacher" in (run_dir / "debrief.md").read_text()
    assert json.loads((run_dir / "review.json").read_text())["edited"] is True


def test_an_edit_that_breaks_the_evidence_is_undone(config):
    run_dir = pending_runs(config["paths"]["runs"])[0]
    before = (run_dir / "debrief.json").read_text()

    def cite_a_question(path):
        data = json.loads(path.read_text())
        data["main_insights"][0]["evidence_turns"] = [1]  # turn 1 is the interviewer's question
        path.write_text(json.dumps(data))

    assert edit_debrief(run_dir, cite_a_question) is False
    assert (run_dir / "debrief.json").read_text() == before


def test_synthesis_needs_approvals(config):
    with pytest.raises(AgentError, match="No approved debriefs"):
        run_synthesis(config, dry_run=True)


def test_synthesis_report_from_approved_runs(config):
    for run_dir in pending_runs(config["paths"]["runs"]):
        review_run(run_dir, ask=answers("a", ""))

    report = run_synthesis(config, dry_run=True)

    out_dir = config["paths"]["runs"] / "synthesis"
    assert report.strongest_segment.persona_id == "p01-visually-impaired-diyer"
    assert (out_dir / "report.md").read_text().startswith(BANNER)
    (call,) = [json.loads(line) for line in (out_dir / "calls.jsonl").open()]
    prompt = call["messages"][0]["content"]
    assert prompt.startswith("Approved debriefs:")
    assert "Transcript:" not in prompt  # synthesis never sees a transcript


def test_synthesis_may_not_cite_an_unapproved_persona(config):
    p01_run = [d for d in pending_runs(config["paths"]["runs"]) if d.parent.name.startswith("p01")][0]
    review_run(p01_run, ask=answers("a", ""))
    # The stub report also cites p10, which wasn't approved: rejected, retried, rejected again.
    with pytest.raises(OutputInvalid, match="have no approved debrief"):
        run_synthesis(config, dry_run=True)
