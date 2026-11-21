# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 8: human in the loop

**Goal.** Put a person between the agents and the conclusions. `review.py` shows each run's debrief, critique and interviewer check, and the reviewer approves, rejects or edits it. Only approved debriefs reach the synthesis agent, which compares segments and lists what real interviews have to verify.

Earlier modules' READMEs are on their `module-NN-solution` branches.

**Files that change**

| File | What changes |
| --- | --- |
| `harness/review.py` | New. The review command line: `pending_runs()`, `show()`, `review_run()` and `edit_debrief()`. Flagged runs come first. Decisions go to `review.json`. |
| `prompts/synthesis.md` | New. Compares approved debriefs, weighted by their critiques. |
| `harness/schemas.py` | New `SynthesisReport`, plus `check_persona_ids()`: the report may cite only personas with an approved debrief. |
| `harness/orchestrator.py` | New `latest_attempts()`, `approved_runs()` and `run_synthesis()`, and a `--synthesize` flag. |
| `harness/render.py`, `harness/context.py`, `config.yaml` | The synthesis report renderer, its two artifacts and its allow-list. |
| `tests/test_review.py` | New tests for approving, rejecting, editing, review order and synthesis. |

**Run it**

```bash
python -m harness.orchestrator --dry-run --personas p01,p10
python -m harness.review
python -m harness.orchestrator --dry-run --synthesize
```

`edit` opens `debrief.json` in `$EDITOR` (nano if unset). An edit has to pass the same schema and evidence checks as the agent's output, or it's undone.

**Exercise: be the gate, then judge the result**

Run all ten personas for real, then review all thirty runs.

1. Approve or reject every run. Write a reason for every rejection. Which check did you lean on most: the quotes in the debrief, the critique or the transcript?
2. Run the synthesis and read `runs/synthesis/report.md`. Do you agree with the strongest and weakest segment? Find one shared job you think the evidence doesn't support.
3. Change one decision, approving a run you rejected or the other way round, and synthesize again. How much did one run move the conclusions?

**What good output looks like**

- Every run folder has a `review.json` with a decision, a note and whether it was edited.
- `runs/synthesis/report.md` starts with the banner, cites only approved personas, and ends with claims to verify and caveats, not a recommendation to build.

**Things to notice**

- The person comes after the cheap checks and before the conclusions. Reviewers spend their time on debriefs that already passed the schema, the evidence check and the critic.
- An edit isn't trusted just because a person made it. It goes through the same validation as an agent's output.
- Synthesis sees approved debriefs and their critiques, never transcripts or personas. If the review gate let it through, it can shape the conclusions; if not, it can't.
- The synthesis agent picks a strongest and a weakest segment because the design spec asks it to. Whether it should rank at all, or leave ranking to people, is still an open question in the spec. Argue it out in class.
