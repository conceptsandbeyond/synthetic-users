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
}


def build_context(agent: str, config: dict, **artifacts) -> str:
    """Build the user message for `agent` from exactly the artifacts it may see.

    Raises IsolationError if the agent has no allow-list, if an artifact
    isn't on its list, or if one on its list is missing. The last check stops
    a prompt from quietly going out without, say, the transcript.

    TODO (module 4): build this function.
      1. Look up the agent's allow-list: config["isolation"].get(agent).
         Raise IsolationError if there is none.
      2. Raise IsolationError naming any artifact passed in that isn't on the list.
      3. Raise IsolationError naming any artifact on the list that wasn't passed in.
      4. For each name on the list, in list order, look up (heading, render) in
         ARTIFACTS and make a section: f"{heading}:\n{render(artifacts[name])}".
      5. Join the sections with a blank line between them and return the result.
    The tests look for these phrases in the error messages: "no allow-list",
    "may not see: <names>" and "needs: <names>", with names sorted and
    separated by ", ".
    """
    raise NotImplementedError("Module 4: build build_context()")
