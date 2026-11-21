"""The interviewer check: flag leading questions and questions about the future.

This one is plain code, not a model. The patterns are cheap, predictable and
easy to argue with in class. They miss subtle cases, which is what the devil's
advocate is for, and they flag some fair questions, which is why a flag is a
warning for a person to read, not a failure.
"""

import re

from harness.schemas import Turn

PATTERNS = {
    "leading": [
        r"\bwouldn'?t it\b", r"\bdon'?t you (think|feel|agree)\b", r"\bisn'?t (it|that)\b",
        r"\bmust have been\b", r"\bi bet\b", r",\s*right\?$", r"\bsurely\b",
    ],
    "future": [
        r"\bwould you\b", r"\bwill you\b", r"\bif (you|there) (had|were|could)\b",
        r"\bimagine\b", r"\bhow likely\b", r"\bwould it help\b", r"\bin the future\b",
    ],
}


def check_questions(turns: list[Turn]) -> list[dict]:
    """Return one entry for each interviewer question that matches a pattern."""
    flagged = []
    for turn in turns:
        if turn.speaker != "interviewer":
            continue
        text = turn.text.lower().strip()
        flags = [kind for kind, patterns in PATTERNS.items() if any(re.search(p, text) for p in patterns)]
        if flags:
            flagged.append({"turn": turn.turn, "question": turn.text, "flags": flags})
    return flagged
