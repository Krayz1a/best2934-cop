"""The kit's CORE pre-game agreement: fourteen flat terms, a nonce, a signature.

Our handshake published nine fields about *us* -- group id, code version, the
config digest, the scent locks -- and not one of the terms themselves. That is a
greeting, not an agreement, and imreeyal's gate refused it in as many words: "a
bookletter-shaped greeting under a reference wire". Their gate is right and ours
was the incomplete one. Two peers cannot agree on the physics by exchanging
*hashes of differently-shaped objects*; they agree by exchanging the values.

So this module speaks the league's shape instead of ours. The fourteen keys, the
canonical serialisation and the signature construction are all pinned by the
kit's CORE vector ``vectors/terms_signature.json``, which we reproduce in the
tests rather than trusting anyone's description of it -- including our own.

**The separator is a single ``|`` and this is not a detail.** The kit states the
construction as ``SHA256(canonical_json(terms)|nonce)``. In correspondence it was
restated to us as ``canonical_json(terms) || nonce``, which reads naturally as
either a C-style "concatenate" or a literal double pipe. All three readings are
plausible and only one reproduces the published vector::

    concat      d2c5d275566b3098...   no
    "|"         80793141f22b6193...   the vector
    "||"        d5d53f27356eaea0...   no

A peer that picks either of the other two produces a signature that verifies
against nothing, on every handshake, with no diagnostic beyond "signature
mismatch". We only know which one is right because the vector exists.
"""

from __future__ import annotations

from typing import Any

from .crypto import canonical_json, new_nonce, sha256_hex

#: The fourteen keys of a CORE agreement, in the kit's spelling. Order is
#: irrelevant to the signature -- :func:`canonical_json` sorts -- but the *set*
#: is not: a missing or extra key changes the digest completely.
CORE_KEYS = (
    "board_size", "smell_grid_size", "decay_per_step", "emit_intensity",
    "min_center_intensity", "max_steps", "barriers_max", "setting",
    "hint_max_words", "axis_origin_corner", "axis_start_index",
    "thief_start", "cop_start", "num_games",
)

#: The floor on the emission centre after decay. It has no home in ``game.json``
#: because our own engine never needed it as a separate parameter -- it lives
#: inside the registered scent document. The league's terms carry it explicitly,
#: so it is read from the same constant the locked document is built from rather
#: than written down a second time here.
MIN_CENTER_INTENSITY = 0.5


def core_terms(shared: dict[str, Any]) -> dict[str, Any]:
    """Our game config, restated in the league's fourteen flat keys.

    A translation, not a second source of truth: every value is read out of the
    shared config that already governs play. If the two could drift, we would be
    signing terms we do not run -- which is the one failure a signature is
    supposed to make impossible.

    ``max_steps`` comes from ``survival_threshold`` rather than ``max_moves``.
    We carry both and they are equal at 35; imreeyal carries both, is also at
    35, and also reads ``survival_threshold``. If either of us ever moves one,
    the other has to be told -- agreed explicitly, and noted here because the
    equality is what hides the choice.
    """
    board = shared["board_and_agents"]
    world = shared["world"]
    movement = shared["movement_and_barriers"]
    pheromones = shared["pheromones"]
    league = shared["network_and_league"]
    return {
        "board_size": int(board["grid_size"]),
        "smell_grid_size": int(pheromones["pheromone_grid_size"]),
        "decay_per_step": float(pheromones["pheromone_decay"]),
        "emit_intensity": float(pheromones["pheromone_center_intensity"]),
        "min_center_intensity": MIN_CENTER_INTENSITY,
        "max_steps": int(movement["survival_threshold"]),
        "barriers_max": int(movement["max_barriers"]),
        "setting": str(world["map_area"]),
        "hint_max_words": int(world["hint_max_words"]),
        "axis_origin_corner": str(board["axis_origin_corner"]),
        "axis_start_index": int(board["axis_start_index"]),
        "thief_start": list(board["thief_start"]),
        "cop_start": list(board["cop_start"]),
        "num_games": int(league["num_sub_games"]),
    }


def sign_terms(terms: dict[str, Any], nonce: str) -> str:
    """``SHA256(canonical_json(terms)|nonce)`` -- the kit's CORE construction.

    The same shape as a commit (:mod:`p2pchase.domain.crypto`), over the agreed
    terms instead of over a move. The nonce is *not* secret here: unlike a
    commitment there is nothing to brute-force, because the terms travel in the
    clear beside it. It is there so the signature binds to this exchange rather
    than being replayable from a previous one.
    """
    return sha256_hex(f"{canonical_json(terms)}|{nonce}")


def signed_agreement(shared: dict[str, Any], nonce: str = "") -> dict[str, Any]:
    """Our CORE agreement, ready to put on the wire."""
    terms = core_terms(shared)
    nonce = nonce or new_nonce()
    return {"terms": terms, "nonce": nonce, "signature": sign_terms(terms, nonce)}


def signature_verifies(terms: dict[str, Any], nonce: str, signature: str) -> bool:
    """Whether a peer's own signature matches the terms it sent.

    Checked before comparing their terms to ours, because the two failures mean
    different things: a bad signature says their agreement is internally
    inconsistent (or that they built it differently -- see the ``|`` note in the
    module docstring), while a value mismatch says we disagree about the game.
    Reporting the second when the first is true sends the humans to the wrong
    file.
    """
    return bool(signature) and sign_terms(terms, nonce) == signature


def term_differences(ours: dict[str, Any], theirs: dict[str, Any]) -> list[str]:
    """Every one of the fourteen values the two peers disagree about.

    All of them, not the first: a peer that fixes one term per round trip and
    rediscovers the next is a pairing that spends its window on the handshake.
    A key missing on either side is reported as a difference rather than skipped
    -- the CORE set is fixed, so an absent key is a malformed agreement and not
    an omission the omission rule protects.
    """
    return [f"terms.{key}: ours={ours.get(key)!r} theirs={theirs.get(key)!r}"
            for key in CORE_KEYS if ours.get(key) != theirs.get(key)]
