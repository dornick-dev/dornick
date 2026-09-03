"""Model providers.

The harness sees a single contract (`Backend`); which model is speaking is
a matter of configuration. The same mind and the same session log can be
carried on with Opus today and a local model tomorrow.
"""

from __future__ import annotations

from ..config import ModelConfig
from .base import (
    Backend,
    Callbacks,
    Interrupted,
    SimpleMessage,
    SimpleUsage,
    TurnResult,
    cancellable,
)

__all__ = [
    "Backend",
    "Callbacks",
    "Interrupted",
    "SimpleMessage",
    "SimpleUsage",
    "TurnResult",
    "build_client",
    "cancellable",
]

PROVIDERS = ("anthropic", "openai")


def build_client(model: ModelConfig) -> Backend:
    """Builds a client according to the configuration.

    If a fallback model is defined, the primary client goes inside a
    wrapper: when the primary model goes permanently silent (credits
    exhausted, credentials invalid) the turn continues with the fallback
    instead of dying. The loop sees no difference — what it sees is still
    a single `Backend`.
    """
    if (model.fallback_model or "").strip() and model.fallback_model != model.name:
        from .fallback import FallbackBackend

        return FallbackBackend(model, _plain_client)

    return _plain_client(model)


def _plain_client(model: ModelConfig) -> Backend:
    if model.provider == "anthropic":
        from .anthropic_backend import AnthropicBackend

        return AnthropicBackend(model)

    if model.provider == "openai":
        from .openai_backend import OpenAIBackend

        return OpenAIBackend(model)

    raise ValueError(
        f"Bilinmeyen sağlayıcı: {model.provider}. Geçerli olanlar: {', '.join(PROVIDERS)}"
    )
