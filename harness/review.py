"""The human review gate: approve, reject or edit each debrief before synthesis.

Agents check agents up to a point. A person decides what counts as a finding.
Only runs approved here reach the synthesis agent.

    python -m harness.review
"""

import json
import os
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from harness.orchestrator import latest_attempts, load_config
from harness.render import render_debrief
from harness.schemas import Critique, UserDebrief, check_evidence, describe_error
from harness.transcript import Transcript


def pending_runs(runs_dir: Path) -> list[Path]:
    """Runs with no review yet, flagged ones first so they get fresh eyes."""
    pending = [d for d in latest_attempts(runs_dir) if not (d / "review.json").exists()]
    return sorted(pending, key=lambda d: not json.loads((d / "summary.json").read_text()).get("flagged"))


def show(run_dir: Path) -> None:
    """Print what a reviewer needs: the debrief, the critique and the interviewer check."""
    summary = json.loads((run_dir / "summary.json").read_text())
    critique = Critique.model_validate_json((run_dir / "critique.json").read_text())
    flags = json.loads((run_dir / "interviewer_check.json").read_text())

    print("=" * 72)
    if summary.get("flagged"):
        print("FLAGGED: the devil's advocate rated this run low, and low again on the rerun.\n")
    print((run_dir / "debrief.md").read_text())
    print(f"Devil's advocate: confidence {critique.confidence}")
    print("  " + ", ".join(f"{name} {rating}" for name, rating in critique.checks.model_dump().items()))
    print(f"  {critique.summary}")
    for claim in critique.unsupported_claims:
        print(f"  Unsupported: {claim}")
    print(f"Interviewer check: {len(flags)} question(s) flagged")
    for flag in flags:
        print(f"  Turn {flag['turn']} ({', '.join(flag['flags'])}): {flag['question']}")
    print(f"Transcript: {run_dir / 'transcript.jsonl'}\n")


def open_in_editor(path: Path) -> None:
    subprocess.run([os.environ.get("EDITOR", "nano"), str(path)], check=False)


def edit_debrief(run_dir: Path, edit: Callable[[Path], None]) -> bool:
    """Let the reviewer edit debrief.json, then validate it the same way as the agent's output.

    A person's edit gets no free pass: if it breaks the schema or cites a
    turn that isn't an answer, the edit is undone.
    """
    path = run_dir / "debrief.json"
    before = path.read_text()
    edit(path)
    turns = Transcript.load(run_dir / "transcript.jsonl")
    try:
        debrief = UserDebrief.model_validate_json(path.read_text())
        check_evidence(debrief, turns)
    except ValueError as error:
        path.write_text(before)
        print(f"That edit doesn't validate, so it was undone:\n{describe_error(error)}")
        return False
    (run_dir / "debrief.md").write_text(render_debrief(debrief, turns))
    return True


def review_run(run_dir: Path, ask: Callable[[str], str] = input,
               edit: Callable[[Path], None] = open_in_editor) -> str:
    """Ask for a decision on one run and save it to review.json. Returns the choice made.

    TODO (module 8): build the decision loop. Keep asking until the reviewer decides:
      - "a" or "r": ask for a note ("Note (optional): " or "Why reject it? "), write
        review.json with decision ("approved" or "rejected"), edited, note and ts,
        then return the decision.
      - "e": call edit_debrief(run_dir, edit) and remember whether an edit was
        saved, so review.json can record it. Then ask again.
      - "s": return "skipped". "q": return "quit".
    Read only the first letter of each answer, lowercased.
    """
    raise NotImplementedError("Module 8: build review_run()")


def main() -> None:
    runs_dir = load_config()["paths"]["runs"]
    pending = pending_runs(runs_dir)
    print(f"{len(pending)} run(s) waiting for review.\n")
    for run_dir in pending:
        show(run_dir)
        if review_run(run_dir) == "quit":
            break

    approved = sum(json.loads((d / "review.json").read_text())["decision"] == "approved"
                   for d in latest_attempts(runs_dir) if (d / "review.json").exists())
    print(f"\n{approved} run(s) approved so far.")
    if approved:
        print("Next: python -m harness.orchestrator --synthesize")


if __name__ == "__main__":
    main()
