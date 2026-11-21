"""The orchestrator: prep, interview, debrief and critique every persona, then synthesize.

This file grows into the full pipeline over the modules. It is plain Python
on purpose. The code decides who speaks next, what each agent sees and when
to stop. Only the steps that need judgment call a model.

    python -m harness.orchestrator --dry-run --personas p01
"""

import argparse
import json
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from harness.agents import AgentError, OutputInvalid, TokenMeter, call_agent, call_agent_json
from harness.checks import check_questions
from harness.context import build_context
from harness.render import render_debrief, render_prep, render_synthesis
from harness.schemas import (Critique, InterviewerTurn, InterviewPrep, Persona, SynthesisReport, UserDebrief,
                             check_evidence, check_persona_ids, describe_error)
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


def fresh_dir(path: Path) -> Path:
    """Empty a folder before a step writes to it, so old logs never mix with new ones."""
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def save_failure(out_dir: Path, failure: OutputInvalid) -> None:
    """Save both bad replies and the error, so you can see exactly what went wrong."""
    failed = {"error": describe_error(failure.error), "replies": failure.replies}
    (out_dir / f"failed-{failure.agent}.json").write_text(json.dumps(failed, indent=2))


def run_prep(persona: Persona, config: dict, dry_run: bool = False) -> InterviewPrep:
    """Prepare one interview and save it as prep.json and prep.md."""
    out_dir = fresh_dir(config["paths"]["runs"] / persona.id / "prep")
    user_message = build_context(
        "prep", config,
        persona_summary=persona,
        question_bank=question_bank(persona.segment, config["paths"]["question_bank"]),
    )
    try:
        # The code already knows the persona id, so it adds it instead of asking the model.
        prep = call_agent_json("prep", user_message, InterviewPrep, config, out_dir, dry_run,
                               known_fields={"persona_id": persona.id})
    except OutputInvalid as failure:
        save_failure(out_dir, failure)
        raise
    (out_dir / "prep.json").write_text(prep.model_dump_json(indent=2))
    (out_dir / "prep.md").write_text(render_prep(prep))
    return prep


@dataclass
class Interview:
    """What one interview produced: the transcript, why it stopped, what it cost."""

    run: int
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
                  dry_run: bool = False, rerun: bool = False) -> Interview:
    """Run one interview until the interviewer ends it or a stop rule fires.

    The code relays every turn. The two agents never talk to each other
    directly: each call is built fresh by build_context() from what that
    agent is allowed to see.
    """
    run_dir = fresh_dir(config["paths"]["runs"] / persona.id / f"run-{run}{'-rerun' if rerun else ''}")
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
    return Interview(run, transcript, stopped_by, meter.used)


def run_debrief(persona: Persona, interview: Interview, config: dict, dry_run: bool = False) -> UserDebrief:
    """Debrief one interview from its transcript alone, and save it as debrief.json and debrief.md.

    The debrief agent never sees the persona, so it reports what was said,
    not what the profile claims. The code adds the name, which it already knows.
    """
    run_dir = interview.transcript.path.parent
    turns = interview.transcript.turns
    try:
        debrief = call_agent_json(
            "debrief", build_context("debrief", config, transcript=interview.transcript),
            UserDebrief, config, run_dir, dry_run,
            known_fields={"persona_id": persona.id, "run": interview.run, "name": persona.name},
            check=lambda d: check_evidence(d, turns),
        )
    except OutputInvalid as failure:
        save_failure(run_dir, failure)
        raise
    (run_dir / "debrief.json").write_text(debrief.model_dump_json(indent=2))
    (run_dir / "debrief.md").write_text(render_debrief(debrief, turns))
    return debrief


class RunSpend:
    """Tokens spent by the whole run, shared safely between persona threads."""

    def __init__(self, cap: int):
        self.cap, self.spent, self._lock = cap, 0, threading.Lock()

    def add(self, tokens: int) -> None:
        with self._lock:
            self.spent += tokens

    def over_cap(self) -> bool:
        return self.spent >= self.cap


@dataclass
class RunResult:
    """One interview and its debrief."""

    interview: Interview
    debrief: UserDebrief


def run_once(persona: Persona, prep: InterviewPrep, config: dict, run: int, spend: RunSpend,
             dry_run: bool = False, rerun: bool = False) -> RunResult:
    """Interview and debrief once."""
    interview = run_interview(persona, prep, config, run, dry_run, rerun)
    spend.add(interview.tokens)
    return RunResult(interview, run_debrief(persona, interview, config, dry_run))


def run_critique(persona: Persona, result: RunResult, others: list[UserDebrief], config: dict,
                 dry_run: bool = False) -> Critique:
    """Run the interviewer check and the devil's advocate on one run, and save both."""
    run_dir = result.interview.transcript.path.parent
    flagged_questions = check_questions(result.interview.transcript.turns)
    (run_dir / "interviewer_check.json").write_text(json.dumps(flagged_questions, indent=2))
    try:
        critique = call_agent_json(
            "advocate",
            build_context("advocate", config, persona=persona, transcript=result.interview.transcript,
                          debrief=result.debrief, other_debriefs=others),
            Critique, config, run_dir, dry_run,
            known_fields={"persona_id": persona.id, "run": result.interview.run},
        )
    except OutputInvalid as failure:
        save_failure(run_dir, failure)
        raise
    (run_dir / "critique.json").write_text(critique.model_dump_json(indent=2))
    return critique


def evaluate_run(persona: Persona, prep: InterviewPrep, result: RunResult, others: list[UserDebrief],
                 config: dict, spend: RunSpend, dry_run: bool = False) -> str:
    """Critique one run. A low rating gets one rerun; a second low is flagged for human review.

    One rerun, not a loop: if the same persona fails twice, the problem is
    probably the persona or the prompts, and a person should look.
    """
    critique = run_critique(persona, result, others, config, dry_run)
    reran = critique.confidence == "low" and not spend.over_cap()
    if reran:
        result = run_once(persona, prep, config, result.interview.run, spend, dry_run, rerun=True)
        critique = run_critique(persona, result, others, config, dry_run)
    flagged = critique.confidence == "low"

    summary_path = result.interview.transcript.path.parent / "summary.json"
    summary = json.loads(summary_path.read_text()) | {"confidence": critique.confidence, "flagged": flagged}
    summary_path.write_text(json.dumps(summary, indent=2))
    interview = result.interview
    return (f"{persona.id} run {interview.run}{' (rerun)' if reran else ''}: {len(interview.transcript.turns)} "
            f"turns, stopped by {interview.stopped_by}, confidence {critique.confidence}"
            f"{', FLAGGED for review' if flagged else ''}")


def run_persona(persona: Persona, config: dict, spend: RunSpend, dry_run: bool = False) -> list[tuple[bool, str]]:
    """Prep once, interview and debrief each run, then critique every run.

    Returns (succeeded, message) for each run. Critiques wait until all runs
    are done, so the consistency check can compare each run with the others.
    """
    try:
        prep = run_prep(persona, config, dry_run)
    except AgentError as error:
        return [(False, f"{persona.id} prep: FAILED. {error}")]

    messages, results = [], {}
    for run in range(1, config["runs_per_persona"] + 1):
        if spend.over_cap():
            messages.append((False, f"{persona.id} run {run}: SKIPPED. The run has spent {spend.spent:,} tokens."))
            continue
        try:
            results[run] = run_once(persona, prep, config, run, spend, dry_run)
        except AgentError as error:
            messages.append((False, f"{persona.id} run {run}: FAILED. {error}"))

    for run, result in results.items():
        others = [r.debrief for n, r in results.items() if n != run]
        try:
            messages.append((True, evaluate_run(persona, prep, result, others, config, spend, dry_run)))
        except AgentError as error:
            messages.append((False, f"{persona.id} run {run} critique: FAILED. {error}"))
    return messages


def latest_attempts(runs_dir: Path) -> list[Path]:
    """Return the folder of the latest attempt of every critiqued run: the rerun if there was one."""
    attempts = []
    for run_dir in sorted(runs_dir.glob("p*/run-*")):
        if run_dir.name.endswith("-rerun"):
            continue
        rerun = run_dir.with_name(run_dir.name + "-rerun")
        latest = rerun if rerun.exists() else run_dir
        if (latest / "critique.json").exists():
            attempts.append(latest)
    return attempts


def approved_runs(runs_dir: Path) -> list[tuple[UserDebrief, Critique]]:
    """Load the debrief and critique of every run a person approved in review.py."""
    approved = []
    for run_dir in latest_attempts(runs_dir):
        review = run_dir / "review.json"
        if review.exists() and json.loads(review.read_text())["decision"] == "approved":
            approved.append((UserDebrief.model_validate_json((run_dir / "debrief.json").read_text()),
                             Critique.model_validate_json((run_dir / "critique.json").read_text())))
    return approved


def run_synthesis(config: dict, dry_run: bool = False) -> SynthesisReport:
    """Compare approved runs across segments and save report.json and report.md.

    Only debriefs a person approved get here. Nothing the human gate rejected
    or skipped can shape the conclusions.
    """
    approved = approved_runs(config["paths"]["runs"])
    if not approved:
        raise AgentError("No approved debriefs yet. Run python -m harness.review first.")
    debriefs, critiques = [d for d, _ in approved], [c for _, c in approved]
    out_dir = fresh_dir(config["paths"]["runs"] / "synthesis")
    try:
        report = call_agent_json(
            "synthesis", build_context("synthesis", config, approved_debriefs=debriefs, critiques=critiques),
            SynthesisReport, config, out_dir, dry_run,
            check=lambda r: check_persona_ids(r, {d.persona_id for d in debriefs}),
        )
    except OutputInvalid as failure:
        save_failure(out_dir, failure)
        raise
    (out_dir / "report.json").write_text(report.model_dump_json(indent=2))
    (out_dir / "report.md").write_text(render_synthesis(report, len(debriefs)))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Prep, interview, debrief and critique each persona.")
    parser.add_argument("--dry-run", action="store_true", help="use the stub model: no API key, no cost")
    parser.add_argument("--personas", help="comma-separated id prefixes, e.g. p01,p05")
    parser.add_argument("--synthesize", action="store_true", help="after review: compare the approved debriefs")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    config = load_config()
    if args.synthesize:
        try:
            run_synthesis(config, dry_run=args.dry_run)
        except AgentError as error:
            sys.exit(str(error))
        print(f"Synthesis saved to {(config['paths']['runs'] / 'synthesis' / 'report.md').relative_to(REPO_ROOT)}")
        return

    wanted = args.personas.split(",") if args.personas else None
    personas = load_personas(config["paths"]["personas"], wanted)
    spend = RunSpend(config["run_token_cap"])

    # Personas are independent, so they run in parallel. Runs of one persona stay in order.
    results = []
    with ThreadPoolExecutor(max_workers=config["parallel_personas"]) as pool:
        jobs = [pool.submit(run_persona, p, config, spend, args.dry_run) for p in personas]
        for job in as_completed(jobs):
            for ok, message in job.result():
                print(message)
                results.append(ok)

    print(f"\n{sum(results)} of {len(results)} runs completed, {spend.spent:,} interview tokens in total.")
    print("Next: review the debriefs with python -m harness.review")
    if not all(results):
        print("Some runs failed. Look for failed-<agent>.json and calls.jsonl in the folders named above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
