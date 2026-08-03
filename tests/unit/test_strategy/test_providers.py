"""The four talk providers (Appendix F Table 21).

Three of the four reach outside the process -- to a local Ollama server, to the
Anthropic API, to the ``claude`` binary. None of them may do so here
(guidelines §6.1 rule 7), so each is driven against a stub standing in for its
dependency. What is being tested is our side of the contract: the word limit is
enforced, the token count is reported honestly, and no provider is ever allowed
to decide a move (rule 25).
"""

from __future__ import annotations

import subprocess
import sys
import types

import pytest

from p2pchase.strategy.providers import (
    ClaudeApiProvider,
    ClaudeCliProvider,
    OllamaProvider,
    TemplateProvider,
    env_has_anthropic_credentials,
)
from p2pchase.strategy.talk_prompt import TalkRequest


@pytest.fixture
def request_() -> TalkRequest:
    return TalkRequest(role="thief", step=4, intent="truth", heading="north",
                       landmark="Harlem", max_words=15, steps_remaining=20)


# --------------------------------------------------------------- template
def test_the_template_provider_costs_nothing_and_always_answers(request_):
    """It is the default and the fallback, so it must not be able to fail."""
    text, tokens = TemplateProvider(seed=1).compose(request_)
    assert tokens == 0
    assert text and len(text.split()) <= request_.max_words


def test_the_template_provider_is_reproducible_from_its_seed(request_):
    """Replays have to produce the same sentences as the match did."""
    assert TemplateProvider(seed=9).compose(request_) == \
           TemplateProvider(seed=9).compose(request_)


def test_the_cop_and_the_thief_draw_from_different_banks(request_):
    cop = TemplateProvider(seed=2).compose(
        TalkRequest(**{**vars(request_), "role": "police"}))[0]
    thief = TemplateProvider(seed=2).compose(request_)[0]
    assert cop != thief


def test_a_lie_and_a_truth_read_differently(request_):
    lying = TalkRequest(**{**vars(request_), "intent": "lie"})
    assert TemplateProvider(seed=4).compose(lying)[0] != \
           TemplateProvider(seed=4).compose(request_)[0]


# ----------------------------------------------------------------- ollama
def test_ollama_runs_locally_and_is_therefore_billed_as_zero(monkeypatch, request_):
    """It consumes compute, not budget -- reporting otherwise would be dishonest."""
    calls = {}

    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"response": "  Running north past Harlem, still ahead of you.  "}

    def _post(url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs["json"]
        return _Response()

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(post=_post))
    text, tokens = OllamaProvider(model="llama3.2").compose(request_)

    assert tokens == 0
    assert text == "Running north past Harlem, still ahead of you."
    assert calls["url"] == "http://localhost:11434/api/generate"
    assert calls["json"]["stream"] is False


def test_a_long_local_answer_is_clipped_to_the_agreed_limit(monkeypatch, request_):
    """A model that ignores the instruction must not put us in breach of it."""
    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"response": " ".join(["word"] * 60)}

    monkeypatch.setitem(sys.modules, "httpx",
                        types.SimpleNamespace(post=lambda url, **kw: _Response()))
    text, _ = OllamaProvider().compose(request_)
    assert len(text.split()) <= request_.max_words


# ------------------------------------------------------------- claude api
def test_the_api_provider_reports_the_tokens_it_actually_spent(request_):
    """Rule 54: consumption is declared per sub-game, so it must be measured."""
    provider = ClaudeApiProvider()
    provider._client = types.SimpleNamespace(messages=types.SimpleNamespace(
        create=lambda **kwargs: types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="North, past Harlem.")],
            usage=types.SimpleNamespace(input_tokens=40, output_tokens=11),
        )
    ))
    text, tokens = provider.compose(request_)
    assert text == "North, past Harlem."
    assert tokens == 51


def test_the_api_provider_asks_for_a_small_model_by_default():
    """One fifteen-word sentence does not justify a large model."""
    assert "haiku" in ClaudeApiProvider().model


# ------------------------------------------------------------- claude cli
def test_the_cli_provider_declares_its_token_use_as_an_estimate(monkeypatch, request_):
    """The CLI reports no usage, so we estimate -- and say so, rather than
    claiming a measurement we do not have."""
    monkeypatch.setattr("p2pchase.strategy.providers.shutil.which", lambda _n: "/bin/claude")
    monkeypatch.setattr(
        "p2pchase.strategy.providers.subprocess.run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout="Going north.\n", stderr=""),
    )
    text, tokens = ClaudeCliProvider().compose(request_)
    assert text == "Going north."
    assert tokens > 0


def test_a_missing_cli_says_so_plainly(monkeypatch, request_):
    monkeypatch.setattr("p2pchase.strategy.providers.shutil.which", lambda _n: None)
    with pytest.raises(RuntimeError, match="claude CLI not found"):
        ClaudeCliProvider().compose(request_)


# ------------------------------------------------------------ credentials
def test_missing_api_credentials_are_detectable_before_the_match(monkeypatch, tmp_path):
    """Finding out mid-match is a forfeit; finding out at startup is a warning."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("p2pchase.strategy.providers.os.path.isdir", lambda _p: False)
    assert env_has_anthropic_credentials() is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-a-real-key")
    assert env_has_anthropic_credentials() is True
