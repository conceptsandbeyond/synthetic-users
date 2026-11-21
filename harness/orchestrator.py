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
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from harness.agents import AgentError, OutputInvalid, TokenMeter, call_agent, call_agent_json
from harness.context import build_context
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
    user_message = build_context(
        "prep", config,
        persona_summary=persona,
        question_bank=question_bank(persona.segment, config["paths"]["question_bank"]),
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


@dataclass
class Interview:
    """What one interview produced: the transcript, why it stopped, what it cost."""

    transcript: Transcript
    stopped_by: str
    tokens: int


def stop_rule_hit(transcript: Transcript, tokens_used: int, config: dict) -> str | None:
    """Return the name of the stop rule that fires now, or None to keep going.

    Checked before every interviewer turn. These rules protect the budget and
    catch interviews that have gone wrong. A healthy interview ends earlier,
    when the interviewer decides it has heard enough.
    """
    limits = config["interview"]
    questions = sum(t.speaker == "interviewer" for t in transcript.turns)
    if questions >= limits["max_interviewer_turns"]:
        return "turn cap"
    if tokens_used >= limits["token_budget_per_interview"]:
        return "token budget"
    answers = [t for t in transcript.turns if t.speaker == "user"][-limits["stall_answers"]:]
    if len(answers) == limits["stall_answers"] and all(
        len(t.text.split()) < limits["stall_min_words"] for t in answers
    ):
        return "stalled"
    return None


def run_interview(persona: Persona, prep: InterviewPrep, config: dict, run: int = 1,
                  dry_run: bool = False) -> Interview:
    """Run one interview until the interviewer ends it or a stop rule fires.

    The code relays every turn. The two agents never talk to each other
    directly: each call is built fresh by build_context() from what that
    agent is allowed to see.
    """
    run_dir = config["paths"]["runs"] / persona.id / f"run-{run}"
    transcript = Transcript(run_dir / "transcript.jsonl")
    meter = TokenMeter()
    # Each run talks about a different recent task. That's what makes repeat runs differ.
    task = persona.recent_tasks[(run - 1) % len(persona.recent_tasks)]

    while not (stopped_by := stop_rule_hit(transcript, meter.used, config)):
        move = call_agent_json(
            "interviewer", build_context("interviewer", config, prep=prep, transcript=transcript),
            InterviewerTurn, config, run_dir, dry_run, meter=meter,
        )
        if move.action == "end":
            stopped_by = "interviewer ended"
            break
        transcript.add("interviewer", move.question, meter.last_output_tokens)

        answer = call_agent(
            "user",
            build_context("user", config, persona_profile=persona, recent_task=task, transcript=transcript),
            config, run_dir, dry_run, meter,
        )
        transcript.add("user", answer, meter.last_output_tokens)

    summary = {"persona_id": persona.id, "run": run, "stopped_by": stopped_by,
               "turns": len(transcript.turns), "tokens": meter.used}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return Interview(transcript, stopped_by, meter.used)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prep and run one interview for each persona.")
    parser.add_argument("--dry-run", action="store_true", help="use the stub model: no API key, no cost")
    parser.add_argument("--personas", help="comma-separated id prefixes, e.g. p01,p05")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    config = load_config()
    wanted = args.personas.split(",") if args.personas else None
    personas = load_personas(config["paths"]["personas"], wanted)
    failed, total_tokens = [], 0
    for persona in personas:
        if total_tokens >= config["run_token_cap"]:
            print(f"{persona.id}: SKIPPED. The run has spent {total_tokens:,} tokens, over run_token_cap.")
            failed.append(persona.id)
            continue
        # One persona failing shouldn't stop the other nine.
        try:
            prep = run_prep(persona, config, dry_run=args.dry_run)
            interview = run_interview(persona, prep, config, dry_run=args.dry_run)
        except AgentError as error:
            failed.append(persona.id)
            print(f"{persona.id}: FAILED. {error}")
            continue
        total_tokens += interview.tokens
        print(f"{persona.id}: {len(interview.transcript.turns)} turns, stopped by {interview.stopped_by}, "
              f"{interview.tokens:,} tokens -> {interview.transcript.path.relative_to(REPO_ROOT)}")

    print(f"\n{len(personas) - len(failed)} of {len(personas)} interviews completed, "
          f"{total_tokens:,} interview tokens in total.")
    if failed:
        print(f"Not completed: {', '.join(failed)}. See failed.json and calls.jsonl in each persona's folders.")
        sys.exit(1)


if __name__ == "__main__":
    main()
