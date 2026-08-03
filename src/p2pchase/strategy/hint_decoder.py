"""Reading the opponent's sentence back out (book ch6.5, rules 26, 27).

A verbal channel nobody parses is decoration. This module is the receiving half
of the deception game: it pulls a direction claim out of free-form English so
the claim can be cross-examined against the scent trail.

The distinction that makes the channel meaningful is between the two things an
opponent discloses at REVEAL:

* the **move**, which is sealed in the commitment and therefore always truthful;
* the **hint**, which is free text and may assert anything at all.

Decoding the move would be pointless -- it cannot lie, so cross-examining it can
only ever confirm honesty. It is the hint that carries deception, so it is the
hint we decode and the hint we score. An opponent whose sentences keep
contradicting its trail is the one whose future sentences stop moving our belief.

Deliberately forgiving: we scan for a compass word anywhere in the sentence and
give up quietly when there is none. A hint we cannot parse is simply
uninformative, which is a normal outcome, not an error -- and treating it as one
would let an opponent silence our estimator by writing prettier sentences.
"""

from __future__ import annotations

import re

#: Word -> canonical move. Ordered longest-first so "north-east" is not read as
#: "north"; a compound bearing is ambiguous and we would rather claim nothing.
_HEADING_WORDS: dict[str, str] = {
    "north": "N",
    "south": "S",
    "east": "E",
    "west": "W",
    "nowhere": "STAY",
}

_COMPOUND = re.compile(
    r"\b(?:north|south)[\s-]*(?:east|west)\b|\b(?:north|south)(?:east|west)\b",
    re.IGNORECASE,
)
_SIMPLE = re.compile(r"\b(north|south|east|west|nowhere)\b", re.IGNORECASE)


def heading_from_hint(hint: str) -> str | None:
    """Extract the direction a sentence claims, or ``None`` if it claims none.

    Returns ``None`` for a compound bearing: "north-east" is consistent with two
    different moves, and a claim that cannot be checked should not be scored.
    """
    if not hint:
        return None
    text = str(hint)
    if _COMPOUND.search(text):
        return None
    match = _SIMPLE.search(text)
    if match is None:
        return None
    return _HEADING_WORDS[match.group(1).lower()]


def opposite(move: str) -> str:
    """The heading a liar would name instead of the one it took."""
    return {"N": "S", "S": "N", "E": "W", "W": "E"}.get(move, "STAY")
