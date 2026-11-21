"""Render prep and debrief JSON as Markdown laid out like the Concepts and Beyond templates.

The JSON is for code. These files are for people: students, reviewers and
class materials. Every one starts with the banner so nothing synthetic is
ever mistaken for real research.
"""

from harness.schemas import InterviewPrep, SynthesisReport, Turn, UserDebrief

BANNER = "> **Synthetic interview, not real user data.**"


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- (none)"


def render_prep(prep: InterviewPrep) -> str:
    """Lay out an Interview Prep in the template's order."""
    return f"""{BANNER}

# Interview Prep: {prep.persona_id}

## Key hypotheses
{bullets(prep.key_hypotheses)}

## Who to interview
{prep.interviewee_profile}

## Starter questions
{bullets(prep.starter_questions)}

## Contrasting questions
{bullets(prep.contrasting_questions)}
"""


def render_debrief(debrief: UserDebrief, turns: list[Turn]) -> str:
    """Lay out a User Debrief, quoting the turns each point cites.

    Quotes come from the transcript, not from the debrief agent, so a reader
    sees exactly what the evidence says.
    """
    said = {t.turn: t.text for t in turns}

    def with_quotes(text: str, evidence: list[int]) -> str:
        quotes = "\n".join(f'  > "{said[n]}" (turn {n})' for n in evidence if n in said)
        return f"- **{text}**\n{quotes}"

    needs = "\n".join(with_quotes(n.need, n.evidence_turns) for n in debrief.most_pressing_needs)
    insights = "\n".join(with_quotes(i.insight, i.evidence_turns) for i in debrief.main_insights)
    return f"""{BANNER}

# User Debrief: {debrief.name}

*Persona {debrief.persona_id}, run {debrief.run}*

**Occupation / role:** {debrief.occupation_role}

## About me and goals
{debrief.about_me_and_goals}

## Most pressing needs
{needs}

## Main insights
{insights}

## Current solutions
{bullets(debrief.current_solutions)}

## Opportunities
{bullets(debrief.opportunities)}
"""


def render_synthesis(report: SynthesisReport, run_count: int) -> str:
    """Lay out the cross-segment report."""
    jobs = "\n".join(f"- **{j.job}** ({', '.join(j.persona_ids)})\n  {j.evidence}" for j in report.shared_jobs)
    return f"""{BANNER}

# Cross-segment synthesis

*Built from {run_count} approved debriefs.*

## Shared jobs
{jobs or "- (none)"}

## Strongest segment: {report.strongest_segment.persona_id}
{report.strongest_segment.why}

## Weakest segment: {report.weakest_segment.persona_id}
{report.weakest_segment.why}

## Claims to verify in real interviews
{bullets(report.claims_to_verify)}

## Caveats
{bullets(report.caveats)}
"""
