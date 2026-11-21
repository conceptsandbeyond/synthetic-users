"""Isolation tests: each agent sees only what its allow-list permits.

The most important test in the repo. It runs real dry-run interviews and then
reads calls.jsonl, the exact prompts that went to the model, rather than
trusting what the code says it sends.
"""

import json

import pytest

from harness.context import IsolationError, build_context
from harness.orchestrator import load_config, load_personas, run_interview, run_prep

CONFIG = load_config()
PERSONAS = load_personas(CONFIG["paths"]["personas"])


def persona_text(persona) -> list[str]:
    """Everything about a persona that only the synthetic user may see."""
    return [persona.name, persona.location, *persona.behaviors, *persona.current_alternatives,
            *persona.objections, *persona.recent_tasks]


def prompts_sent_to(agent: str, log_dir) -> list[str]:
    """Every system prompt and message actually sent to `agent`, read from the log."""
    calls = [json.loads(line) for line in (log_dir / "calls.jsonl").read_text().splitlines()]
    return [c["system"] + "\n" + "\n".join(m["content"] for m in c["messages"])
            for c in calls if c["agent"] == agent]


@pytest.fixture
def config(tmp_path):
    return CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}}


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_interviewer_never_sees_persona_text(persona, config):
    prep = run_prep(persona, config, dry_run=True)
    run_interview(persona, prep, config, dry_run=True)

    prompts = prompts_sent_to("interviewer", config["paths"]["runs"] / persona.id / "run-1")
    assert prompts, "the interviewer was never called"
    for prompt in prompts:
        for secret in persona_text(persona):
            assert secret not in prompt, f"interviewer saw persona text: {secret!r}"


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_user_never_sees_the_prep_or_the_hypothesis(persona, config):
    prep = run_prep(persona, config, dry_run=True)
    run_interview(persona, prep, config, dry_run=True)

    prompts = prompts_sent_to("user", config["paths"]["runs"] / persona.id / "run-1")
    assert prompts, "the user was never called"
    for prompt in prompts:
        assert persona.job_hypothesis not in prompt
        assert "Interview prep:" not in prompt
        # Hypotheses are never said aloud, so they can't reach the user through the transcript either.
        for hypothesis in prep.key_hypotheses:
            assert hypothesis not in prompt


def test_prep_sees_the_segment_not_the_person(config):
    persona = PERSONAS[0]
    run_prep(persona, config, dry_run=True)
    (prompt,) = prompts_sent_to("prep", config["paths"]["runs"] / persona.id / "prep")
    assert persona.segment in prompt
    for secret in persona_text(persona):
        assert secret not in prompt


def test_unlisted_artifact_is_refused():
    with pytest.raises(IsolationError, match="may not see: persona_profile"):
        build_context("interviewer", CONFIG, prep=None, transcript=None, persona_profile=PERSONAS[0])


def test_missing_artifact_is_refused():
    with pytest.raises(IsolationError, match="needs: transcript"):
        build_context("interviewer", CONFIG, prep=None)


def test_unknown_agent_is_refused():
    with pytest.raises(IsolationError, match="no allow-list"):
        build_context("narrator", CONFIG)


def test_summary_artifact_never_reveals_the_whole_persona():
    """Passing a full Persona under persona_summary still sends only the summary."""
    persona = PERSONAS[0]
    prompt = build_context("prep", CONFIG, persona_summary=persona, question_bank="(guide)")
    for secret in persona_text(persona):
        assert secret not in prompt
