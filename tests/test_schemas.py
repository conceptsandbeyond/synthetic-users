"""Module 1 tests: the persona files are valid and a dry-run prep produces a valid Interview Prep.

All tests use the stub model, so they run without an API key and cost nothing.
"""

import json

import pytest
from pydantic import ValidationError

from harness.orchestrator import load_config, load_personas, question_bank, run_prep
from harness.schemas import Persona

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
        for private in [p.name, p.location, *p.behaviors, *p.objections, *p.current_alternatives]:
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
