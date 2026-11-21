# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 2: structured outputs

**Goal.** Never pass an unchecked model reply downstream. Every reply is parsed into its Pydantic model. A reply that fails gets one retry that shows the model its own reply and what was wrong. A second failure is saved for inspection and the harness moves on.

Module 1's README is on the `module-01-solution` branch.

**Files that change**

| File | What changes |
| --- | --- |
| `harness/schemas.py` | `InterviewPrep` now enforces the counts the prompt asks for. New `parse_reply()` strips a code fence and validates. New `describe_error()` turns errors into one line per problem. |
| `harness/agents.py` | New `call_agent_json()`: call, validate, retry once with the error, then raise `OutputInvalid`. `call_agent()` is unchanged and still the only function that calls a model. |
| `harness/orchestrator.py` | `run_prep()` uses `call_agent_json()` and writes `failed.json` on a double failure. The main loop keeps going when one persona fails and prints a summary. |
| `tests/test_schemas.py` | Six tests that drive the retry with a fake model, no API key needed. |

**Run it**

```bash
pytest
python -m harness.orchestrator --dry-run --personas p01
python -m harness.orchestrator --personas p01
```

**Exercise: break the prompt on purpose**

This needs an API key. Run each break against p01, read `calls.jsonl`, then undo it.

1. In `prompts/prep.md`, change "5 to 7 contextual questions" to "2 or 3". The reply is valid JSON but breaks the schema. Watch the retry prompt tell the model `starter_questions` needs at least 5, and see whether it follows the error or the prompt.
2. Delete the last paragraph of `prompts/prep.md`, the one that describes the JSON. Does the retry rescue it, or do you get a `failed.json`?
3. Ask for a reply in Markdown instead of JSON. Two failures in a row should leave `failed.json` and a non-zero exit code.

**What good output looks like**

- A normal run makes one call per persona. `calls.jsonl` has one line.
- A rescued run has two lines. The second prompt ends with "Your previous reply could not be used", then the bad reply and a short list of what was wrong.
- A failed persona has `failed.json` with the error and both replies, the other personas still finish, and the summary names the failures.

**Things to notice**

- The schema is a contract the prompt makes. Valid JSON can still break it, so the counts in `InterviewPrep` matter as much as the JSON parsing does. Change the prompt and the schema together.
- A code fence gets fixed in code, not with a retry. Fix whatever is predictable in code and save retries for real mistakes. The raw reply, fence included, is still in `calls.jsonl`.
- Retry once, not forever. A prompt that fails twice is broken, and more retries just make that cost more.

**In production**

The Claude API can enforce a JSON schema for you through its structured outputs feature, so replies always parse. This harness doesn't use it, because then you'd never see the failures this module is about. Even with it, checks that need context still need code and a retry. Module 6's check that every `evidence_turns` value exists in the transcript is one of those.
