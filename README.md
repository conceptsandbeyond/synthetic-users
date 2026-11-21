# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 3: two agents talking

**Goal.** Run a real interview. The interviewer asks, the synthetic user answers, and plain Python relays each turn between them. Every turn is written to disk the moment it happens.

Earlier modules' READMEs are on their `module-NN-solution` branches.

**Files that change**

| File | What changes |
| --- | --- |
| `harness/transcript.py` | New. `Transcript` appends each turn to `transcript.jsonl` as it happens and renders the conversation as text for the next prompt. |
| `harness/orchestrator.py` | New `run_interview()`: the turn-taking loop. `main()` now preps and then interviews each persona. |
| `harness/schemas.py` | New `Turn` (one transcript line) and `InterviewerTurn` (a question or `end`). `Persona` gains `recent_tasks`. |
| `prompts/interviewer.md`, `prompts/user.md` | New system prompts for the two agents. |
| `personas/*.json` | Three `recent_tasks` each. Run N talks about task N. |
| `harness/stub_replies.json` | The dry-run replies, moved out of the code. The stub interviewer asks three questions and ends. |
| `config.yaml` | `interview.max_interviewer_turns`, a safety cap. |
| `tests/test_interview.py` | New tests for the loop and the transcript. |

**Your task**

You're on the `module-03-start` branch. The transcript writer, schemas, prompts, recent tasks and stub are in place. The loop inside `run_interview()` in `harness/orchestrator.py` is missing: the code that asks the interviewer, records the question, asks the user and records the answer. The TODO comment lists the steps. Build it until `pytest` passes, then compare with the `module-03-solution` branch.

Before you start, the tests that run an interview fail with `NotImplementedError`. That's expected.

**Run it**

```bash
pytest
python -m harness.orchestrator --dry-run --personas p05
python -m harness.orchestrator --personas p05
```

**Exercise: read one interview aloud**

Run one real interview, then read `runs/<persona_id>/run-1/transcript.jsonl` aloud in class, with one person as the interviewer and one as the interviewee. Then discuss:

1. Where did the interviewer follow up on something the interviewee said, and where did it just move to the next prepared question?
2. Did the interviewee ever push back, or name a reason the current method is good enough?
3. Find one answer that sounds like a real person and one that sounds like a model. What's the difference?

**What good output looks like**

- The interviewer opens with a question about one recent task and keeps returning to it.
- Follow-ups use the interviewee's own words: "You said you checked it twice. What made you check again?"
- The interviewee answers in a few spoken sentences, mentions what they do today, and doesn't fall in love with anything.
- The run ends with "stopped by interviewer ended", usually after 10 to 16 questions. "Stopped by turn cap" means the interviewer prompt needs work.

**Things to notice**

- Nobody talks to anybody. Each agent call is built fresh from what that agent may see, plus the transcript so far. The "conversation" exists only in `transcript.jsonl`.
- The user agent never sees the job hypothesis. If it knew what was being tested, it would drift toward confirming it.
- Repeat runs differ because each run talks about a different recent task, not because of randomness. Module 6 runs all three.
- Both prompts are still built by hand inside `run_interview()`. Nothing stops a careless edit from showing the interviewer the persona. That's the problem module 4 solves.
