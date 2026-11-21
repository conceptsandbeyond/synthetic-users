# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 6: pipelines and repeat runs

**Goal.** Turn one interview into a pipeline. Each persona is prepped once, then interviewed and debriefed three times, each run about a different recent task. Personas run in parallel. Every prep and debrief is also rendered as Markdown laid out like the Concepts and Beyond templates.

Earlier modules' READMEs are on their `module-NN-solution` branches.

**Files that change**

| File | What changes |
| --- | --- |
| `prompts/debrief.md` | New. The debrief agent works from the transcript alone and must cite turns. |
| `harness/schemas.py` | New `UserDebrief`, plus `check_evidence()`: every cited turn must be an interviewee answer in this transcript. |
| `harness/agents.py` | `call_agent_json()` takes an optional `check`, an extra test that gets the same single retry as a schema error. |
| `harness/orchestrator.py` | New `run_debrief()`, `run_persona()` and `RunSpend`. `main()` runs personas in a thread pool. Each step starts in an emptied folder, and `save_failure()` writes `failed-<agent>.json`. |
| `harness/render.py` | New. Renders `prep.md` and `debrief.md` with the banner, quoting each cited turn. |
| `config.yaml` | `runs_per_persona`, `parallel_personas`, and the debrief's allow-list (`transcript` only). |
| `tests/test_pipeline.py` | New tests for the three runs, rendering, debrief isolation, evidence checks and the parallel run. |

**Run it**

```bash
pytest
python -m harness.orchestrator --dry-run
python -m harness.orchestrator --personas p03
```

Outputs land in `runs/<persona_id>/prep/` and `runs/<persona_id>/run-1/` to `run-3/`. Each run folder holds `transcript.jsonl`, `debrief.json`, `debrief.md`, `summary.json` and `calls.jsonl`.

**Exercise: compare three debriefs of the same persona**

Run one persona for real, then open its three `debrief.md` files side by side.

1. Which needs show up in all three runs? Those are your strongest signals.
2. Which needs show up in only one? Is that because the recent task was different, or because the synthetic user said something new?
3. Pick one insight and read the quoted turn. Does the quote actually support it, or did the debrief agent stretch it?

**What good output looks like**

- Every need and insight in `debrief.md` has at least one quote under it, from an interviewee answer.
- The three debriefs overlap but aren't identical. Identical debriefs mean the recent tasks aren't doing their job. Completely different ones mean the persona isn't holding together.
- The run summary ends with "30 of 30 runs completed" for a full run.

**Things to notice**

- The debrief agent never sees the persona. If a debrief says something the transcript doesn't, the evidence check or the reader will catch it.
- The name comes from code, not from the model. The debrief agent never learns it.
- Evidence is checked in two layers. Pydantic checks the shape. `check_evidence()` checks the meaning: the cited turn has to exist and has to be an answer.
- Personas run in parallel, but one persona's runs stay in order, so its logs read top to bottom.
