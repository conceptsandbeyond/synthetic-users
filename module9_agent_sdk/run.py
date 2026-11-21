"""Run the whole harness with the Claude Agent SDK as its engine.

    python -m module9_agent_sdk.run --dry-run --personas p01
    python -m module9_agent_sdk.run --personas p01

Takes the same flags as harness.orchestrator. Everything else stays the same:
build_context(), the schemas, the stop rules, the critiques and the review
gate. Only the function that talks to a model is swapped. That this takes two
lines is the payoff for routing every call through call_agent() in module 1.
"""

from harness import agents, orchestrator
from module9_agent_sdk.sdk_agents import call_agent_sdk


def use_agent_sdk() -> None:
    """Point the harness at the SDK engine."""
    agents.call_agent = call_agent_sdk        # what call_agent_json() calls
    orchestrator.call_agent = call_agent_sdk  # what the orchestrator calls for the synthetic user


if __name__ == "__main__":
    use_agent_sdk()
    orchestrator.main()
