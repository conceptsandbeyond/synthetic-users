# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 7: evaluation

**Goal.** Catch weak results before a person reads them. Each run now gets two checks. The devil's advocate agent assumes the debrief is wrong until the evidence proves otherwise, and it's the only agent with a tool: web search for the reality-anchor check. The interviewer check is plain code that flags leading questions and questions about the future. A run the advocate rates `low` is rerun once. A second `low` is flagged for human review.

Earlier modules' READMEs are on their `module-NN-solution` branches.

**Files that change**

| File | What changes |
| --- | --- |
| `prompts/advocate.md` | New. Seven checks, each rated pass, warn or fail, plus a confidence rule. |
| `harness/schemas.py` | New `Checks` and `Critique`. |
| `harness/checks.py` | New. `check_questions()`, the interviewer check, built from regular expressions. |
| `harness/agents.py` | `call_agent()` attaches server tools from config, resumes a paused search, keeps only the text after the last search result, and logs each call's tools. |
| `harness/context.py` | New artifacts for the advocate: the full `persona`, this run's `debrief`, and `other_debriefs`. |
| `harness/orchestrator.py` | New `run_once()`, `run_critique()` and `evaluate_run()`. Critiques wait until all runs are done. A low rating reruns into `run-N-rerun/`. `summary.json` records the confidence and whether the run is flagged. |
| `config.yaml` | The advocate's allow-list, and `tools: advocate: [web_search]`. |
| `tests/test_evaluation.py` | New tests for critiques, advocate isolation, tool access, the rerun rule, the interviewer check and resuming a paused search. |

**Run it**

```bash
pytest tests/test_evaluation.py -v
python -m harness.orchestrator --dry-run --personas p10
python -m harness.orchestrator --personas p10
```

**Exercise: find a run the critic rates low**

Run all ten personas for real, then find every `summary.json` with `"confidence": "low"`.

1. Read that run's `critique.json`. Which checks failed, and do you agree after reading the transcript?
2. Look at the rerun in `run-N-rerun/`. Did it fix the problem? If not, is the problem the persona, the user prompt or the interviewer prompt? Try a prompt fix before a code fix.
3. Open `interviewer_check.json` for a few runs. Find one flag you agree with and one false alarm. What would it take to catch the subtle leading questions the patterns miss?

**What good output looks like**

- Each run folder has `critique.json` and `interviewer_check.json`, and its `summary.json` has `confidence` and `flagged`.
- Most runs come back `medium`. A wall of `high` ratings is suspicious: a devil's advocate that agrees with everything isn't doing its job.
- The `sources` in a critique are real pages about real people doing this job: forums, research or advocacy organizations.

**Things to notice**

- The advocate is the only agent that sees everything: persona, transcript, debrief and the other runs. Its job is to find gaps between them.
- It runs on a stronger model than the agents it checks, but it shares their blind spots. For p01 and p10, plan a review by two or three people from those communities before treating either persona as credible.
- One tool, for one check. Search adds cost, latency and outside text in the prompt. It's worth that only where the answer has to come from outside the harness.
- The interviewer check is code, not a model, so you can predict exactly what it flags. It also guarantees false alarms: "Would you rather..." is a fair contrasting question that still gets flagged as about the future.
- One rerun, then a person. A persona that fails twice needs a human, not a third try.
