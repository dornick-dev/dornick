"""Fallback model: when the primary model goes permanently silent, the job must not die.

In the field the problem looks like this: a long job is running, credits
run out (402) or the model id in the settings becomes invalid. The
provider gives the same answer on every request, so waiting achieves
nothing; the loop keeps surfacing the error and a job hours in the making
is left half-done.

This wrapper steps in: if the primary model returns a PERMANENT error,
the same turn is tried once more with the fallback model. If it succeeds
the job continues and the user sees a single line in the chat. From that
moment on, turns continue with the fallback — retrying the primary on
every turn would double every turn into two requests, and if credits are
out it never recovers.

Why in the BACKEND layer: the loop (`loop.py`) does not know which model
is speaking, it only sees a `Backend`. Putting the switch here works
without touching the loop, the session log, or the UI — `build_client`
returns this instead of the primary client when a fallback is defined.

Boundary: TRANSIENT errors never come here. Dropped connections, 429 and
5xx are already on the loop's retry ladder (RETRY_DELAYS) and must stay
there — permanently switching to a weaker model on a provider hiccup
means a job whose quality silently degraded.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from ..config import ModelConfig
from .base import Backend, Callbacks, TurnResult

# States that count as permanent. The measure is a single question: if
# the SAME request were sent again shortly, would the result change? If
# not, switching to the fallback is right.
#
#   402  payment / credits — every request is the same until money lands
#   401  invalid key — the loop counts this as transient (the key can be
#        fixed later) and retries; we don't touch that
#   404  model missing / removed
#   400  usually an invalid model id or an unsupported field
#   403  no access (region, plan)
_PERMANENT_STATUS = ("400", "402", "403", "404", "405", "422")

# Providers that send no status code say the same thing in plain text.
_PERMANENT_TEXT = re.compile(
    r"is not a valid model|model_not_found|modeli bulunamadı|"
    r"insufficient|credit|quota|billing|payment required|"
    r"unsupported_country|not permitted",
    re.I,
)


def is_permanent(error: str | None) -> bool:
    """Is this an error where retrying would not change the outcome?

    We decide from the TEXT because the backends already turn the error
    into a readable sentence (`_explain`) and the original exception
    object is gone by that point.
    """
    text = (error or "").strip()
    if not text:
        return False
    if re.search(r"\b(" + "|".join(_PERMANENT_STATUS) + r")\b", text):
        return True
    return bool(_PERMANENT_TEXT.search(text))


class FallbackBackend:
    """Wraps the primary backend; switches to the fallback on a permanent error and stays there."""

    def __init__(self, model: ModelConfig, build: Any) -> None:
        self._build = build
        self._model = model
        self._primary: Backend | None = build(model)
        self._fallback: Backend | None = None
        # Has the switch happened: if so, the primary model is never tried again.
        self.switched = False

    # -- helpers -------------------------------------------------------

    @property
    def fallback_name(self) -> str:
        return (self._model.fallback_model or "").strip()

    def _fallback_client(self) -> Backend:
        """The fallback client is built when first needed.

        The provider and address stay the same, only the model name
        changes: fallback means "another model at the same door". Falling
        to a different provider is the settings' job — doing it silently
        here would make it invisible which key is being spoken with.
        """
        if self._fallback is None:
            self._fallback = self._build(
                replace(self._model, name=self.fallback_name, fallback_model="")
            )
        return self._fallback

    # -- the Backend contract ------------------------------------------

    async def turn(
        self,
        prepared: Any,
        tools: list[dict[str, Any]],
        *,
        cancel: Any,
        callbacks: Callbacks | None = None,
    ) -> TurnResult:
        if self.switched:
            return await self._fallback_client().turn(
                prepared, tools, cancel=cancel, callbacks=callbacks)

        assert self._primary is not None
        result = await self._primary.turn(
            prepared, tools, cancel=cancel, callbacks=callbacks)

        # A cancel is a decision, not an error: switching to the fallback would be wrong.
        if result.interrupted or not is_permanent(result.error):
            return result

        self.switched = True
        # A one-line notice. `on_text` is the display channel: the line
        # shows in the chat but does not enter the answer's content or the
        # session log — writing a sentence the model never said into the
        # history would be mistaken for the model's own words on later turns.
        if callbacks is not None:
            callbacks.on_text(
                f"\n_Asıl model yanıt vermedi — yedek modelle sürüyorum "
                f"({self.fallback_name})._\n\n"
            )

        return await self._fallback_client().turn(
            prepared, tools, cancel=cancel, callbacks=callbacks)

    async def count_tokens(self, prepared: Any, tools: list[dict[str, Any]]) -> int:
        client = self._fallback_client() if self.switched else self._primary
        assert client is not None
        return await client.count_tokens(prepared, tools)

    async def close(self) -> None:
        for client in (self._primary, self._fallback):
            if client is not None:
                await client.close()
