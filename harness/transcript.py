"""Append-only transcript writer.

Each turn is written to disk the moment it happens. If an interview crashes
at turn 14, the first 13 turns are still there to read, and nothing ever
rewrites a turn after the fact.
"""

from datetime import datetime, timezone
from pathlib import Path

from harness.schemas import Turn

SPEAKER_LABELS = {"interviewer": "Interviewer", "user": "Interviewee"}


class Transcript:
    """The turns of one interview, kept in memory and in a JSONL file."""

    def __init__(self, path: Path):
        """Start a fresh transcript at `path`, replacing any earlier run's file."""
        self.path = path
        self.turns: list[Turn] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")

    def add(self, speaker: str, text: str, tokens: int = 0) -> Turn:
        """Record one turn and append it to the file straight away."""
        turn = Turn(
            turn=len(self.turns) + 1,
            speaker=speaker,
            text=text.strip(),
            tokens=tokens,
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.turns.append(turn)
        with open(self.path, "a") as f:
            f.write(turn.model_dump_json() + "\n")
        return turn

    def render(self) -> str:
        """Return the transcript as plain text for the next agent's prompt.

        Turn numbers stay visible so the debrief agent can cite them later.
        """
        if not self.turns:
            return "(The interview hasn't started yet.)"
        return "\n\n".join(f"[{t.turn}] {SPEAKER_LABELS[t.speaker]}: {t.text}" for t in self.turns)

    @classmethod
    def load(cls, path: Path) -> list[Turn]:
        """Read a saved transcript back into Turn objects."""
        return [Turn.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
