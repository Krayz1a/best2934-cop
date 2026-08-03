"""best2934 — distributed Cops-and-Robbers over a peer-to-peer network.

Two symmetric autonomous agents chase each other across a shared grid with no
central server and no referee. Neither ever sees the objective board: each holds
only its own truth plus whatever the opponent chooses to disclose, which makes
the whole thing a decentralised partially observable Markov decision process.

Public entry point is :class:`p2pchase.sdk.P2PChaseSDK`. Every consumer -- CLI,
GUI, tests, future integrations -- goes through it and never reaches into the
internal modules directly (guidelines §4.1).
"""

from .shared.version import CODE_VERSION as __version__

__all__ = ["__version__"]
