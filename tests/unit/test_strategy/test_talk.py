"""The verbal layer: word limits, cost control, and never losing to an outage."""

from __future__ import annotations

import random

import pytest

from p2pchase.strategy.landmarks import LANDMARKS, heading_word, pick_landmark
from p2pchase.strategy.providers import TemplateProvider
from p2pchase.strategy.talk_engine import TalkEngine, build_talk_engine
from p2pchase.strategy.talk_prompt import (
    FALLBACK_HINT,
    TalkRequest,
    build_prompt,
    clamp_words,
    system_prompt,
)


def request(**overrides) -> TalkRequest:
    fields = {"role": "thief", "step": 1, "intent": "truth", "heading": "north",
              "landmark": "Harlem", "max_words": 15, "steps_remaining": 30}
    fields.update(overrides)
    return TalkRequest(**fields)


class ExplodingProvider:
    name = "exploding"

    def compose(self, request):
        raise RuntimeError("provider is down")


class CountingProvider:
    name = "counting"

    def __init__(self):
        self.calls = 0

    def compose(self, request):
        self.calls += 1
        return "a real sentence", 7


def test_the_word_limit_is_enforced_locally():
    """A negotiated term cannot be left to a model's cooperation."""
    assert len(clamp_words(" ".join(["word"] * 50), 15).split()) == 15


def test_a_short_sentence_is_left_alone():
    assert clamp_words("short one", 15) == "short one"


def test_whitespace_and_newlines_are_normalised():
    assert clamp_words("a\n b  c", 15) == "a b c"


def test_an_empty_response_becomes_a_usable_hint():
    assert clamp_words("", 15) == FALLBACK_HINT
    assert clamp_words("   \n ", 15) == FALLBACK_HINT


def test_the_system_prompt_states_the_limit_and_bans_coordinates():
    text = system_prompt(request(max_words=12))
    assert "12 words" in text
    assert "Never write numbers" in text
    assert "TRUTHFUL" in text


def test_the_system_prompt_switches_on_intent():
    assert "MISLEADING" in system_prompt(request(intent="lie"))


def test_the_user_prompt_carries_the_turn_context():
    text = build_prompt(request(step=9, steps_remaining=4))
    assert "Step 9" in text and "4 steps left" in text


def test_the_template_bank_costs_nothing_and_respects_the_limit():
    hint, tokens = TemplateProvider(seed=1).compose(request(max_words=6))
    assert tokens == 0
    assert len(hint.split()) <= 6


def test_the_template_bank_differs_by_role_and_intent():
    provider = TemplateProvider(seed=1)
    cop, _ = provider.compose(request(role="police"))
    assert "closing" in cop or "Sealing" in cop or "know you passed" in cop


def test_the_template_bank_is_reproducible():
    a, _ = TemplateProvider(seed=42).compose(request())
    b, _ = TemplateProvider(seed=42).compose(request())
    assert a == b


def test_a_provider_outage_never_costs_the_sub_game():
    """Losing a taunt costs nothing; a timeout is a technical loss for both."""
    engine = TalkEngine(provider=ExplodingProvider())
    hint = engine.compose(request())
    assert hint
    assert engine.failures == 1
    assert engine.degraded


def test_token_use_is_accumulated():
    engine = TalkEngine(provider=CountingProvider())
    engine.compose(request(step=1))
    engine.compose(request(step=2))
    assert engine.tokens_used == 14


def test_the_cost_gate_skips_the_real_provider_between_turns():
    provider = CountingProvider()
    engine = TalkEngine(provider=provider, every_n_steps=3)
    for step in range(1, 10):
        engine.compose(request(step=step))
    assert provider.calls == 3  # steps 3, 6 and 9 only


def test_the_default_engine_is_the_free_bank():
    engine = build_talk_engine({}, {})
    assert engine.provider.name == "template"
    assert engine.every_n_steps == 1


def test_an_unknown_provider_degrades_to_the_free_bank():
    assert build_talk_engine({"provider": "gpt-9000"}, {}).provider.name == "template"


@pytest.mark.parametrize("name", ["ollama", "claude_api", "claude_cli"])
def test_each_configured_provider_is_constructible(name):
    engine = build_talk_engine({"provider": name}, {"model": "claude-haiku-4-5"})
    assert engine.provider.name == name


def test_landmarks_come_from_the_agreed_arena():
    rng = random.Random(0)
    assert pick_landmark("New York", rng) in LANDMARKS["New York"]
    assert pick_landmark("", rng) in LANDMARKS[""]
    assert pick_landmark("Atlantis", rng) in LANDMARKS[""]


def test_a_move_renders_as_a_compass_word_never_an_axis_delta():
    assert heading_word("N") == "north"
    assert heading_word("STAY") == "nowhere"
    assert heading_word("?") == "somewhere"


def test_a_hint_naming_a_square_is_stripped_before_the_wire():
    """Rule 27: the prompt asks a model not to name coordinates; this enforces it."""
    from p2pchase.strategy.talk_prompt import strip_positions

    assert strip_positions("heading to 3,4 now") == "heading to now"
    assert strip_positions("watch row 2 column 5") == "watch"
    assert strip_positions("drifting north past the well") == "drifting north past the well"


def test_the_engine_guards_every_provider_including_our_own():
    """A guard that trusts some of its inputs is a guard that stops being run."""
    from p2pchase.strategy.talk_engine import TalkEngine
    from p2pchase.strategy.talk_prompt import TalkRequest

    class LeakyProvider:
        name = "leaky"

        def compose(self, request):
            return "I am at cell 4,4 and closing", 7

    engine = TalkEngine(provider=LeakyProvider())
    request = TalkRequest(role="police", step=1, intent="truth", heading="north",
                          landmark="the well", max_words=15, steps_remaining=30)
    hint = engine.compose(request)
    assert not any(char.isdigit() for char in hint)
    assert "cell" not in hint
    assert hint  # never empty -- a stripped hint still has to be sendable
