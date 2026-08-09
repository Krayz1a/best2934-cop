"""The league's commitment construction, which is not ours.

Two peers can agree every one of the fourteen CORE terms, verify each other's
signatures, play thirty-five clean rounds -- and still fail every step of the
mutual audit, because they never agreed how a commitment is *built*. That is
not a hypothetical: on 2026-08-09 we played imreeyal six sub-games end to end
and audited 0 of 36 steps in all six, with nothing forged and nothing withheld.
Every step arrived and every step failed to re-hash.

The two constructions:

    ours  sha256(canonical_json({**payload, "nonce": nonce}))   nonce merged in
    kit   sha256(canonical_json(payload) + "|" + nonce)         nonce appended

The kit's ``turn_message`` field note is explicit -- ``SHA256(canonical_json(
payload)|nonce), a SINGLE pipe`` -- and that document is PROMOTED, carrying two
completed counted six-sub-game series between independently written peers. On
their wire, theirs is the correct spelling and ours is the deviation.

Both are sound commitments: each binds the payload to the nonce and neither can
be opened two ways. Nothing here is a security choice -- it is a spelling
choice, and the only wrong answer is for the two peers to pick differently.

**Why this is per-pairing rather than global.** gal-roy1 audit our chains under
*our* construction and it works -- that is how they proved the rule 46 defect
from our own sealed records. Switching everyone to the kit form to reach
imreeyal would break the one opponent we already agree with, which is the same
trade we have refused four times in :func:`NegotiationService.compare`. So the
form is declared per opponent in ``setup["opponents"]``, beside ``scent_model``
and ``role_convention``, and defaults to ours.

**Verification is deliberately more generous than sealing.** We seal in the one
form this pairing agreed, and we accept either. Accepting both costs no
integrity -- a peer still cannot open a commitment two ways -- and it means an
honest opponent whose spelling we guessed wrong fails nothing. Refusing on a
spelling is how six clean sub-games became six worthless audits.
"""

from __future__ import annotations

import secrets
from typing import Any

from .crypto import canonical_json, digest_payload, sha256_hex

#: Our own construction: the nonce merged into the payload before hashing.
MERGED = "merged_nonce_v1"

#: The league's: canonical payload, one pipe, the nonce. copthief-league-protocol
#: SPEC section 4, carried by the PROMOTED reference-v3 turn message.
PIPE = "kit_pipe_v1"

DEFAULT_FORM = MERGED
FORMS = (MERGED, PIPE)


def seal(payload: dict[str, Any], nonce: str, form: str = DEFAULT_FORM) -> str:
    """The commitment for ``payload`` under the named construction.

    An unknown form falls back to ours rather than raising. This runs inside a
    live sub-game: a typo in a config file should not forfeit the match under
    rule 6, and the audit will say plainly that the spellings disagreed.
    """
    if form == PIPE:
        return sha256_hex(f"{canonical_json(payload)}|{nonce}")
    sealed = dict(payload)
    sealed["nonce"] = nonce
    return digest_payload(sealed)


def opens(payload: dict[str, Any], nonce: str, announced: str) -> bool:
    """Does ``announced`` open under *either* construction?

    Constant-time per candidate, and it does not short-circuit on the first
    match in a way that leaks which form the peer used -- there is nothing
    secret about the form, but the comparison itself stays constant-time
    because that is what :func:`secrets.compare_digest` is for.
    """
    return any(secrets.compare_digest(seal(payload, nonce, form), announced)
               for form in FORMS)
