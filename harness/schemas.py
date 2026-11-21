"""Pydantic models for the harness's data contracts.

Every persona file and every agent output is parsed into one of these models.
If the data doesn't fit, we find out at the moment it is created, not three
steps later when another agent quietly works from a broken input.
"""

from pydantic import BaseModel, ConfigDict, Field


class Persona(BaseModel):
    """A synthetic customer, written by hand in personas/<id>.json.

    These are hypotheses, not research. current_alternatives and objections
    exist so the synthetic user has something concrete to push back with
    instead of agreeing with every question.
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

    def summary(self) -> str:
        """Return the only persona facts the prep agent may see.

        The prep agent plans an interview for a segment, not for a person, so
        it gets the segment and the job hypothesis and nothing else.
        """
        return f"Segment: {self.segment}\nJob hypothesis: {self.job_hypothesis}"


class InterviewPrep(BaseModel):
    """The prep agent's output. Mirrors the Interview Prep template."""

    model_config = ConfigDict(extra="forbid")

    persona_id: str
    key_hypotheses: list[str] = Field(min_length=1)
    interviewee_profile: str
    starter_questions: list[str] = Field(min_length=1)
    contrasting_questions: list[str] = Field(min_length=1)
