"""Facade for the verbal layer -- one import for every talk-related symbol.

The implementation is split across four focused modules (word limits and the
prompt contract, the four providers, the cost/safety engine, and the landmark
vocabulary). This module re-exports them so callers write one import and stay
insulated from the internal layout, which is free to change.
"""

from __future__ import annotations

from .landmarks import HEADINGS, LANDMARKS, heading_word, pick_landmark
from .providers import (
    ClaudeApiProvider,
    ClaudeCliProvider,
    OllamaProvider,
    TemplateProvider,
    env_has_anthropic_credentials,
)
from .talk_engine import PROVIDERS, TalkEngine, build_talk_engine
from .talk_prompt import (
    FALLBACK_HINT,
    TalkProvider,
    TalkRequest,
    build_prompt,
    clamp_words,
    system_prompt,
)

__all__ = [
    "FALLBACK_HINT",
    "HEADINGS",
    "LANDMARKS",
    "PROVIDERS",
    "ClaudeApiProvider",
    "ClaudeCliProvider",
    "OllamaProvider",
    "TalkEngine",
    "TalkProvider",
    "TalkRequest",
    "TemplateProvider",
    "build_prompt",
    "build_talk_engine",
    "clamp_words",
    "env_has_anthropic_credentials",
    "heading_word",
    "pick_landmark",
    "system_prompt",
]
