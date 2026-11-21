"""The orchestrator: prep an interview, then run it, for each persona.

This file grows into the full pipeline over the modules. It is plain Python
on purpose. The code decides who speaks next, what each agent sees and when
to stop. Only the steps that need judgment call a model.

    python -m harness.orchestrator --dry-run --personas p01
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from harness.agents import AgentError, OutputInvalid, call_agent, call_agent_json
from harness.schemas import InterviewerTurn, InterviewPrep, Persona, describe_error
from harness.transcript import Transcript

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
    """Prepare one interview and save it to runs/<persona_id>/prep/prep.json.

    If the reply fails validation twice, save both replies and the error to
    failed.json so you can see exactly what went wrong, then re-raise.
    """
    # Built by hand for now. Module 4 moves prompt assembly into build_context(),
    # which enforces what each agent is allowed to see.
    user_message = (
        f"{persona.summary()}\n\n"
        f"Interview guide for this segment:\n\n{question_bank(persona.segment, config['paths']['question_bank'])}"
    )
    out_dir = config["paths"]["runs"] / persona.id / "prep"
    try:
        # The code already knows the persona id, so it adds it instead of asking the model.
        prep = call_agent_json("prep", user_message, InterviewPrep, config, out_dir, dry_run,
                               known_fields={"persona_id": persona.id})
    except OutputInvalid as failure:
        failed = {"error": describe_error(failure.error), "replies": failure.replies}
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "failed.json").write_text(json.dumps(failed, indent=2))
        raise
    (out_dir / "failed.json").unlink(missing_ok=True)  # clear a failure from an earlier run
    (out_dir / "prep.json").write_text(prep.model_dump_json(indent=2))
    return prep


def run_interview(persona: Persona, prep: InterviewPrep, config: dict, run: int = 1,
                  dry_run: bool = False) -> tuple[Transcript, str]:
    """Run one interview and return the transcript and the reason it stopped.

    The code relays every turn. The two agents never talk to each other
    directly: each call is built fresh from what that agent is allowed to see.
    """
    run_dir = config["paths"]["runs"] / persona.id / f"run-{run}"
    transcript = Transcript(run_dir / "transcript.jsonl")
    # Each run talks about a different recent task. That's what makes repeat runs differ.
    task = persona.recent_tasks[(run - 1) % len(persona.recent_tasks)]
    prep_text = prep.model_dump_json(indent=2, exclude={"persona_id"})
    # The user never sees the job hypothesis: knowing what's being tested invites it to confirm it.
    profile = persona.model_dump_json(indent=2, exclude={"id", "job_hypothesis", "recent_tasks"})

    # TODO (module 3): write the relay loop. Repeat at most
    # config["interview"]["max_interviewer_turns"] times:
    #   1. Ask the interviewer for its next move with call_agent_json("interviewer", ...,
    #      InterviewerTurn, config, run_dir, dry_run). Its message holds prep_text and
    #      transcript.render(), under the headings "Interview prep:" and "Transcript so far:".
    #   2. If move.action is "end", return transcript, "interviewer ended".
    #   3. Otherwise add move.question to the transcript as the "interviewer".
    #   4. Ask the user for an answer with call_agent("user", ..., config, run_dir, dry_run).
    #      Its message holds profile, task and transcript.render(), under the headings
    #      "Your profile:", "The recent task this interview is about:" and "Transcript so far:".
    #   5. Add the answer to the transcript as the "user".
    # If the loop runs out of turns, return transcript, "turn cap".
    raise NotImplementedError("Module 3: build the relay loop in run_interview()")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prep and run one interview for each persona.")
    parser.add_argument("--dry-run", action="store_true", help="use the stub model: no API key, no cost")
    parser.add_argument("--personas", help="comma-separated id prefixes, e.g. p01,p05")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    config = load_config()
    wanted = args.personas.split(",") if args.personas else None
    personas = load_personas(config["paths"]["personas"], wanted)
    failed = []
    for persona in personas:
        # One persona failing shouldn't stop the other nine.
        try:
            prep = run_prep(persona, config, dry_run=args.dry_run)
            transcript, stopped_by = run_interview(persona, prep, config, dry_run=args.dry_run)
        except AgentError as error:
            failed.append(persona.id)
            print(f"{persona.id}: FAILED. {error}")
            continue
        print(f"{persona.id}: {len(transcript.turns)} turns, stopped by {stopped_by} -> {transcript.path.relative_to(REPO_ROOT)}")

    print(f"\n{len(personas) - len(failed)} of {len(personas)} interviews completed.")
    if failed:
        print(f"Failed: {', '.join(failed)}. See failed.json and calls.jsonl in each persona's folders.")
        sys.exit(1)


if __name__ == "__main__":
    main()
