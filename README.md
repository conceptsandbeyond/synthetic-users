# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 1: a single agent call

**Goal.** Make one model call, cleanly: send the prep agent a segment and its interview guide, get back an Interview Prep, and log everything about the call.

**Files**

| File | What it does |
| --- | --- |
| `config.yaml` | Model names and paths. The only place a model name appears. |
| `personas/*.json` | The 10 synthetic personas. |
| `prompts/prep.md` | The prep agent's system prompt. |
| `harness/schemas.py` | `Persona` and `InterviewPrep`, the Pydantic models. |
| `harness/agents.py` | `call_agent()`, the only function that calls a model, plus the dry-run stub. |
| `harness/orchestrator.py` | Loads personas, runs the prep agent, saves the result. |
| `tests/test_schemas.py` | Proves the personas are valid and a dry-run prep works. |

**Your task**

You're on the `module-01-start` branch. Everything is in place except two functions in `harness/agents.py`: `call_agent()` and `_log_call()`. Their docstrings list the steps. Build them until `pytest` passes, then compare your version with the `module-01-solution` branch.

Before you start, one test fails on purpose: `test_dry_run_prep_is_valid_and_logged`, because `call_agent()` raises `NotImplementedError`.

**Run it**

```bash
pip install -r requirements.txt
pytest
python -m harness.orchestrator --dry-run --personas p01
```

`--dry-run` uses a stub model with a canned answer, so it needs no API key. For a real call, copy `.env.example` to `.env`, add your key, and drop the flag:

```bash
python -m harness.orchestrator --personas p01
```

**What good output looks like**

Each persona gets a folder, `runs/<persona_id>/prep/`, holding two files:

- `prep.json`: key hypotheses, who to interview, starter questions and contrasting questions. Good starter questions ask about one recent, real task ("Tell me about the last time..."). Good hypotheses include at least one that would count against the product.
- `calls.jsonl`: one line per model call with the model, token counts, latency and the exact prompt sent. Open it and check what the prep agent saw: the segment, the job hypothesis and that segment's guide. Not the persona's name, behaviors or objections.

**Things to notice**

- The model never writes `persona_id`. The code already knows it, so the code adds it.
- In module 1 the prompt is assembled by hand in `run_prep()`. Module 4 replaces that with `build_context()`, which enforces what each agent may see.
- A real reply wrapped in a code fence, or with an extra key, will fail validation. That failure is the starting point for module 2.
