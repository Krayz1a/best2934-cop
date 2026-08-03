"""The vocabulary of the verbal channel (Appendix F Table 14).

Rule 26 requires the inter-agent channel to be natural language; rule 27 forbids
turning it into a numeric position protocol. Landmarks are how those two rules
are satisfied at once: "past Grand Central, heading north" carries real
information about direction without ever encoding a coordinate.

The arena is negotiable. ``map_area = "New York"`` is the book's default; an
empty string falls back to a generic street vocabulary so two teams who agree on
no arena still speak the same language.
"""

from __future__ import annotations

import random

LANDMARKS: dict[str, list[str]] = {
    "New York": [
        "Times Square", "Central Park", "Brooklyn Bridge", "Wall Street",
        "Harlem", "the East River", "Chinatown", "the Bowery", "Queens",
        "the Bronx", "Coney Island", "Grand Central",
    ],
    "": [  # generic fallback when no arena is agreed
        "the north gate", "the old market", "the river", "the tower",
        "the alley", "the rooftops", "the docks", "the square",
    ],
}

HEADINGS: dict[str, str] = {
    "N": "north",
    "S": "south",
    "E": "east",
    "W": "west",
    "STAY": "nowhere",
}


def pick_landmark(map_area: str, rng: random.Random) -> str:
    """Choose a landmark from the agreed arena, or the generic pool."""
    pool = LANDMARKS.get(map_area) or LANDMARKS[""]
    return rng.choice(pool)


def heading_word(move: str) -> str:
    """Render a move as a compass word, never as an axis delta."""
    return HEADINGS.get(move, "somewhere")
