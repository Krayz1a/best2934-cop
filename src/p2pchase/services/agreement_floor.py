"""The floor beneath the omission rule: what a greeting must contain to be one.

Every comparison in :meth:`NegotiationService.compare` is guarded by "refuse
only when BOTH peers declare and the values differ". Each of those guards was
added deliberately, for a good reason, and each is individually right -- the
league's peers do not all speak the same fields, and comparing a field the
other side has never heard of refuses opponents over our own vocabulary. Rule
31 needs opponents; four separate times, strictness was the thing standing
between us and one.

Composed, they invert. ``config_sha256`` silent, ``terms`` absent, both scent
locks empty, ``schema_version`` unset, ``group_id`` absent-so-never-colliding:
zero mismatches, ``agreed: true``. **The emptier the message, the more
agreeable we are.** imreeyal found it with a liveness probe on 2026-08-09 --
an empty payload, and we told them we had an agreement.

That is worse than a strict gate, because it is a gate that reports success.
Two peers who never agreed anything can open a counted series on it, and rule
35 voids the sub-game for both when the two reports disagree about a game
neither had terms for.

So the omission rule stays exactly as it is, per field, and this module sets
the floor under all of it. Two requirements, both about the message rather
than its values:

* **Name yourself.** ``group_id`` is not one term among fourteen -- it selects
  which fourteen. Our scent model and role convention are per-pairing
  (``setup["opponents"]``), so an unnamed caller is not compared loosely, it is
  compared against *the wrong opponent's terms*. This is the same root as the
  second thing imreeyal's probe saw: their anonymous greeting was answered with
  ``multiplicative_book_v1``, the default, where this pairing agreed
  ``subtractive_chebyshev_v1``. One cause, two symptoms.

* **Declare something comparable.** A peer that sends nothing checkable has not
  made an agreement we can hold either side to. This does not name any
  particular field -- any one of the five will do -- so it stays true as the
  league's vocabulary drifts, which is precisely what the omission rule was
  protecting.

Neither refusal can turn away a real opponent. gal-roy1, imreeyal and anrbj666
all name themselves and all carry CORE terms; ``Handshake.from_dict`` reads
``identity.group_id`` from the reference-v3 shape as well as the flat one, so
the requirement is on the *information*, not on a spelling.
"""

from __future__ import annotations

from typing import Any

#: Any one of these makes a greeting checkable. Deliberately a list of "things
#: we know how to compare" rather than a required set: the whole point of the
#: omission rule is that no single one of them is mandatory.
COMPARABLE = ("terms", "config_sha256", "scent_fingerprint", "scent_model_sha256",
              "schema_version")


def refusals(theirs: Any) -> list[str]:
    """Reasons this message is not an agreement at all, before any value is compared.

    Input:  ``theirs`` -- the opponent's parsed :class:`Handshake`.
    Output: mismatch strings, empty when the greeting clears the floor.
    """
    problems: list[str] = []
    if not str(getattr(theirs, "group_id", "") or "").strip():
        problems.append(
            "group_id: absent. We cannot agree with a peer who does not name "
            "themselves -- the scent model and role convention are per-pairing "
            "terms selected by your group_id, so an unnamed greeting would be "
            "answered with our defaults and those are the wrong terms for "
            "someone. Send group_id at the top level or in identity.group_id."
        )
    if not any(getattr(theirs, name, "") for name in COMPARABLE):
        problems.append(
            "nothing to compare: none of " + ", ".join(COMPARABLE) + " was "
            "declared. Each of those is individually optional -- we refuse only "
            "when both peers declare and differ -- but a greeting carrying none "
            "of them states no game, and agreeing to it would be a report of "
            "success with nothing behind it."
        )
    return problems
