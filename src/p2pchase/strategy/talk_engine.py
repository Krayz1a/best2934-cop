"""The talk engine: cost control and the promise that talking never loses a game.

Two policies live here, and both exist because the verbal layer is worth far
less than the match it sits inside.

**Cost.** ``every_n_steps`` runs the real provider only once every N turns and
falls back to the free template bank in between. A six-sub-game series with
``every_n_steps = 3`` costs roughly a third of what running the model every turn
would, for a rhetorical layer nobody scores.

**Safety.** Every provider call is wrapped. If the model is unreachable,
rate-limited or slow, we swallow it and take the template line. Losing a taunt
costs nothing; letting a provider outage run us past the turn deadline is a
technical loss for both sides (rule 6). That is a trade with only one sane
answer, so it is made here rather than left to each call site.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .providers import (
    ClaudeApiProvider,
    ClaudeCliProvider,
    OllamaProvider,
    TemplateProvider,
)
from .talk_prompt import TalkProvider, TalkRequest, clamp_words, strip_positions

LOGGER = logging.getLogger(__name__)

#: Provider name -> factory. Adding a mode means adding one entry here
#: (guidelines §12.1: extension by registration, not by editing a branch).
PROVIDERS: dict[str, str] = {
    "template": "TemplateProvider",
    "ollama": "OllamaProvider",
    "claude_api": "ClaudeApiProvider",
    "claude_cli": "ClaudeCliProvider",
}


@dataclass
class TalkEngine:
    """Provider wrapper adding the every-N-steps gate and a safe fallback.

    Input:  a :class:`~p2pchase.strategy.talk_prompt.TalkRequest`.
    Output: a hint string -- always non-empty, always within the word limit.
    Setup:  ``provider`` (the configured mode), ``fallback`` (always the free
            bank), ``every_n_steps`` (cost gate).
    """

    provider: TalkProvider
    fallback: TalkProvider = field(default_factory=TemplateProvider)
    every_n_steps: int = 1
    tokens_used: int = 0
    failures: int = 0

    @property
    def degraded(self) -> bool:
        """True once the configured provider has failed at least once."""
        return self.failures > 0

    def compose(self, request: TalkRequest) -> str:
        """Compose one hint, never raising and never returning an empty string."""
        if self.every_n_steps > 1 and request.step % self.every_n_steps != 0:
            hint, _ = self.fallback.compose(request)
            return self._guard(hint, request)
        try:
            hint, tokens = self.provider.compose(request)
            self.tokens_used += tokens
            if hint:
                return self._guard(hint, request)
        except Exception as error:  # noqa: BLE001 -- degrading is the whole point
            self.failures += 1
            LOGGER.warning(
                "talk provider %s failed (%s: %s); falling back to the template bank",
                getattr(self.provider, "name", "?"), type(error).__name__, error,
            )
        hint, _ = self.fallback.compose(request)
        return self._guard(hint, request)

    def _guard(self, hint: str, request: TalkRequest) -> str:
        """Last checkpoint before the wire: no coordinates, no over-long sentence.

        Applied to every provider including the template bank. The bank is ours
        and is safe by construction, but a guard that trusts *some* of its
        inputs is a guard that stops being run.
        """
        safe = strip_positions(hint)
        if safe != hint:
            LOGGER.warning("stripped a position-like token from a hint (rule 27)")
        return clamp_words(safe, request.max_words)


def build_talk_engine(trash_talk: dict, llm: dict) -> TalkEngine:
    """Construct the configured provider, defaulting to the free template bank."""
    name = str(trash_talk.get("provider", "template")).strip().lower()
    every_n = max(1, int(trash_talk.get("every_n_steps", 1)))
    deadline = float(llm.get("step_deadline_seconds", 30))

    provider: TalkProvider
    if name == "ollama":
        provider = OllamaProvider(
            model=str(llm.get("ollama_model", "llama3.2")),
            host=str(llm.get("ollama_host", "http://localhost:11434")),
            timeout=deadline,
        )
    elif name == "claude_api":
        provider = ClaudeApiProvider(
            model=str(llm.get("model", "claude-haiku-4-5")),
            timeout=deadline,
            max_tokens=int(llm.get("max_tokens", 128)),
        )
    elif name == "claude_cli":
        provider = ClaudeCliProvider(timeout=float(llm.get("step_deadline_seconds", 45)))
    else:
        if name not in PROVIDERS:
            LOGGER.warning("unknown talk provider %r; using the template bank", name)
        provider = TemplateProvider(seed=int(trash_talk.get("seed", 0)) or None)

    return TalkEngine(provider=provider, every_n_steps=every_n)
