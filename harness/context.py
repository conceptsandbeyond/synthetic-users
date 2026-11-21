"""build_context(): the only place prompts are assembled.

Isolation is the most important rule in this harness. Each agent sees only
the artifacts on its allow-list in config.yaml. Sending every prompt through
one function means the rule lives in one place, and one test can prove it.
"""


class IsolationError(Exception):
    """Code tried to show an agent something it isn't allowed to see."""


# How each artifact is shown to a model: a section heading and a formatter.
# The artifact's name decides how much of an object goes out. Passing a whole
# Persona as persona_summary still reveals only the segment and job hypothesis.
ARTIFACTS = {
    "persona_summary": ("Persona summary", lambda persona: persona.summary()),
    "question_bank": ("Interview guide for this segment", str),
    "prep": ("Interview prep", lambda prep: prep.model_dump_json(indent=2, exclude={"persona_id"})),
    "persona_profile": (
        "Your profile",
        # The user never sees the job hypothesis: knowing what's being tested invites it to confirm it.
        lambda persona: persona.model_dump_json(indent=2, exclude={"id", "job_hypothesis", "recent_tasks"}),
    ),
    "recent_task": ("The recent task this interview is about", str),
    "transcript": ("Transcript", lambda transcript: transcript.render()),
    "persona": ("Persona given to the synthetic user", lambda persona: persona.model_dump_json(indent=2)),
    "debrief": ("Debrief of this run", lambda debrief: debrief.model_dump_json(indent=2)),
    "other_debriefs": (
        "Debriefs of this persona's other runs",
        lambda debriefs: "\n\n".join(d.model_dump_json(indent=2) for d in debriefs) or "(none)",
    ),
    "approved_debriefs": (
        "Approved debriefs",
        lambda debriefs: "\n\n".join(d.model_dump_json(indent=2) for d in debriefs),
    ),
    "critiques": (
        "Devil's advocate critiques of those runs",
        lambda critiques: "\n\n".join(c.model_dump_json(indent=2) for c in critiques),
    ),
}


def build_context(agent: str, config: dict, **artifacts) -> str:
    """Build the user message for `agent` from exactly the artifacts it may see.

    Raises IsolationError if the agent has no allow-list, if an artifact
    isn't on its list, or if one on its list is missing. The last check stops
    a prompt from quietly going out without, say, the transcript.
    """
    allowed = config["isolation"].get(agent)
    if allowed is None:
        raise IsolationError(f"{agent!r} has no allow-list under isolation in config.yaml")
    not_allowed = set(artifacts) - set(allowed)
    if not_allowed:
        raise IsolationError(f"{agent} may not see: {', '.join(sorted(not_allowed))}")
    missing = set(allowed) - set(artifacts)
    if missing:
        raise IsolationError(f"{agent} needs: {', '.join(sorted(missing))}")

    sections = []
    for name in allowed:  # config order, so prompts read the same every time
        heading, render = ARTIFACTS[name]
        sections.append(f"{heading}:\n{render(artifacts[name])}")
    return "\n\n".join(sections)
