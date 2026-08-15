"""Keep what an opponent's opening payload ACTUALLY carried.

`opponent_declared_sub_games` was added so that a numbering disagreement could
be settled from an artifact instead of argued from two teams' recollections.
It could not do it, because it records our *parse* rather than their *arrival*:
the extractor reads ``payload.get("sub_game_number", 0)``, and a **missing** key
and a declared ``0`` both come out as ``0``.

On 2026-08-16 the gal-roy1 throwaway logged exactly that -- ``[0]`` on the first
sub-game, the key absent on the second -- and that reading was consistent with
three different stories:

* they declared ``0``;
* they declared nothing;
* they declared it under a spelling we do not read.

Only the first is theirs to answer for, and we could not tell which it was, so
we had to say so rather than answer a question they had asked twice.

The key names separate them. They are cheap, they are the opponent's own bytes,
and they are the half of the evidence that survives a parse we got wrong --
which is the half worth keeping, since the parse is the thing under suspicion.
"""

from __future__ import annotations

from typing import Any


def note_declaration(session: Any, payload: dict[str, Any]) -> None:
    """Record one opening payload's keys, and its number when it carried one.

    Both are appended in arrival order and neither replaces the other. A
    populated key list beside an absent number reads "they opened, and nothing
    we recognise carried a sub-game number" -- a sentence about them, which is
    the sentence a settlement needs and the one ``[0]`` could not express.

    Numbers are de-duplicated because a retry re-sends the same one and the
    fact worth keeping is *which* numbers were claimed, not how often. Keys are
    not, because two openings are two events even when they look alike.
    """
    session.declaration_keys.append(sorted(map(str, payload)))
    if "sub_game_number" in payload:
        number = int(payload.get("sub_game_number", 0) or 0)
        session.declared_sub_games[:] = dict.fromkeys(
            [*session.declared_sub_games, number])
