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

    Numbers stay distinct because a retry re-sends the same one and the fact
    worth keeping is *which* numbers were claimed, not how often. A repeat moves
    to the END rather than being dropped where it first appeared, so the last
    entry is always the most recently declared number -- which is what
    :func:`opening_sub_game` reads. Keeping first-seen order instead looked
    tidier and was wrong: a six-sub-game series that revisits a number would
    have opened on a declaration several sub-games stale.

    Keys are not de-duplicated, because two openings are two events even when
    they look alike.
    """
    session.declaration_keys.append(sorted(map(str, payload)))
    if "sub_game_number" in payload:
        number = int(payload.get("sub_game_number", 0) or 0)
        session.declared_sub_games[:] = [
            n for n in session.declared_sub_games if n != number] + [number]


def declared_sub_game(payload: dict[str, Any], session: Any) -> int:
    """The number to judge this sub-game's roles against: THEIRS, not ours.

    The step-0 role check used ``session.sub_game`` -- our own local counter --
    and never read what the caller declared. On 2026-08-16 gal-roy1 dialled a
    correct sub-game 4 (``first_half`` makes us the thief there, and thief is
    what we were serving) while our counter still read 1, which makes us the
    cop. The guard compared their role against *our* number, invented a clash
    that did not exist, and refused a dial that was right.

    So it was validating a fiction: it could only agree with the opponent when
    our counter happened to track their series, which is the one thing a local
    counter cannot be assumed to do. The declared number is the shared fact.

    Falling back to the counter when they declare nothing preserves the old
    behaviour for peers that send no number, which is the only case where ours
    is the best answer available.
    """
    return int(payload.get("sub_game_number", 0) or 0) or int(session.sub_game)


def opening_sub_game(payload: dict[str, Any], session: Any, played: bool) -> int:
    """Which sub-game an opening turn starts. Theirs first, ours only as a last resort.

    Precedence, and each step exists because the one after it got something wrong:

    1. the number on the opening turn itself, when the peer sends one;
    2. the last number they declared at step 0, which arrives *before* the
       opening turn and is the shared fact this whole module exists to keep;
    3. our own counter, incremented -- a guess, and only when they have told us
       nothing at all.

    gal-roy1's driver declares the number at ``declare_step0`` and omits it from
    the opening ``submit_turn``, so before (2) existed we fell straight through
    to (3). That is Finding 2, and left alone it would have voided tomorrow's
    counted series rather than merely mislabelling a throwaway: their agreed
    order is one alignment throwaway and then the six, in a single process, so
    the counter would have labelled the six **2..7** while our own shape guard
    demands exactly 1..6 once each. A refusal at settlement, on the game that
    counts, from a disagreement neither team would have seen coming.
    """
    number = int(payload.get("sub_game_number", 0) or 0)
    declared = [n for n in getattr(session, "declared_sub_games", []) if n]
    return number or (declared[-1] if declared else session.sub_game + (1 if played else 0))


def step0_role_check(payload: dict[str, Any], session: Any,
                     config: Any) -> tuple[int, str, str]:
    """The sub-game the caller declared, their role, and why it is unplayable.

    Returns ``(number, clash, their_role)``; ``clash`` is empty when sound.
    The check is judged against ``number`` -- see :func:`declared_sub_game` for
    why our own counter is the wrong yardstick and what it cost.

    A peer that declares no role at all is accepted, because we cannot check
    what nobody stated.
    """
    from ..domain import roles

    theirs = roles.normalise_role(str(payload.get("role", "")))
    opponent = str(payload.get("group_id", "") or payload.get("group_name", "")
                   or session.opponent)
    number = declared_sub_game(payload, session)
    clash = roles.role_clash(session.role, theirs, session.group_id, opponent, number,
                             config.num_sub_games, config.role_convention(opponent))
    return number, str(clash or ""), theirs


def outstanding_clash(session: Any) -> str:
    """Why every call in this sub-game is refused, or ``""`` if none is.

    ``declare_step0`` detected a role clash, logged it, returned an error -- and
    the sub-game then played all thirty-five turns, because each later
    ``submit_turn`` was judged on its own merits. That produced a complete,
    plausible, sealed artifact for a sub-game we had already declined.

    A refusal that refuses only the call it was raised on is worse than no check
    at all: it writes an ERROR line nobody reads and leaves evidence that looks
    exactly like consent.
    """
    return str(getattr(session, "role_clash", "") or "")
