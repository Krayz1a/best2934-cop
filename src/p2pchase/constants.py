"""Project-wide constants.

Every quantitative value in this project is owned by the binding parameter
table (book Appendix F) and reaches the code through ``config/game.json``.
The values mirrored here are DEFAULTS ONLY -- they are what the code falls
back to when the shared, agreed config does not specify a key, exactly as
Appendix F requires ("in the absence of an explicit agreement between the
parties, the code must ensure the example value is the default").

Nothing here may be lowered. Parameters marked PERMANENT in Appendix F must
not change at all; deviation disqualifies the team.
"""

from __future__ import annotations

from typing import Final

CODE_VERSION: Final[str] = "1.0.0"
BOOK_VERSION: Final[str] = "3.0.0"
SCHEMA_VERSION: Final[str] = "1.2"

# --- Appendix F, Table 13: board, axes and start positions -----------------
GRID_SIZE: Final[int] = 7  # minimum
NUM_AGENTS: Final[int] = 2  # permanent
AXIS_ORIGIN_CORNER: Final[str] = "top-left"  # negotiable
AXIS_START_INDEX: Final[int] = 0  # negotiable
THIEF_START: Final[tuple[int, int]] = (3, 3)  # negotiable
COP_START: Final[tuple[int, int]] = (0, 0)  # negotiable

# --- Appendix F, Table 14: arena and verbal hints --------------------------
MAP_AREA: Final[str] = "New York"  # negotiable; "" => generic landmarks
HINT_MAX_WORDS: Final[int] = 15  # negotiable

# --- Appendix F, Table 15: movement and barriers ---------------------------
MOVE_SET: Final[tuple[str, ...]] = ("N", "S", "E", "W", "STAY")  # permanent
MAX_BARRIERS: Final[int] = 14  # minimum
MAX_MOVES: Final[int] = 35  # minimum
SURVIVAL_THRESHOLD: Final[int] = 35  # minimum

# --- Appendix F, Table 16: dynamic pheromones (ALL PERMANENT) --------------
PHEROMONE_CENTER_INTENSITY: Final[float] = 0.9
PHEROMONE_DECAY: Final[float] = 0.10
PHEROMONE_GRID_SIZE: Final[int] = 5

# Not an Appendix F term: an agreed reading of book ch4, negotiated per pairing
# (interop item I-6). Full turns a field is held before the opponent may sample
# it. 0 transmits live, which peaks on the emitter's own cell.
PHEROMONE_TRANSMIT_LAG: Final[int] = 1

# The two registered scent-model *forms*. Appendix F fixes the three numbers
# above as PERMANENT; what a registration selects is the shape of the update,
# never the values. The book's ch4 prose gives multiplicative decay over its
# printed figure-4 kernel; the course's reference implementation gives
# subtractive decay over a linear Chebyshev falloff. Both are legal, they are
# visibly different physics, and a pairing locks one of them explicitly.
SCENT_MULTIPLICATIVE: Final[str] = "multiplicative_book_v1"
SCENT_SUBTRACTIVE: Final[str] = "subtractive_chebyshev_v1"

# --- Appendix F, Table 17: scoring (ALL PERMANENT) -------------------------
CAPTURE_COP: Final[int] = 20
CAPTURE_THIEF: Final[int] = 5
SURVIVAL_COP: Final[int] = 5
SURVIVAL_THIEF: Final[int] = 10
TIE_SCORE: Final[int] = 2
TECHNICAL_LOSS: Final[int] = 0

# --- Appendix F, Table 18: network and league ------------------------------
NUM_SUB_GAMES: Final[int] = 6  # permanent: sub-games in a series
DIVERSITY_REWARD: Final[int] = 10  # permanent
MIN_GAMES_TO_PASS: Final[int] = 2  # permanent
MAX_GAMES_PER_TEAM: Final[int] = 10  # permanent
TOKEN_BUDGET_PER_SERIES: Final[int] = 200_000  # negotiable

# --- Appendix F, Table 19: rate limiter / gatekeeper -----------------------
REQUESTS_PER_MINUTE: Final[int] = 30  # minimum
CONCURRENT_REQUESTS: Final[int] = 2  # minimum
RETRY_BACKOFF_SEC: Final[int] = 5  # minimum
MAX_RETRIES: Final[int] = 3  # minimum
QUEUE_DEPTH: Final[int] = 100  # minimum
RESPONSE_TIMEOUT_SEC: Final[int] = 30  # negotiable
WATCHDOG_TIMEOUT_SEC: Final[int] = 60  # negotiable

# --- Appendix F, Table 20: fixed addresses (reference table, NOT negotiable)
LECTURER_EMAIL: Final[str] = "rmisegal@gmail.com"
AGENT_REPORT_EMAIL: Final[str] = "rmisegal+uoh26finalgame@gmail.com"
REFERENCE_REPO: Final[str] = "https://github.com/rmisegal/Game-P2P-Cop-Chase"

# --- Roles -----------------------------------------------------------------
ROLE_COP: Final[str] = "police"
ROLE_THIEF: Final[str] = "thief"

# The side this repository ships as. The engine is symmetric -- both roles are
# fully implemented here and either can be selected with ``--role`` -- so this
# constant is the *only* thing that differs between the two submitted
# repositories, `best2934-cop` and `best2934-thief`, besides their READMEs.
# Rule 41 asks for one repository per role; it does not ask for two codebases,
# and two codebases would be two places for a bug to live.
DEFAULT_ROLE: Final[str] = ROLE_COP

# --- Outcomes --------------------------------------------------------------
OUTCOME_CAPTURE: Final[str] = "capture"
OUTCOME_SURVIVAL: Final[str] = "survival"
OUTCOME_TECHNICAL_LOSS: Final[str] = "technical_loss"

# --- Intent flag (book ch5: committed BEFORE the hint is revealed) ---------
INTENT_TRUTH: Final[str] = "truth"
INTENT_LIE: Final[str] = "lie"
