# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The harness runs synthetic jobs-to-be-done (JTBD) interviews with 10 customer personas for an "audible level" (a level that tells you by sound when something is level), saves the transcripts, and fills in two Concepts and Beyond templates: Interview Prep and User Debrief.

The audience is product management students learning how agent harnesses work. Readable code matters more than clever code.

Full spec: `docs/design-spec.md`. Personas: `docs/personas.md`. Interview questions: `docs/jtbd-interview-guides.md`. Templates: `templates/Interview_Prep.pdf`, `templates/User_Persona.pdf`.

## Decisions (ask before changing any of these)

- Python 3.10+.
- Modules 1 to 8 use the Anthropic Python SDK (`anthropic`) directly. No agent frameworks (no LangGraph, CrewAI, AutoGen).
- The Claude Agent SDK appears only in module 9, in its own folder, as a rebuild of the same harness for comparison.
- Pydantic v2 for every data contract, `pyyaml` for config, `python-dotenv` for the API key, `pytest` for tests.
- The orchestrator is plain, deterministic Python. Only tasks that need judgment call a model.
- Outputs are files. No web UI.
- Keep `harness/` under about 800 lines. Short functions, with docstrings that explain why, not what.

## Agents

| Agent | Sees | Produces | Template |
| --- | --- | --- | --- |
| prep | persona summary (segment, job hypothesis), JTBD question bank | Interview Prep JSON | Interview Prep |
| interviewer | prep JSON, transcript so far | next question, or `{"action": "end"}` | none |
| user (synthetic) | persona without the job hypothesis, this run's recent task, transcript so far | one in-character answer | none |
| debrief | transcript only | User Debrief JSON with `evidence_turns` | User Debrief |
| advocate (devil's advocate) | persona, transcript, debrief | critique JSON with confidence rating | none |
| synthesis | approved debriefs, critiques | cross-segment report | none |

## Context isolation: the most important rule

- Every prompt is assembled by `build_context(agent, ...)` in `harness/context.py`. Nothing else builds prompts.
- `build_context` reads the allow-list in `config.yaml` and raises an error if code passes anything not on it.
- No agent shares conversation history with another. Each call is built fresh.
- The interviewer must never see persona text. `tests/test_isolation.py` proves it.

## Orchestration rules

- The interviewer speaks first. The code relays turns between the interviewer and the user agent.
- Stop when the first of these happens: the interviewer returns `end`, 20 interviewer turns, the 40,000-token budget per interview, or 3 user answers in a row under 10 words.
- 3 runs per persona. Each run gives the synthetic user a different task from the persona's `recent_tasks`; that is what makes runs differ. Don't set temperature: current models accept only the default.
- A critique rated `low` triggers one rerun of that run. A second `low` goes to human review flagged.
- Only debriefs approved in the human review step reach synthesis.

## Quality layer

1. Schema validation: every output parses into its Pydantic model, and every `evidence_turns` value exists in the transcript. On invalid output, retry once with the error, then mark the run failed.
2. Devil's advocate: 7 checks (evidence trail, too agreeable, missing alternatives, stereotype, consistency, reality anchor, job strength). Each is pass, warn or fail. Only this agent gets a tool: the API's web search, for the reality-anchor check.
3. Interviewer check: flag leading questions and questions about the hypothetical future instead of past behavior.
4. Human review: a command-line step in `review.py` to approve, reject or edit.

## Repo layout

```
config.yaml        models, limits, budgets, isolation allow-list
personas/          10 persona JSON files
prompts/           one markdown system prompt per agent
harness/
  agents.py        call_agent(): the only place models are called; logs every call
  context.py       build_context(): enforces isolation
  orchestrator.py  run_persona() and the main loop
  schemas.py       Pydantic models
  transcript.py    append-only JSONL writer
  stub_replies.json canned replies for --dry-run
  review.py        human review CLI
  render.py        renders prep and debrief JSON to Markdown laid out like the templates
runs/              outputs: runs/<persona_id>/<run>/
tests/             test_isolation.py, test_schemas.py, test_interview.py, test_stop_rules.py
module9_agent_sdk/ the Agent SDK rebuild
```

## Conventions

- Model names live only in `config.yaml`. Defaults: claude-sonnet-5-5 for prep, interviewer and debrief; claude-haiku-5-5 for the user; claude-opus-5-5 for advocate and synthesis.
- Every model call goes through `call_agent()` and is logged to `runs/<persona>/<run>/calls.jsonl` with agent, model, tokens, latency and the exact prompt.
- `--dry-run` swaps in a stub model with canned answers. All tests run on the stub and need no API key.
- `--personas p01,p05` runs a subset.
- Never commit `.env`. Ship `.env.example` instead.
- Every rendered output starts with the banner: "Synthetic interview, not real user data."
- Synthetic users portray competent adults with real constraints. No pity stories or stereotypes, especially for the visually impaired and senior personas.

## Teaching modules

Each module has a `module-NN-start` and a `module-NN-solution` branch, and a README covering the goal, files to touch, how to run it, and what good output looks like.

1. A single agent call: `call_agent()` and the prep agent
2. Structured outputs: Pydantic schemas, retry on invalid JSON
3. Two agents talking: turn-taking loop and transcript writer
4. Context isolation: `build_context()` and the allow-list (the key module)
5. Stop rules and budgets
6. Pipelines and repeat runs: debrief agent, 3 runs, parallel personas
7. Evaluation: devil's advocate, interviewer check, web search tool
8. Human in the loop: review gate and synthesis
9. Rebuild on the Claude Agent SDK and compare

## Commands

```
pip install -r requirements.txt
pytest
python -m harness.orchestrator --dry-run --personas p01
python -m harness.orchestrator --personas p01
python -m harness.review
```

## How to work in this repo

- Build one module at a time, in order. Don't write code for later modules early.
- Show a short plan before creating or changing more than 3 files.
- Run `pytest` after every change.
- Prompts change more often than code. When output quality is poor, suggest a prompt fix before a code fix.
