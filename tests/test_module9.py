"""Module 9 tests: the Agent SDK engine is configured for isolation and drops into the same pipeline.

Skipped unless claude-agent-sdk is installed (pip install -r module9_agent_sdk/requirements.txt).
These tests never start the SDK's subprocess or call the API.
"""

import json

import pytest

pytest.importorskip("claude_agent_sdk")

from harness import agents, orchestrator  # noqa: E402
from harness.orchestrator import RunSpend, load_config, load_personas, run_persona  # noqa: E402
from module9_agent_sdk.run import use_agent_sdk  # noqa: E402
from module9_agent_sdk.sdk_agents import call_agent_sdk, sdk_options  # noqa: E402

CONFIG = load_config()


@pytest.mark.parametrize("agent", ["prep", "interviewer", "user", "debrief", "synthesis"])
def test_agents_without_tools_get_no_built_in_tools(agent):
    options = sdk_options(agent, CONFIG)
    assert options.tools == [] and options.allowed_tools == []
    assert options.setting_sources == []  # CLAUDE.md and settings files stay out
    assert options.max_turns == 1
    assert options.model == CONFIG["models"][agent]


def test_the_advocate_gets_only_web_search():
    options = sdk_options("advocate", CONFIG)
    assert options.tools == options.allowed_tools == ["WebSearch"]


def test_the_same_pipeline_runs_on_the_sdk_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(agents, "call_agent", call_agent_sdk)
    monkeypatch.setattr(orchestrator, "call_agent", call_agent_sdk)
    config = CONFIG | {"paths": CONFIG["paths"] | {"runs": tmp_path}, "runs_per_persona": 1}
    persona = load_personas(CONFIG["paths"]["personas"], ["p08"])[0]

    results = run_persona(persona, config, RunSpend(10**9), dry_run=True)

    assert results[0][0] is True
    run_dir = tmp_path / persona.id / "run-1"
    agents_called = {json.loads(line)["agent"] for line in (run_dir / "calls.jsonl").open()}
    assert agents_called == {"interviewer", "user", "debrief", "advocate"}


def test_use_agent_sdk_swaps_both_call_sites(monkeypatch):
    monkeypatch.setattr(agents, "call_agent", agents.call_agent)
    monkeypatch.setattr(orchestrator, "call_agent", orchestrator.call_agent)
    use_agent_sdk()
    assert agents.call_agent is call_agent_sdk and orchestrator.call_agent is call_agent_sdk
