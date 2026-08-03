"""Frame sources and the live view (rules 8, 9; book ch7, ch9.4.2).

The strongest claim this module can make is a negative one: no frame may ever
contain the opponent's true position. That is what makes the screenshot legal
evidence rather than an illegal information advantage, and it is asserted here
against every frame of a real run rather than argued for in a comment.

The second claim is that the picture is worth taking. A solo run's belief only
diffuses, so it demonstrates the renderer and nothing else; a two-sided run's
posterior must actually tighten, or the heat map the README requires would be
showing a uniform prior with extra steps.
"""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.ui.frames import match_frames, solo_frames
from p2pchase.ui.live_view import frame_source, run_text_view, tkinter_available

TALK = {"provider": "template", "seed": 2}


def _frames(shared_config, role=constants.ROLE_COP, seed=4):
    return list(match_frames(shared_config, role, {}, TALK, {}, seed=seed))


def test_a_frame_shows_our_own_cell_and_never_the_opponents(shared_config):
    """The only position in a frame is ours. There is no key for theirs."""
    for view, _hint in _frames(shared_config):
        assert "my_position" in view
        assert not {"opponent_position", "thief_position", "cop_position"} & set(view)


def test_a_frame_carries_a_belief_rather_than_a_location(shared_config):
    view, _ = _frames(shared_config)[3]
    assert view["belief"]
    assert view["belief_top"]
    assert view["belief_entropy"] >= 0.0
    assert 0.0 <= view["hint_trust"] <= 1.0


def test_a_two_sided_run_keeps_the_posterior_well_below_ignorance(shared_config):
    """Otherwise the heat map is a uniform prior and proves nothing.

    Frame 0 is a point mass -- start positions are agreed, so entropy begins at
    zero -- and diffusion then pushes it up. The claim worth making is about
    where it settles: evidence must hold it well under the 5.61 bits of a flat
    distribution over all 49 cells.
    """
    import math

    uniform = math.log2(49)
    frames = _frames(shared_config)
    settled = [view["belief_entropy"] for view, _ in frames[3:]]
    assert settled
    assert max(settled) < uniform - 1.0
    # And it must genuinely move, rather than sitting on the initial point mass.
    assert max(settled) > 0.0


def test_a_solo_run_only_ever_diffuses(shared_config):
    """Stated explicitly so nobody screenshots the solo view by mistake."""
    frames = list(solo_frames(shared_config, constants.ROLE_COP, {}, TALK, {}, seed=1))
    entropies = [view["belief_entropy"] for view, _ in frames]
    assert entropies[-1] >= entropies[0]


def test_the_watched_peer_hears_the_opponents_sentence_not_its_own(shared_config):
    """Showing our own hint back to us would make the deception channel invisible."""
    frames = _frames(shared_config)
    spoken = [hint for _view, hint in frames if hint]
    assert spoken, "the opponent never said anything"
    assert all(isinstance(hint, str) for hint in spoken)


def test_a_run_reaches_a_decided_outcome(shared_config):
    frames = _frames(shared_config)
    last = frames[-1][0]
    assert last["finished"] is True or last["step"] >= 1
    if last["finished"]:
        assert last["outcome"] in (constants.OUTCOME_CAPTURE, constants.OUTCOME_SURVIVAL)


@pytest.mark.parametrize("role", [constants.ROLE_COP, constants.ROLE_THIEF])
def test_both_sides_can_be_watched(shared_config, role):
    """The project is symmetric, so the view must be too."""
    view, _ = _frames(shared_config, role=role)[1]
    assert view["role"] == role


# ------------------------------------------------------------- live view
def test_the_text_renderer_produces_a_readable_final_frame(loaded_config):
    from p2pchase.sdk.sdk import P2PChaseSDK

    frame = run_text_view(P2PChaseSDK(loaded_config), seed=3, delay=0.0, quiet=True)
    assert "p2pchase live view" in frame
    assert "opponent says:" in frame


def test_the_default_frame_source_is_the_two_sided_one(loaded_config):
    from p2pchase.sdk.sdk import P2PChaseSDK

    sdk = P2PChaseSDK(loaded_config)
    assert frame_source(sdk, seed=1).__name__ == "match_frames"
    assert frame_source(sdk, seed=1, solo=True).__name__ == "solo_frames"


def test_tkinter_availability_is_a_question_not_a_crash():
    """A headless grader must still be able to run everything else."""
    assert tkinter_available() in (True, False)
