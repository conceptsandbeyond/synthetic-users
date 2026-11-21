"""Pydantic models for the harness's data contracts.

Every persona file and every agent output is parsed into one of these models.
If the data doesn't fit, we find out at the moment it is created, not three
steps later when another agent quietly works from a broken input.
"""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Persona(BaseModel):
    """A synthetic customer, written by hand in personas/<id>.json.

    These are hypotheses, not research. current_alternatives and objections
    exist so the synthetic user has something concrete to push back with
    instead of agreeing with every question. recent_tasks gives each repeat
    run a different real situation to talk about, which is what makes runs
    differ from each other.
    """

    # Reject unknown keys so a typo in a hand-written file fails loudly.
    model_config = ConfigDict(extra="forbid")

    id: str
    segment: str
    job_hypothesis: str
    name: str
    age: int
    location: str
    behaviors: list[str] = Field(min_length=1)
    values: list[str] = Field(min_length=1)
    current_alternatives: list[str] = Field(min_length=1)
    objections: list[str] = Field(min_length=1)
    recent_tasks: list[str] = Field(min_length=3)

    def summary(self) -> str:
        """Return the only persona facts the prep agent may see.

        The prep agent plans an interview for a segment, not for a person, so
        it gets the segment and the job hypothesis and nothing else.
        """
        return f"Segment: {self.segment}\nJob hypothesis: {self.job_hypothesis}"


class InterviewPrep(BaseModel):
    """The prep agent's output. Mirrors the Interview Prep template.

    The list lengths match what prompts/prep.md asks for. A reply can be
    perfectly valid JSON and still break the contract, and these limits are
    what catch that. Change the prompt and the schema together.
    """

    model_config = ConfigDict(extra="forbid")

    persona_id: str
    key_hypotheses: list[str] = Field(min_length=3, max_length=5)
    interviewee_profile: str
    starter_questions: list[str] = Field(min_length=5, max_length=7)
    contrasting_questions: list[str] = Field(min_length=4, max_length=6)


class Turn(BaseModel):
    """One line of transcript.jsonl.

    Turns are numbered across both speakers (1, 2, 3...) so later agents can
    cite exact turns as evidence.
    """

    turn: int
    speaker: Literal["interviewer", "user"]
    text: str
    tokens: int = 0  # output tokens the model spent writing this turn
    ts: str


class InterviewerTurn(BaseModel):
    """The interviewer's output: the next question, or a signal to stop."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["ask", "end"]
    question: str | None = None

    @model_validator(mode="after")
    def ask_needs_a_question(self) -> "InterviewerTurn":
        if self.action == "ask" and not (self.question and self.question.strip()):
            raise ValueError('action "ask" needs a non-empty "question"')
        return self


class Need(BaseModel):
    need: str
    evidence_turns: list[int] = Field(min_length=1)


class Insight(BaseModel):
    insight: str
    evidence_turns: list[int] = Field(min_length=1)


class UserDebrief(BaseModel):
    """The debrief agent's output. Mirrors the User Debrief template.

    evidence_turns is required on every need and insight. It forces the
    debrief to cite the transcript, and gives the devil's advocate something
    concrete to check.
    """

    model_config = ConfigDict(extra="forbid")

    persona_id: str
    run: int
    name: str
    occupation_role: str
    about_me_and_goals: str
    most_pressing_needs: list[Need] = Field(min_length=1)
    main_insights: list[Insight] = Field(min_length=1)
    current_solutions: list[str]
    opportunities: list[str]


def check_evidence(debrief: UserDebrief, turns: list[Turn]) -> None:
    """Raise ValueError unless every cited turn is an answer in this transcript.

    Pydantic can check that evidence_turns holds numbers. Only code that has
    the transcript can check that the numbers point at something real.
    """
    answers = {t.turn for t in turns if t.speaker == "user"}
    cited = [n for point in debrief.most_pressing_needs + debrief.main_insights for n in point.evidence_turns]
    wrong = sorted({n for n in cited if n not in answers})
    if wrong:
        raise ValueError(f"evidence_turns {wrong} are not interviewee answers. "
                         f"Cite only these turns: {sorted(answers)}")


def parse_reply(text: str, schema: type[BaseModel], known_fields: dict | None = None) -> BaseModel:
    """Turn a model's text reply into a validated schema object, or raise ValueError.

    known_fields holds values the code already knows, like persona_id, so we
    never ask a model for them. Both json.JSONDecodeError and pydantic's
    ValidationError are subclasses of ValueError, so callers catch just one.
    """
    data = json.loads(_strip_code_fence(text))
    if not isinstance(data, dict):
        raise ValueError(f"Expected one JSON object, got a JSON {type(data).__name__}")
    return schema.model_validate({**data, **(known_fields or {})})


def describe_error(error: ValueError) -> str:
    """Return a short, readable version of a parse or validation error.

    Pydantic's default message adds documentation links and echoes the input
    back. That's noise in a retry prompt, so keep one line per problem.
    """
    if isinstance(error, ValidationError):
        return "\n".join(f"- {'.'.join(map(str, e['loc'])) or 'reply'}: {e['msg']}" for e in error.errors())
    return f"- {error}"


def _strip_code_fence(text: str) -> str:
    """Remove a ```json ... ``` wrapper if the whole reply is one.

    Models often add the fence even when told not to. It's a predictable
    formatting quirk, so fixing it in code is cheaper than spending a retry.
    """
    match = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n?\s*```\s*", text, flags=re.DOTALL)
    return match.group(1) if match else text
