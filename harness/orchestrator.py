"""Module 1 entry point: run the prep agent for each persona.

This file grows into the full pipeline over the next modules. For now it does
one job: load personas, prepare an interview for each, and save the result.
The orchestrator is plain Python on purpose. Only the prep itself needs
judgment, so only the prep calls a model.

    python -m harness.orchestrator --dry-run --personas p01
"""

import argparse
import json
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

from harness.agents import call_agent
from harness.schemas import InterviewPrep, Persona

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path = REPO_ROOT / "config.yaml") -> dict:
    """Read config.yaml and turn its relative paths into absolute ones.

    Absolute paths mean the harness and the tests work no matter which
    folder you run them from.
    """
    config = yaml.safe_load(path.read_text())
    config["paths"] = {name: REPO_ROOT / p for name, p in config["paths"].items()}
    return config


def load_personas(personas_dir: Path, wanted: list[str] | None = None) -> list[Persona]:
    """Load persona files, or only those whose id starts with a wanted prefix like 'p01'."""
    personas = [Persona.model_validate_json(f.read_text()) for f in sorted(personas_dir.glob("*.json"))]
    if wanted:
        personas = [p for p in personas if any(p.id.startswith(w) for w in wanted)]
    return personas


def question_bank(segment: str, guide_path: Path) -> str:
    """Return the interview guide section for one segment.

    The prep agent gets only its own segment's questions. Handing it all ten
    guides would cost tokens and invite it to borrow questions that don't fit.
    """
    for section in re.split(r"(?m)^## ", guide_path.read_text())[1:]:
        heading = section.splitlines()[0]  # e.g. "1. Visually impaired DIYers"
        if heading.split(". ", 1)[-1].strip() == segment:
            return "## " + section.strip()
    raise ValueError(f"No interview guide section for segment {segment!r} in {guide_path}")


def run_prep(persona: Persona, config: dict, dry_run: bool = False) -> InterviewPrep:
    """Prepare one interview and save it to runs/<persona_id>/prep/prep.json."""
    # Built by hand for now. Module 4 moves prompt assembly into build_context(),
    # which enforces what each agent is allowed to see.
    user_message = (
        f"{persona.summary()}\n\n"
        f"Interview guide for this segment:\n\n{question_bank(persona.segment, config['paths']['question_bank'])}"
    )
    out_dir = config["paths"]["runs"] / persona.id / "prep"
    text = call_agent("prep", user_message, config, log_dir=out_dir, dry_run=dry_run)

    # The code already knows the persona id, so it adds it instead of asking the model.
    prep = InterviewPrep.model_validate({**json.loads(text), "persona_id": persona.id})
    (out_dir / "prep.json").write_text(prep.model_dump_json(indent=2))
    return prep


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the prep agent for each persona.")
    parser.add_argument("--dry-run", action="store_true", help="use the stub model: no API key, no cost")
    parser.add_argument("--personas", help="comma-separated id prefixes, e.g. p01,p05")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    config = load_config()
    wanted = args.personas.split(",") if args.personas else None
    for persona in load_personas(config["paths"]["personas"], wanted):
        prep = run_prep(persona, config, dry_run=args.dry_run)
        print(f"{persona.id}: {len(prep.starter_questions)} starter and "
              f"{len(prep.contrasting_questions)} contrasting questions -> runs/{persona.id}/prep/prep.json")


if __name__ == "__main__":
    main()
