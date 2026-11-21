# Synthetic User Interview Harness

A teaching repo for building an AI agent harness in Python. The finished harness runs synthetic jobs-to-be-done interviews with 10 customer personas for an audible level (a level that tells you by sound when something is level), then fills in the Interview Prep and User Debrief templates.

Synthetic interviews rehearse an interview guide and surface hypotheses. They are not user research. Real interviews validate what these suggest.

Background: [design spec](docs/design-spec.md), [personas](docs/personas.md), [interview guides](docs/jtbd-interview-guides.md).

## Module 9: rebuild on the Claude Agent SDK

**Goal.** Run the same harness with the Claude Agent SDK as its engine, then compare. The SDK runs Claude Code as a subprocess: a full agent harness with built-in tools, settings files and its own system context. This module swaps it in at the one seam built in module 1, `call_agent()`, and asks what that changes.

Earlier modules' READMEs are on their `module-NN-solution` branches.

**Files**

| File | What it does |
| --- | --- |
| `module9_agent_sdk/sdk_agents.py` | `call_agent_sdk()`: same arguments and return value as `call_agent()`, implemented with `query()` from `claude_agent_sdk`. `sdk_options()` turns off everything this harness doesn't want. |
| `module9_agent_sdk/run.py` | Swaps the engine in two lines and runs the normal orchestrator. |
| `module9_agent_sdk/requirements.txt` | `claude-agent-sdk`, needed only for this module. |
| `tests/test_module9.py` | Checks the SDK options and runs the pipeline on the SDK engine with the stub. Skipped if the SDK isn't installed. |

**Your task**

You're on the `module-09-start` branch. `sdk_options()`, `_ask()`, `run.py` and the tests are in place. `call_agent_sdk()` in `module9_agent_sdk/sdk_agents.py` is empty. Its docstring lists the steps. Build it until `pytest tests/test_module9.py` passes, then compare with the `module-09-solution` branch.

**Run it**

```bash
pip install -r module9_agent_sdk/requirements.txt
pytest tests/test_module9.py -v
python -m module9_agent_sdk.run --dry-run --personas p08
python -m module9_agent_sdk.run --personas p08
```

The same flags work as for `harness.orchestrator`, `--synthesize` included. Review is unchanged: `python -m harness.review`.

**What the swap looks like**

| | Messages API (modules 1 to 8) | Agent SDK (module 9) |
| --- | --- | --- |
| What runs | One HTTPS request per call | A Claude Code subprocess per call, which makes the requests |
| Tools | None unless you add one | Built-in tools (Bash, file reading, web) unless you pass `tools=[]` |
| Project files | Never read | `CLAUDE.md` and settings can load unless you pass `setting_sources=[]` |
| Web search | Declared by its API type, paused turns handled by hand | Built-in `WebSearch` tool, looping handled for you |
| What `calls.jsonl` proves | The exact request sent to the model | Only what we handed the SDK. The subprocess builds the final request |
| Cost | Tokens from `usage` | Tokens plus `total_cost_usd` on the result message |

**Exercise: compare the two engines**

Run p08 on both engines with an API key, then compare the outputs and the logs.

1. **What did the SDK hide?** Find something the module 7 version of `call_agent()` does by hand that `call_agent_sdk()` doesn't have to do.
2. **What did it save?** Count the lines. Is the SDK version shorter? Is the whole system simpler, or is the complexity just somewhere you can't read?
3. **Where did isolation get harder to prove?** `test_isolation.py` reads `calls.jsonl`. On the SDK engine, does a passing test still prove what the model saw? What would you need to see to be sure?
4. **The tempting rebuild.** The SDK makes it easy to hand the whole interview to one agent with subagents for the interviewer and the user. Sketch that design, then explain how you would prove the interviewer never saw the persona. That proof is the main reason this harness keeps a plain-Python orchestrator.

**What good output looks like**

- Both engines produce the same files in the same places, because everything above `call_agent()` is unchanged.
- The SDK log entries show `"tools": []` for every agent except the advocate, which shows `["WebSearch"]`.

**Things to notice**

- The swap is two assignments in `run.py`. Module 1's rule that every model call goes through one function is what makes that possible.
- Every option in `sdk_options()` turns something off. With a framework, isolation becomes a set of things you must remember to disable, instead of a list of things you chose to include.
- Neither engine is wrong. The SDK is the better choice when you want an agent that acts on files and tools. A raw API call is the better choice when the job is a controlled conversation you need to audit.
