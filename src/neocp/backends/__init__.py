"""Model sağlayıcıları.

Harness tek bir sözleşme görür (`Backend`); hangi modelin konuştuğu
yapılandırma meselesidir. Aynı zihin ve aynı oturum günlüğü, bugün Opus'la
yarın yerel bir modelle sürdürülebilir.
"""

from __future__ import annotations

from ..config import ModelConfig
from .base import Backend, Callbacks, SimpleMessage, SimpleUsage, TurnResult

__all__ = [
    "Backend",
    "Callbacks",
    "SimpleMessage",
    "SimpleUsage",
    "TurnResult",
    "build_client",
]

PROVIDERS = ("anthropic", "openai")


def build_client(model: ModelConfig) -> Backend:
    if model.provider == "anthropic":
        from .anthropic_backend import AnthropicBackend

        return AnthropicBackend(model)

    if model.provider == "openai":
        from .openai_backend import OpenAIBackend

        return OpenAIBackend(model)

    raise ValueError(
        f"Bilinmeyen sağlayıcı: {model.provider}. Geçerli olanlar: {', '.join(PROVIDERS)}"
    )
