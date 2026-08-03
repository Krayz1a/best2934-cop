"""Providers for the verbal layer of the game (book ch6.5, Appendix F Table 21).

Four modes, chosen privately per peer in ``config/<role>/game.toml`` under
``[trash_talk] provider``. All four concern ONLY the deception text. The move
itself is always decided by pure Python (rule 25) -- a language model never
picks a move here, because a hallucinated illegal move is a technical loss.

  template    zero tokens, offline, no account.  DEFAULT.
  ollama      local model on localhost:11434.    zero API tokens.
  claude_api  small cloud model via the API.     real, metered consumption.
  claude_cli  `claude -p` through Claude Code.   highest cost.

``every_n_steps`` runs the model only once every N turns, cutting spend further.
In ``template`` and ``ollama`` the entire six-sub-game series costs zero tokens
and the competition reduces to the quality of the movement algorithm -- which
is exactly where the book says the grade lives.

Every provider is wrapped so that a failure NEVER breaks the match: if the
model is unreachable, rate-limited or slow, we fall back to the template bank
and keep playing. Losing the taunt costs nothing; losing the sub-game to a
timeout is a technical loss for both sides (rule 6).
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

# The book's default arena. Real landmarks make the hints feel like language
# rather than coordinates, which is the point: the channel must be natural
# language (rule 26) and must never be a numeric position protocol (rule 27).
LANDMARKS: dict[str, list[str]] = {
    "New York": [
        "Times Square", "Central Park", "Brooklyn Bridge", "Wall Street",
        "Harlem", "the East River", "Chinatown", "the Bowery", "Queens",
        "the Bronx", "Coney Island", "Grand Central",
    ],
    "": [  # generic fallback when no arena is agreed
        "the north gate", "the old market", "the river", "the tower",
        "the alley", "the rooftops", "the docks", "the square",
    ],
}


@dataclass
class TalkRequest:
    """Everything a provider may see when composing a hint.

    Deliberately narrow: the provider gets our own local view and the intended
    honesty, never the opponent's true position (we do not have it) and never
    the authority to change the move.
    """

    role: str
    step: int
    intent: str  # "truth" | "lie"
    heading: str  # the direction we actually moved, in words
    landmark: str
    max_words: int
    steps_remaining: int


class TalkProvider(Protocol):
    name: str

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        """Return ``(hint, tokens_used)``."""


# --------------------------------------------------------------------------
# template -- the zero-token default
# --------------------------------------------------------------------------

_TRUTH_LINES = [
    "Heading {heading}, near {landmark}. Catch me if you can.",
    "Moving {heading} past {landmark}. Still breathing.",
    "{landmark} is behind me now, going {heading}.",
    "Honest one: {heading}, by {landmark}.",
]

_LIE_LINES = [
    "Doubling back {heading} toward {landmark}. Good luck.",
    "You will find nothing near {landmark}. I went {heading}.",
    "Resting by {landmark}. Not moving {heading} at all.",
    "Try {landmark}, I am done running {heading}.",
]

_COP_LINES = [
    "Sweeping {heading} from {landmark}. The net is closing.",
    "Sealing the way past {landmark}. Nowhere left to go {heading}.",
    "I know you passed {landmark}. Moving {heading}.",
]


class TemplateProvider:
    """Pre-written sentence bank. Zero tokens, no account, always available."""

    name = "template"

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        if request.role == "police":
            bank = _COP_LINES
        else:
            bank = _LIE_LINES if request.intent == "lie" else _TRUTH_LINES
        line = self._rng.choice(bank).format(
            heading=request.heading, landmark=request.landmark
        )
        return clamp_words(line, request.max_words), 0


# --------------------------------------------------------------------------
# ollama -- local model, zero API tokens
# --------------------------------------------------------------------------


class OllamaProvider:
    """Local model served by Ollama. No API cost, no rate limit, no account."""

    name = "ollama"

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434", timeout: float = 10.0) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        import httpx

        response = httpx.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": build_prompt(request),
                "stream": False,
                "options": {"num_predict": 60},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        text = str(body.get("response", "")).strip()
        # Ollama runs locally, so nothing is billed; report 0 against the
        # agreed token budget while still recording that the model ran.
        return clamp_words(text, request.max_words), 0


# --------------------------------------------------------------------------
# claude_api -- metered cloud model
# --------------------------------------------------------------------------


class ClaudeApiProvider:
    """Small cloud model through the Anthropic API.

    The book specifies a small model for this mode, and that is the right call:
    the entire job is one sentence of at most fifteen words, so Haiku is both
    the cheapest and an entirely sufficient choice. The model is configurable
    in ``[llm] model`` for teams who want to spend more.

    Consumption here is real and is counted against the agreed token budget,
    reported per sub-game in the result JSON (rule 54).
    """

    name = "claude_api"

    def __init__(self, model: str = "claude-haiku-4-5", timeout: float = 30.0) -> None:
        self.model = model
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            # Resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an
            # `ant auth login` profile. Never hard-code a key (rule 39).
            self._client = anthropic.Anthropic(timeout=self.timeout)
        return self._client

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        client = self._get_client()
        message = client.messages.create(
            model=self.model,
            max_tokens=128,
            system=system_prompt(request),
            messages=[{"role": "user", "content": build_prompt(request)}],
        )
        text = "".join(
            block.text for block in message.content if block.type == "text"
        ).strip()
        tokens = message.usage.input_tokens + message.usage.output_tokens
        return clamp_words(text, request.max_words), tokens


# --------------------------------------------------------------------------
# claude_cli -- through the Claude Code CLI
# --------------------------------------------------------------------------


class ClaudeCliProvider:
    """`claude -p` via the Claude Code CLI. Highest cost of the four modes."""

    name = "claude_cli"

    def __init__(self, timeout: float = 45.0) -> None:
        self.timeout = timeout

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        binary = shutil.which("claude")
        if binary is None:
            raise RuntimeError("claude CLI not found on PATH")
        prompt = f"{system_prompt(request)}\n\n{build_prompt(request)}"
        completed = subprocess.run(
            [binary, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=True,
        )
        # The CLI does not report token usage, so the consumption we declare is
        # an honest estimate rather than a measurement -- flagged as such in the
        # research report so the lecturer's fairness normalisation is not misled.
        text = completed.stdout.strip()
        estimate = max(1, (len(prompt) + len(text)) // 4)
        return clamp_words(text, request.max_words), estimate


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------


def system_prompt(request: TalkRequest) -> str:
    """The word limit is told to the model explicitly (Appendix F Table 14)."""
    honesty = (
        "This message must be MISLEADING but must never state a coordinate."
        if request.intent == "lie"
        else "This message must be TRUTHFUL about your direction."
    )
    return (
        f"You are the {request.role} in a pursuit game played on a hidden grid. "
        f"Write one taunt of at most {request.max_words} words in natural English. "
        f"{honesty} "
        "Never write numbers, grid coordinates, row/column indices or any direct "
        "position encoding -- speak only in landmarks and directions. "
        "Reply with the sentence and nothing else."
    )


def build_prompt(request: TalkRequest) -> str:
    return (
        f"You just moved {request.heading}, near {request.landmark}. "
        f"Step {request.step}, {request.steps_remaining} steps left. "
        "Write the taunt."
    )


def clamp_words(text: str, max_words: int) -> str:
    """Hard-enforce the agreed word limit, whatever the model returned.

    The limit is a negotiated term of the match, so it cannot be left to a
    model's cooperation -- we truncate locally before anything goes on the wire.
    """
    cleaned = " ".join(str(text).replace("\n", " ").split())
    if not cleaned:
        return "Still here."
    words = cleaned.split(" ")
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words])


@dataclass
class TalkEngine:
    """Provider wrapper adding the every-N-steps gate and a safe fallback."""

    provider: TalkProvider
    fallback: TalkProvider = field(default_factory=TemplateProvider)
    every_n_steps: int = 1
    tokens_used: int = 0
    failures: int = 0

    def compose(self, request: TalkRequest) -> str:
        if self.every_n_steps > 1 and request.step % self.every_n_steps != 0:
            hint, _ = self.fallback.compose(request)
            return hint
        try:
            hint, tokens = self.provider.compose(request)
            self.tokens_used += tokens
            if hint:
                return hint
        except Exception:
            # A provider outage must never cost us the sub-game. Degrade to
            # the offline bank and carry on.
            self.failures += 1
        hint, _ = self.fallback.compose(request)
        return hint


def build_talk_engine(trash_talk: dict, llm: dict) -> TalkEngine:
    """Construct the configured provider, defaulting to the free template bank."""
    name = str(trash_talk.get("provider", "template")).strip().lower()
    every_n = int(trash_talk.get("every_n_steps", 1))

    provider: TalkProvider
    if name == "ollama":
        provider = OllamaProvider(
            model=str(llm.get("ollama_model", "llama3.2")),
            host=str(llm.get("ollama_host", "http://localhost:11434")),
            timeout=float(llm.get("step_deadline_seconds", 30)),
        )
    elif name == "claude_api":
        provider = ClaudeApiProvider(
            model=str(llm.get("model", "claude-haiku-4-5")),
            timeout=float(llm.get("step_deadline_seconds", 30)),
        )
    elif name == "claude_cli":
        provider = ClaudeCliProvider(timeout=float(llm.get("step_deadline_seconds", 45)))
    else:
        provider = TemplateProvider(seed=int(trash_talk.get("seed", 0)) or None)

    return TalkEngine(provider=provider, every_n_steps=max(1, every_n))


def pick_landmark(map_area: str, rng: random.Random) -> str:
    pool = LANDMARKS.get(map_area) or LANDMARKS[""]
    return rng.choice(pool)


def heading_word(move: str) -> str:
    return {
        "N": "north", "S": "south", "E": "east", "W": "west", "STAY": "nowhere",
    }.get(move, "somewhere")


def env_has_anthropic_credentials() -> bool:
    """Best-effort check so we can warn early instead of failing mid-match."""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.path.expanduser("~/.config/anthropic/") and os.path.isdir(os.path.expanduser("~/.config/anthropic"))
    )
