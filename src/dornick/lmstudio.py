"""LM Studio's own API.

The OpenAI-compatible endpoint is enough to *use* the model but not to
*manage* it, and not being able to manage it led to two concrete problems:

**Loading with the wrong window.** When LM Studio loads on its own it uses
4096 tokens — even if the model supports 262144. The system prompt plus the
tool schemas already exceed that and the server drops the head of the
prompt; the model forgets who it is and what was asked. `/api/v1/models/load`
takes `context_length`, so we can load the model **with the window from the
settings**.

**The duplicated model.** When a second request reaches a busy model LM
Studio loads a second copy: `qwen3.5-9b`, `:2`, `:3`. Three copies of a
6.5 GB model is 20 GB. Copies can be seen and removed here.

The model list also says what the model can do — whether it accepts images,
whether it was trained for tool use. The settings page shows this: there is
no point turning the camera on for a model that does not accept images.

This file is LM Studio specific. On another server the endpoints do not
exist and every call returns empty silently — the feature disappears, the
program keeps running.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

# The list endpoint is fast; loading is slow (the model goes from disk to memory).
LIST_TIMEOUT = 3.0
LOAD_TIMEOUT = 180.0

# LM Studio uses this when it loads on its own. Not a threshold, an
# observation: on meeting this value the right reading is "loaded on its
# own", not "the user asked for this".
JIT_CONTEXT = 4096


@dataclass(slots=True)
class Instance:
    """A loaded copy of a model."""

    id: str
    context: int


@dataclass(slots=True)
class Model:
    key: str
    name: str
    max_context: int
    vision: bool
    tools: bool
    instances: list[Instance]
    size_bytes: int = 0
    params_b: float = 0.0
    # If present in the catalogue `capabilities`; otherwise None — not made up.
    thinking: bool | None = None

    @property
    def loaded(self) -> bool:
        return bool(self.instances)


def root_of(base_url: str | None) -> str:
    """`http://localhost:1234/v1` → `http://localhost:1234`"""
    text = (base_url or "").rstrip("/")
    return text[: -len("/v1")] if text.endswith("/v1") else text


def models(base_url: str | None) -> list[Model]:
    """Models on the server. Empty list if it is not LM Studio."""
    payload = _get(base_url, "/api/v1/models")
    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []

    out: list[Model] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "llm":
            continue
        skills = entry.get("capabilities") or {}
        thinking = None
        if isinstance(skills, dict):
            for key in ("reasoning", "think", "thinking"):
                if key in skills:
                    thinking = bool(skills[key])
                    break
        out.append(
            Model(
                key=str(entry.get("key") or ""),
                name=str(entry.get("display_name") or entry.get("key") or ""),
                max_context=int(entry.get("max_context_length") or 0),
                vision=bool(skills.get("vision")) if isinstance(skills, dict) else False,
                tools=bool(skills.get("trained_for_tool_use")) if isinstance(skills, dict) else False,
                size_bytes=int(entry.get("size_bytes") or 0),
                params_b=_params_b(entry.get("params_string")),
                thinking=thinking,
                instances=[
                    Instance(
                        id=str(item.get("id") or ""),
                        context=int((item.get("config") or {}).get("context_length") or 0),
                    )
                    for item in (entry.get("loaded_instances") or [])
                    if isinstance(item, dict)
                ],
            )
        )
    return out


def find(base_url: str | None, key: str) -> Model | None:
    return next((m for m in models(base_url) if m.key == key), None)


def ensure_loaded(base_url: str | None, key: str, context: int, ttl: int = 0) -> dict[str, Any]:
    """Gets the model loaded with the wanted window.

    `ttl` > 0: unload the model after this many idle seconds (LM Studio
    `ttl` field). Left at 0, LM Studio uses its own default — which was
    unloading JIT models quickly and dropping the next request with "Model
    unloaded". The caller (desktop) gives a generous value for the local
    model so the model does not vanish mid-conversation.

    The returned dict says what was done; the UI shows this to the user:

        ok       was already loaded with the right window, untouched
        loaded   loaded
        capped   the wanted window exceeded the model's limit, pulled to the limit
        skipped  not LM Studio or unreachable

    Avoiding a reload matters: loading takes seconds and doing it on every
    start makes the program look heavy.
    """
    model = find(base_url, key)
    if model is None:
        return {"state": "skipped"}

    wanted = context
    capped = model.max_context and wanted > model.max_context
    if capped:
        wanted = model.max_context

    # If a copy already stands with a sufficient window, no reload. Larger
    # is accepted too: if the wanted one fits there is no problem.
    if any(inst.context >= wanted for inst in model.instances):
        return {"state": "ok", "context": wanted}

    payload: dict[str, Any] = {"model": key, "context_length": wanted}
    if ttl > 0:
        payload["ttl"] = ttl
    answer = _post(base_url, "/api/v1/models/load", payload)
    if answer.get("error") or not answer:
        return {"state": "skipped", "error": _error_of(answer)}

    return {
        "state": "capped" if capped else "loaded",
        "context": wanted,
        "instance": answer.get("instance_id", ""),
        "seconds": answer.get("load_time_seconds", 0),
    }


def unload(base_url: str | None, instance_id: str) -> bool:
    answer = _post(base_url, "/api/v1/models/unload", {"instance_id": instance_id})
    return not answer.get("error") if answer else False


def drop_duplicates(base_url: str | None, key: str) -> list[str]:
    """Removes the extra copies of the same model; returns the removed ones.

    The copy with the widest window stays — prompts go to it anyway, and
    keeping the narrow one would perpetuate the original problem.
    """
    model = find(base_url, key)
    if model is None or len(model.instances) < 2:
        return []

    keep = max(model.instances, key=lambda i: i.context)
    dropped = [i.id for i in model.instances if i.id != keep.id and unload(base_url, i.id)]
    return dropped


def unload_others(base_url: str | None, keep_key: str) -> list[str]:
    """Unloads ALL loaded copies other than the selected model.

    So two different models do not stay in VRAM at once — `_prepare_model`
    calls this when local optimization is on.
    """
    dropped: list[str] = []
    for model in models(base_url):
        if model.key == keep_key:
            continue
        for inst in model.instances:
            if inst.id and unload(base_url, inst.id):
                dropped.append(inst.id)
    return dropped


def suggest_context(
    wanted: int,
    *,
    max_context: int = 0,
    size_bytes: int = 0,
    params_b: float = 0.0,
    free_vram_mb: int | None = None,
) -> int:
    """Lowers the wanted context so it fits the GPU / model size.

    Without a VRAM measurement only the model's `max_context` ceiling
    applies. With a measurement: weights + 15% margin + 512 MB reserve are
    subtracted; the remainder is given to the KV cache. Roughly ~0.06 MB ×
    parameter_B / 1k tokens (Q4 class).
    """
    ceiling = wanted if wanted > 0 else 8192
    if max_context and max_context > 0:
        ceiling = min(ceiling, max_context)
    if free_vram_mb is None or free_vram_mb <= 0 or size_bytes <= 0:
        return ceiling if ceiling > 0 else JIT_CONTEXT

    model_mb = size_bytes / (1024 * 1024)
    headroom = free_vram_mb - model_mb * 1.15 - 512.0
    if headroom < 256:
        # Barely room for the model: the JIT window — let the conversation start anyway.
        return min(ceiling, JIT_CONTEXT)

    # KV cache roughly: ~2.5 MB × B-parameters / 1k tokens (Q4, conservative).
    # The old 0.06×B estimate read VRAM far too optimistically.
    params = params_b if params_b > 0 else max(7.0, model_mb / 550.0)
    kv_mb_per_1k = max(16.0, 2.5 * params)
    from_vram = int(headroom / kv_mb_per_1k * 1000)
    fitted = min(ceiling, max(JIT_CONTEXT, from_vram))
    return _snap_context(fitted)


def is_local_url(base_url: str | None) -> bool:
    """localhost / 127.0.0.1 / ::1 — no optimization on cloud endpoints."""
    host = (base_url or "").lower()
    return any(
        token in host
        for token in ("localhost", "127.0.0.1", "[::1]", "0.0.0.0")
    )


def _snap_context(n: int) -> int:
    """Round the context down to known steps (LM Studio friendly)."""
    steps = (4096, 6144, 8192, 12288, 16384, 24576, 32768, 49152, 65536,
             98304, 131072, 196608, 262144)
    best = steps[0]
    for step in steps:
        if step <= n:
            best = step
        else:
            break
    return best


def _params_b(raw: Any) -> float:
    """'9.0B' / '70B' → float billion parameters."""
    text = str(raw or "").strip().upper().replace(",", ".")
    if not text:
        return 0.0
    if text.endswith("B"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return 0.0


# -- HTTP --------------------------------------------------------------


def _get(base_url: str | None, path: str) -> dict[str, Any]:
    return _request(base_url, path, None, LIST_TIMEOUT)


def _post(base_url: str | None, path: str, body: dict[str, Any]) -> dict[str, Any]:
    return _request(base_url, path, body, LOAD_TIMEOUT)


def _request(base_url: str | None, path: str, body: Any, timeout: float) -> dict[str, Any]:
    """Every error falls to an empty dict.

    On a server that is not LM Studio these endpoints do not exist, and that
    is normal: the feature disappears, the program keeps running.
    """
    root = root_of(base_url)
    if not root:
        return {}

    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        root + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # The error body is information too: if messages like "Missing
        # required field" are swallowed, what went wrong never shows.
        try:
            return json.load(exc)
        except Exception:
            return {"error": {"message": f"HTTP {exc.code}"}}
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {}


def _error_of(answer: dict[str, Any]) -> str:
    error = answer.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return str(error or "")
