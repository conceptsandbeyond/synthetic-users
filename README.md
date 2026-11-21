# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 4: context isolation

**Goal.** Make isolation a rule the code enforces instead of a habit. Every prompt is now assembled by `build_context()`, which refuses anything that isn't on that agent's allow-list in `config.yaml`. A test reads the real prompt log and proves the interviewer never saw the persona.

This is the most important module. Spend the time here.

Earlier modules' READMEs are on their `module-NN-solution` branches.

**Files that change**

| File | What changes |
| --- | --- |
| `harness/context.py` | New. `build_context()` and the `ARTIFACTS` table that decides how each artifact is shown. |
| `config.yaml` | New `isolation` allow-list for prep, interviewer and user. |
| `harness/orchestrator.py` | `run_prep()` and `run_interview()` call `build_context()` instead of formatting prompts themselves. |
| `tests/test_isolation.py` | New. Audits `calls.jsonl` for all 10 personas, and checks every way `build_context()` can refuse. |

**Run it**

```bash
pytest tests/test_isolation.py -v
python -m harness.orchestrator --dry-run --personas p01
```

**Exercise: leak the persona and watch what happens**

1. In `config.yaml`, add `persona_profile` to the interviewer's list. In `run_interview()`, pass `persona_profile=persona` to the interviewer's `build_context()` call.
2. Run `pytest`. Ten isolation tests fail, one per persona. The harness caught the leak before a single token was spent.
3. With an API key, run p01 leaked and then isolated. Put the two sets of questions side by side. Look for questions that assume the answer ("As someone who uses VoiceOver...") or that skip discovery and jump to what the interviewer already "knows".
4. Undo the leak and make sure `pytest` is green again.

**What good output looks like**

- Open `runs/p01-visually-impaired-diyer/run-1/calls.jsonl` and search for "Marcus". It appears only in calls where `"agent": "user"`.
- Every prompt is a set of headed sections in allow-list order: "Interview prep:", then "Transcript:".

**Things to notice**

- The artifact's name decides what leaves. `persona_summary` renders only the summary, even when you pass it the whole persona, so a careless caller can't leak by accident.
- A missing artifact is an error too. A prompt that quietly goes out without the transcript is a bug that's hard to spot in the output.
- The test reads the log, not the code. It checks what the model actually received.
- One honest limit: the interviewer does learn about the persona through the interviewee's answers. That's the point of an interview. Isolation stops the interviewer from knowing things nobody told it.
