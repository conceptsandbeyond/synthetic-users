"""Schema tests: personas are valid, prep output is validated, and a bad reply is retried once.

All tests use the stub model, so they run without an API key and cost nothing.
"""

import json

import pytest
from pydantic import ValidationError

from harness import agents
from harness.orchestrator import load_config, load_personas, question_bank, run_prep
from harness.schemas import InterviewPrep, Persona

CONFIG = load_config()
PERSONAS = load_personas(CONFIG["paths"]["personas"])


def test_all_ten_personas_load_with_unique_ids():
    assert len(PERSONAS) == 10
    assert len({p.id for p in PERSONAS}) == 10


def test_each_persona_file_is_named_after_its_id():
    for path in CONFIG["paths"]["personas"].glob("*.json"):
        assert json.loads(path.read_text())["id"] == path.stem


def test_persona_rejects_unknown_fields():
    data = PERSONAS[0].model_dump() | {"nickname": "Marc"}
    with pytest.raises(ValidationError):
        Persona.model_validate(data)


def test_summary_shows_segment_and_job_only():
    """The prep agent plans for a segment, so the summary must not leak the person."""
    for p in PERSONAS:
        summary = p.summary()
        assert p.segment in summary and p.job_hypothesis in summary
        for private in [p.name, p.location, *p.behaviors, *p.objections, *p.current_alternatives, *p.recent_tasks]:
            assert private not in summary


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_every_segment_has_an_interview_guide(persona):
    section = question_bank(persona.segment, CONFIG["paths"]["question_bank"])
    assert "Contrasting questions" in section


def test_dry_run_prep_is_valid_and_logged(tmp_path):
    config = CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}}
    persona = PERSONAS[0]

    prep = run_prep(persona, config, dry_run=True)

    assert prep.persona_id == persona.id
    prep_dir = tmp_path / persona.id / "prep"
    assert (prep_dir / "prep.json").exists()
    calls = [json.loads(line) for line in (prep_dir / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == 1
    assert calls[0]["agent"] == "prep"
    assert persona.job_hypothesis in calls[0]["messages"][0]["content"]


# --- Module 2: validation and retry -----------------------------------------

VALID_PREP = json.dumps(agents.STUB_REPLIES["prep"])


def fake_model(monkeypatch, *replies):
    """Replace call_agent with a fake that returns `replies` in order.

    Returns the list of prompts it received, so tests can check what the
    retry actually told the model.
    """
    queue, prompts = list(replies), []

    def fake_call_agent(agent, user_message, config, log_dir, dry_run=False):
        prompts.append(user_message)
        return queue.pop(0)

    monkeypatch.setattr(agents, "call_agent", fake_call_agent)
    return prompts


def call_prep(tmp_path):
    return agents.call_agent_json("prep", "PREP REQUEST", InterviewPrep, CONFIG, tmp_path,
                                  known_fields={"persona_id": "p01"})


def test_valid_reply_needs_no_retry(monkeypatch, tmp_path):
    prompts = fake_model(monkeypatch, VALID_PREP)
    assert call_prep(tmp_path).persona_id == "p01"
    assert len(prompts) == 1


def test_code_fence_is_stripped_without_a_retry(monkeypatch, tmp_path):
    prompts = fake_model(monkeypatch, f"```json\n{VALID_PREP}\n```")
    call_prep(tmp_path)
    assert len(prompts) == 1


def test_retry_shows_the_model_its_reply_and_the_error(monkeypatch, tmp_path):
    prompts = fake_model(monkeypatch, "Sure! Here are some questions.", VALID_PREP)
    call_prep(tmp_path)
    assert len(prompts) == 2
    retry = prompts[1]
    assert retry.startswith("PREP REQUEST")
    assert "Sure! Here are some questions." in retry
    assert "Expecting value" in retry  # the JSON parser's error message


def test_valid_json_that_breaks_the_contract_is_retried(monkeypatch, tmp_path):
    too_few = json.loads(VALID_PREP) | {"starter_questions": ["Just one?"]}
    prompts = fake_model(monkeypatch, json.dumps(too_few), VALID_PREP)
    call_prep(tmp_path)
    assert "starter_questions" in prompts[1]


def test_second_failure_raises_with_both_replies(monkeypatch, tmp_path):
    fake_model(monkeypatch, "not json", "still not json")
    with pytest.raises(agents.OutputInvalid) as failure:
        call_prep(tmp_path)
    assert failure.value.replies == ["not json", "still not json"]


def test_failed_prep_is_saved_for_inspection(monkeypatch, tmp_path):
    fake_model(monkeypatch, "not json", "still not json")
    config = CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}}
    persona = PERSONAS[0]

    with pytest.raises(agents.OutputInvalid):
        run_prep(persona, config)

    failed = json.loads((tmp_path / persona.id / "prep" / "failed.json").read_text())
    assert failed["replies"] == ["not json", "still not json"]
    assert not (tmp_path / persona.id / "prep" / "prep.json").exists()
