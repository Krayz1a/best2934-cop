"""The four talk providers (book ch6.5, Appendix F Table 21).

Chosen privately per peer under ``trash_talk.provider`` -- the opponent neither
knows nor cares which we use, because all four produce the same thing: one
sentence of at most fifteen words.

  template    zero tokens, offline, no account.  DEFAULT.
  ollama      local model on localhost:11434.    zero API tokens.
  claude_api  small cloud model via the API.     real, metered consumption.
  claude_cli  ``claude -p`` through Claude Code. highest cost.

In ``template`` and ``ollama`` the entire six-sub-game series costs zero tokens
and the competition reduces to the quality of the movement algorithm -- which is
exactly where the book says the grade lives.

None of these ever decides a move (rule 25).
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess

from .talk_prompt import TalkRequest, build_prompt, clamp_words, system_prompt

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
    """Pre-written sentence bank. Zero tokens, no account, always available.

    This is the default because the book requires the match to be fully
    playable with no language model at all -- and because it is the only
    provider that cannot fail, which makes it the natural fallback for the
    other three.
    """

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


class OllamaProvider:
    """Local model served by Ollama. No API cost, no rate limit, no account."""

    name = "ollama"

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434",
                 timeout: float = 10.0, num_predict: int = 60) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.num_predict = num_predict

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        import httpx

        response = httpx.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": build_prompt(request),
                "stream": False,
                "options": {"num_predict": self.num_predict},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        text = str(response.json().get("response", "")).strip()
        # Ollama runs locally, so nothing is billed: we report 0 against the
        # agreed token budget while still recording that the model ran.
        return clamp_words(text, request.max_words), 0


class ClaudeApiProvider:
    """Small cloud model through the Anthropic API.

    The book specifies a small model here and that is the right call: the whole
    job is one sentence of at most fifteen words, so Haiku is both the cheapest
    option and an entirely sufficient one. Consumption is real and counts
    against the agreed token budget, reported per sub-game (rule 54).
    """

    name = "claude_api"

    def __init__(self, model: str = "claude-haiku-4-5", timeout: float = 30.0,
                 max_tokens: int = 128) -> None:
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            # Resolves ANTHROPIC_API_KEY from the environment. Never hard-code
            # a key, and never read one from a config file (rule 39).
            self._client = anthropic.Anthropic(timeout=self.timeout)
        return self._client

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        message = self._get_client().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt(request),
            messages=[{"role": "user", "content": build_prompt(request)}],
        )
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        tokens = message.usage.input_tokens + message.usage.output_tokens
        return clamp_words(text, request.max_words), tokens


class ClaudeCliProvider:
    """``claude -p`` via the Claude Code CLI. Highest cost of the four modes."""

    name = "claude_cli"

    def __init__(self, timeout: float = 45.0) -> None:
        self.timeout = timeout

    def compose(self, request: TalkRequest) -> tuple[str, int]:
        binary = shutil.which("claude")
        if binary is None:
            raise RuntimeError("claude CLI not found on PATH")
        prompt = f"{system_prompt(request)}\n\n{build_prompt(request)}"
        completed = subprocess.run(
            [binary, "-p", prompt], capture_output=True, text=True,
            timeout=self.timeout, check=True,
        )
        # The CLI does not report token usage, so the consumption we declare is
        # an honest estimate rather than a measurement -- flagged as such in the
        # research report so the fairness normalisation is not misled.
        text = completed.stdout.strip()
        estimate = max(1, (len(prompt) + len(text)) // 4)
        return clamp_words(text, request.max_words), estimate


def env_has_anthropic_credentials() -> bool:
    """Warn early instead of failing mid-match when the API mode has no key."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return os.path.isdir(os.path.expanduser("~/.config/anthropic"))
