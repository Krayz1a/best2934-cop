"""The driver must build a counted-aware writer, not just be handed one.

On 2026-08-15 we flipped `counted` for imreeyal, announced it on the league
thread, and verified twice that `NetworkArtifactService` honoured it. Then the
opening sub-game of our first counted series was written into the **friendly**
tree, on top of a friendly log of the same name, and `refresh_result` assembled
one counted sub-game together with five friendly ones.

The result read 75-35 with an unchanged digest, because both openers happened
to be police-survival. A wrong artifact that looks exactly like the right one
is the only kind that survives a settlement.

`for_opponent` reads the flag from the pairing so no caller can forget it, and
we had wired it into the opponent-driven `served_recorder`. We *drive* this
pairing, and the driver came through the SDK, which built the service with the
plain constructor whose `counted` defaults to False.

The quarantine tests were not wrong. They tested the service. Nothing tested
how the driver built it -- so these tests are about construction, at the seam
where the flag was dropped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from p2pchase.shared.paths import COUNTED_SUBDIR


@pytest.fixture
def sdk_for(monkeypatch, tmp_path):
    """An SDK whose recording is captured rather than performed."""
    from p2pchase.sdk import sdk as sdk_module

    def _build(counted_opponents: set[str]):
        seen: dict[str, object] = {}

        class _Service:
            def __init__(self, config, output_dir=None, counted=False):
                self.counted = counted
                self.output_dir = Path(output_dir or tmp_path)

            @classmethod
            def for_opponent(cls, config, opponent, output_dir=None):
                seen["opponent"] = opponent
                return cls(config, output_dir, counted=opponent in counted_opponents)

            def record_sub_game(self, *args, **kwargs):
                seen["counted"] = self.counted
                seen["dir"] = self.output_dir
                return []

        monkeypatch.setattr(sdk_module, "NetworkArtifactService", _Service)
        return seen

    return _build


def _record(sdk, opponent):
    class _Outcome:
        outcome, records, opponent_audit, steps = "capture", [], {}, 15

    sdk.record_networked_sub_game("best2934-vs-" + opponent, 1, opponent,
                                  _Outcome(), "s", "e", 0)


def test_a_counted_pairing_makes_the_driver_build_a_counted_writer(peer_config,
                                                                  sdk_for, tmp_path):
    """The exact defect: the driver dropped the flag on the floor."""
    from p2pchase.sdk.sdk import P2PChaseSDK

    seen = sdk_for({"imreeyal"})
    _record(P2PChaseSDK(peer_config, output_dir=tmp_path), "imreeyal")

    assert seen["counted"] is True


def test_a_friendly_pairing_still_writes_to_the_friendly_tree(peer_config, sdk_for,
                                                             tmp_path):
    from p2pchase.sdk.sdk import P2PChaseSDK

    seen = sdk_for({"imreeyal"})
    _record(P2PChaseSDK(peer_config, output_dir=tmp_path), "gal-roy1")

    assert seen["counted"] is False


def test_the_flag_is_looked_up_by_the_opponent_actually_played(peer_config, sdk_for,
                                                              tmp_path):
    """It must come from the pairing, never from a cached or default service."""
    from p2pchase.sdk.sdk import P2PChaseSDK

    seen = sdk_for({"imreeyal"})
    _record(P2PChaseSDK(peer_config, output_dir=tmp_path), "imreeyal")

    assert seen["opponent"] == "imreeyal"


def test_the_cached_property_is_not_what_records_a_sub_game(peer_config, sdk_for,
                                                            tmp_path):
    """`network_artifacts` has no opponent, so it cannot know the flag.

    Touching it first must not poison the recording -- the bug was a cached,
    counted-blind service being reused for a counted sub-game.
    """
    from p2pchase.sdk.sdk import P2PChaseSDK

    seen = sdk_for({"imreeyal"})
    sdk = P2PChaseSDK(peer_config, output_dir=tmp_path)
    assert sdk.network_artifacts.counted is False   # warm the cache

    _record(sdk, "imreeyal")

    assert seen["counted"] is True


def test_the_real_service_routes_a_counted_pairing_below_the_friendly_tree(peer_config,
                                                                          tmp_path):
    """No mocks: the genuine class, so the directory contract is checked too."""
    from p2pchase.services.network_artifacts import NetworkArtifactService

    peer_config.setup.setdefault("opponents", {}).setdefault("imreeyal", {})
    peer_config.setup["opponents"]["imreeyal"]["counted"] = True

    service = NetworkArtifactService.for_opponent(peer_config, "imreeyal")

    assert service.counted is True
    assert service.output_dir.name == COUNTED_SUBDIR
