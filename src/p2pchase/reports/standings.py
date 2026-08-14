"""The three ``final_result`` fields the lecturer's standings are built from.

``games_played_including_this``, ``first_meeting_between_groups`` and
``diversity_reward_applied``. They are not in the reference implementation's
sample artifact, which is why we did not emit them until 2026-08-14 and why we
declined them once before adopting them.

**On the source, honestly.** imreeyal cites the book's attached example set --
the ``1-pre-game-declaration`` / ``2-config`` / ``3-log`` / ``4-final-result``
family, book section 9.2.1 -- whose ``final_result`` block has nine keys
including these three. **We do not hold that file.** It is not in ``booklet.txt``,
the guidelines, or the assignment ``.docx``, and the reference implementation's
own sample has the other six and stops. So this is adopted on a citation we
cannot check, which is a thing worth writing down rather than glossing.

Four reasons it is still the right call:

* The same file settled the tie rule on 2026-08-06, and imreeyal's quotations of
  it are consistent six days apart, down to the ``32 / 12`` totals.
* The concept is course-level regardless: ``diversity_reward: 10`` sits in the
  reference's own ``game.json``. The reward exists; only the field was in doubt.
* The asymmetry. If the fields are the course's and we omit them, the standings
  under-credit us and we never find out. If they are not, we carry three keys
  outside the consensus scope, which can void nothing.
* Emitting them *removes* the last ``final_result`` difference between our
  report and imreeyal's rather than creating one -- the opposite of ``raw_score``
  and ``tie_rule``, which were ours alone and therefore a diff to explain.

**The derivations must be checkable, not merely plausible**, because a field
both teams emit from different definitions is worse than a field neither emits:
it agrees on the name and disagrees on the number, at settlement. So each one
below reproduces what imreeyal actually emitted for the 2026-08-14 friendly --
``{imreeyal: 5, best2934: 0}``, ``true``, ``{false, false}`` -- and the test
pins that.
"""

from __future__ import annotations

from typing import Any

from .history import counted_games_played, counted_opponents


def standings_block(mine: str, opponent: str, counted: bool,
                    opponent_games: int = 0,
                    directory: Any = None) -> dict[str, Any]:
    """The three standings fields, derived from our own ledger.

    ``opponent_games`` is *their* declared count and cannot be derived here --
    rule 37 makes each team declare its own, and we record what they declared
    rather than inventing it. Zero when they have not told us, which is honest
    about an unknown rather than a claim that they have played none.
    """
    first_meeting = opponent not in counted_opponents(directory)
    ours = counted_games_played(directory) + (1 if counted else 0)
    return {
        "games_played_including_this": {mine: ours, opponent: int(opponent_games)},
        "first_meeting_between_groups": first_meeting,
        "diversity_reward_applied": {
            mine: counted and first_meeting,
            opponent: counted and first_meeting,
        },
    }
