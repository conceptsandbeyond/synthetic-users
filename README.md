# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 5: stop rules and budgets

**Goal.** Decide, in code, when an interview has to stop. The interviewer still ends a healthy interview itself. The stop rules catch the unhealthy ones, and every interview reports what it cost.

Earlier modules' READMEs are on their `module-NN-solution` branches.

**The stop rules.** They're checked before every interviewer turn, and the first one that fires wins.

| Rule | Default | Why |
| --- | --- | --- |
| Turn cap | 20 interviewer turns | An interviewer that never says `end` can't run forever. |
| Token budget | 40,000 tokens per interview | A runaway interview has a fixed worst-case cost. |
| Stall | 3 answers in a row under 10 words | Short answer after short answer means the interview isn't producing anything. |

A fourth limit, `run_token_cap`, stops the harness from starting new interviews once the whole run has spent too much.

**Files that change**

| File | What changes |
| --- | --- |
| `harness/orchestrator.py` | New `stop_rule_hit()`. `run_interview()` loops until a rule fires and returns an `Interview` with the transcript, the stop reason and the token count. It also writes `summary.json`. `main()` enforces `run_token_cap` and prints the total. |
| `harness/agents.py` | New `TokenMeter`. `call_agent()` and `call_agent_json()` add each call's tokens to it, retries included. |
| `harness/schemas.py`, `harness/transcript.py` | Each transcript turn records the output tokens it cost. |
| `config.yaml` | The budget, stall settings and `run_token_cap`. |
| `tests/test_stop_rules.py` | New. Unit tests for each rule, plus real-loop tests with a terse user and a tiny budget. |

**Your task**

You're on the `module-05-start` branch. The token meter, the loop that calls the stop rules, `summary.json` and the tests are in place. `stop_rule_hit()` in `harness/orchestrator.py` is empty. Its docstring lists the steps. Build it until `pytest` passes, then compare with the `module-05-solution` branch.

**Run it**

```bash
pytest tests/test_stop_rules.py -v
python -m harness.orchestrator --dry-run --personas p01
```

**Exercise: change the turn cap**

With an API key, run p05 with `max_interviewer_turns` at 5, then at 40.

1. At 5, which prepared questions never got asked? Which hypotheses can't be tested from this transcript?
2. At 40, did the interviewer end on its own, or did it keep going? If it kept going, read the last ten questions. Are they still useful, or is it repeating itself?
3. Compare the token counts in each `summary.json`. What does one extra question cost by the end of an interview, when the whole transcript goes into every prompt?

**What good output looks like**

- Each interview prints its turns, the rule that stopped it and its tokens. Most should say "stopped by interviewer ended".
- `runs/<persona_id>/run-1/summary.json` holds the same numbers.
- Each line in `transcript.jsonl` has a `tokens` value.

**Things to notice**

- The rules are plain code, not a model's judgment. Stopping has to be predictable, cheap and testable.
- The budget is checked between turns, so an interview can overshoot by one exchange. A hard stop mid-exchange would leave a question with no answer.
- Costs grow faster than turns. Each prompt carries the whole transcript, so the 15th question costs far more than the first.
