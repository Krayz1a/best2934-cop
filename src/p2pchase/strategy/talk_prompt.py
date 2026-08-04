"""The contract between the game and whatever writes the taunt.

Two things live here, and both are about limiting what a provider can do.

:class:`TalkRequest` is deliberately narrow. A provider sees our own local view
and the honesty we already committed to -- never the opponent's true position
(we do not have it) and never any authority over the move (rule 25).

:func:`clamp_words` enforces the agreed word limit locally. The limit is a
negotiated term of the match, so it cannot be left to a model's cooperation:
whatever comes back is truncated before it goes anywhere near the wire.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Returned when a provider yields nothing usable, so a hint is never empty.
FALLBACK_HINT = "Still here."


@dataclass(frozen=True)
class TalkRequest:
    """Everything a provider may see when composing a hint."""

    role: str
    step: int
    intent: str  # "truth" | "lie"
    heading: str  # the direction we actually moved, in words
    landmark: str
    max_words: int
    steps_remaining: int


class TalkProvider(Protocol):
    """Building-block interface every talk provider implements."""

    name: str

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        """Return ``(hint, tokens_used)``."""
        ...


def system_prompt(request: TalkRequest) -> str:
    """The word limit and the coordinate ban are stated to the model explicitly."""
    honesty = (
        "This message must be MISLEADING but must never state a coordinate."
        if request.intent == "lie"
        else "This message must be TRUTHFUL about your direction."
    )
    return (
        f"You are the {request.role} in a pursuit game played on a hidden grid. "
        f"Write one taunt of at most {request.max_words} words in natural English. "
        f"{honesty} "
        "Never write numbers, grid coordinates, row/column indices or any direct "
        "position encoding -- speak only in landmarks and directions. "
        "Reply with the sentence and nothing else."
    )


def build_prompt(request: TalkRequest) -> str:
    """The per-turn user message: what just happened, in the agent's own terms."""
    return (
        f"You just moved {request.heading}, near {request.landmark}. "
        f"Step {request.step}, {request.steps_remaining} steps left. "
        "Write the taunt."
    )


#: Words that only ever appear in a sentence trying to name a square.
POSITION_WORDS = frozenset({"row", "rows", "column", "columns", "col", "cols",
                            "coordinate", "coordinates", "index", "cell"})


def strip_positions(text: str) -> str:
    """Remove anything that could encode a square (rule 27).

    Rule 27 forbids a numeric position protocol, and rule 26 requires free
    natural language. The system prompt asks a model for both; this enforces
    them. A prompt is a request, and a request is not a guarantee -- a provider
    that returns "heading to 3,4" would breach a rule whose sanction is losing
    the game's character, and no taunt is worth that.

    Digit-bearing tokens go, along with the vocabulary that only exists to point
    at a square. Deleting is deliberately preferred to refusing: a hint is
    optional, so degrading to a shorter sentence costs nothing, while raising
    here would turn a chatty model into a technical loss.
    """
    kept = [word for word in str(text).split()
            if not any(char.isdigit() for char in word)
            and word.strip(".,;:!?\"'").lower() not in POSITION_WORDS]
    return " ".join(kept)


def clamp_words(text: str, max_words: int) -> str:
    """Hard-enforce the agreed word limit, whatever the model returned."""
    cleaned = " ".join(str(text).replace("\n", " ").split())
    if not cleaned:
        return FALLBACK_HINT
    words = cleaned.split(" ")
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words])
