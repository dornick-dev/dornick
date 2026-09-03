"""Reading and writing settings.

The UI's settings page is fed from here. Two files are written:

    .dornick/config.json   model, context, permissions — shareable
    .dornick/keys.json     API keys — not shareable

There is a single reason for the split: config.json can end up in a project
and fall into version control, and a key must not be written there.
keys.json stands apart and is never sent to the browser — the settings page
only sees "is there a key". An entered key goes to the server once and never
comes back.

Keys are loaded into the environment at startup: the backends already read
from there, no need to open a second path.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from . import listen as listen_module
from . import lmstudio
from . import organs, environment, sandbox, shell_assoc, startup
from . import voice as voice_module
from .config import (
    BrowserConfig,
    CameraConfig,
    Config,
    ContextConfig,
    ModelConfig,
    PermissionConfig,
    SandboxConfig,
)
from .listen import ListenConfig
from .place import PlaceConfig
from .voice import VoiceConfig

KEYS_FILE = "keys.json"
CONFIG_FILE = "config.json"

# What a key that has a value looks like when returned to the browser. Not
# the real value, only a "there is something here" marker.
MASK = "••••••••"


# The provider list lives in one place: both the settings page and
# `dornick setup` read it from here. The `env` field says which environment
# variable the key is written to; None ones are local servers, they do not
# want a key.
#
# Cloud presets are from the official OpenAI-compatible endpoints (2026): no
# random additions. Sources: ai.google.dev/gemini-api/docs/openai ·
# build.nvidia.com · api-docs.deepseek.com · console.groq.com/docs/openai ·
# docs.mistral.ai · help.aliyun.com/en/model-studio/base-url
PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "id": "anthropic",
        "label": "Claude",
        "provider": "anthropic",
        "base_url": None,
        "env": "ANTHROPIC_API_KEY",
        "hint": "console.anthropic.com üzerinden alınır",
    },
    {
        "id": "openai",
        "label": "ChatGPT",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "env": "OPENAI_API_KEY",
        "hint": "platform.openai.com üzerinden alınır",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "provider": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
        "hint": "tek anahtarla çok sağlayıcı",
    },
    {
        "id": "gemini",
        "label": "Gemini",
        "provider": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env": "GEMINI_API_KEY",
        "hint": "aistudio.google.com — OpenAI-uyumlu uç",
    },
    {
        "id": "nvidia",
        "label": "NVIDIA NIM",
        "provider": "openai",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "env": "NVIDIA_API_KEY",
        "hint": "build.nvidia.com/settings",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "provider": "openai",
        "base_url": "https://api.deepseek.com",
        "env": "DEEPSEEK_API_KEY",
        "hint": "platform.deepseek.com",
    },
    {
        "id": "groq",
        "label": "Groq",
        "provider": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "env": "GROQ_API_KEY",
        "hint": "console.groq.com",
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "provider": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "env": "MISTRAL_API_KEY",
        "hint": "console.mistral.ai",
    },
    {
        "id": "qwen",
        "label": "Qwen (DashScope)",
        "provider": "openai",
        # The shared DashScope domain is still valid; to move to the
        # workspace/region address in production edit the Model › Address field.
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "env": "DASHSCOPE_API_KEY",
        "hint": "Model Studio — bölgeye göre adresi değiştir",
    },
    {
        "id": "lmstudio",
        "label": "LM Studio",
        "provider": "openai",
        "base_url": "http://localhost:1234/v1",
        "env": None,
        "hint": "Developer sekmesinden sunucuyu başlat",
    },
    {
        "id": "vllm",
        "label": "vLLM",
        "provider": "openai",
        "base_url": "http://localhost:8000/v1",
        "env": None,
        "hint": "python -m vllm.entrypoints.openai.api_server",
    },
    {
        "id": "ollama",
        "label": "Ollama",
        "provider": "openai",
        "base_url": "http://localhost:11434/v1",
        "env": None,
        "hint": "ollama serve",
    },
)

# Mail account. The credentials sit in the same file as the API keys:
# config.json can end up in a project and fall into version control.
MAIL_FIELDS: tuple[dict[str, str], ...] = (
    {"env": "DORNICK_IMAP_HOST", "label": "IMAP sunucusu", "hint": "imap.gmail.com", "secret": "0"},
    {"env": "DORNICK_SMTP_HOST", "label": "SMTP sunucusu", "hint": "smtp.gmail.com", "secret": "0"},
    {"env": "DORNICK_MAIL_USER", "label": "adres", "hint": "ornek@gmail.com", "secret": "0"},
    {
        "env": "DORNICK_MAIL_PASSWORD",
        "label": "parola",
        "hint": "Gmail'de normal parola değil 'uygulama şifresi'",
        "secret": "1",
    },
)


PERMISSION_MODES: tuple[dict[str, str], ...] = (
    {"id": "auto", "label": "otomatik", "hint": "okuma serbest, yazma sorulur"},
    {"id": "ask", "label": "her seferinde sor", "hint": "en güvenlisi, en yavaşı"},
    {"id": "plan", "label": "salt okunur", "hint": "hiçbir şeyi değiştiremez"},
    {"id": "yolo", "label": "tam yetki", "hint": "hiçbir şey sorulmaz"},
)


# First-setup guidance: when no provider is usable and the user types (or
# speaks) the model is not called at all; this message lands in the chat.
# The text is translated to English in the UI with t() (app.js).
SETUP_REDIRECT = (
    "Henüz bir yapay zekâ sağlayıcısı tanımlı değil. Ayarlar › Model'den bir "
    "sağlayıcı seçip API anahtarı girmelisin. Varsayılan sağlayıcı "
    "OpenRouter'dır — anahtarını girdiğinde ücretsiz modellerle 'Oto' modda "
    "hemen başlayabilirsin."
)


def _gpu_snapshot() -> list[dict[str, Any]]:
    """VRAM summary for Settings › Machine. [] without nvidia-smi."""
    try:
        from . import gpu as gpu_module
        return [
            {
                "name": g.name,
                "total_mb": g.total_mb,
                "free_mb": g.free_mb,
                "used_mb": g.used_mb,
            }
            for g in gpu_module.nvidia_gpus()
        ]
    except Exception:
        return []


def provider_of(config: ModelConfig) -> str:
    """Which provider the model in settings corresponds to.

    Matching looks at the address, not the provider name: there are six
    different servers under "openai" and the settings page must show which
    one is selected.
    """
    for entry in PROVIDERS:
        if entry["provider"] != config.provider:
            continue
        if entry["base_url"] == (config.base_url or entry["base_url"]):
            return str(entry["id"])
    return "anthropic" if config.provider == "anthropic" else "openai"


def _required_env(model: ModelConfig) -> str | None:
    """The key variable this configuration needs to work.

    If the address corresponds to a known provider, that provider's key; if
    not (a custom/local endpoint) whatever the user wrote. None = no key needed.
    """
    entry = next((e for e in PROVIDERS if e["id"] == provider_of(model)), None)
    if entry is not None and entry["base_url"] == (model.base_url or entry["base_url"]):
        return entry["env"]
    return model.api_key_env


def unconfigured(model: ModelConfig) -> bool:
    """Is no provider in a usable state?

    Definition: the model name is empty OR a key-requiring provider has no
    key. Local servers (env=None) do not want a key — they count as
    configured by name. Keys are loaded into the environment at startup
    (export_keys), so the only place looked at is the environment.
    """
    if not (model.name or "").strip():
        return True
    env = _required_env(model)
    return bool(env) and not os.environ.get(env)


# -- reading -----------------------------------------------------------


def load_keys(state_dir: Path) -> dict[str, str]:
    path = state_dir / KEYS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: str(v) for k, v in data.items() if isinstance(v, str) and v}


def export_keys(state_dir: Path) -> int:
    """Loads the saved keys into the environment. Returns how many.

    If the environment already has a value it is not touched: the key the
    user gave in their shell must come before the one in the file.
    """
    loaded = 0
    for name, value in load_keys(state_dir).items():
        if not os.environ.get(name):
            os.environ[name] = value
            loaded += 1
    return loaded


def _sandbox_snapshot(config: Config) -> dict[str, Any]:
    """Workshop + project state, as the settings page draws it."""
    box = config.open_sandbox()
    chosen = config.sandbox.project.strip()
    # The path sitting in settings may have become invalid (folder deleted,
    # hand-edited): the sandbox drops it silently, the user sees the REASON here.
    block = sandbox.root_block(Path(chosen).expanduser()) if chosen else None
    return {
        **asdict(config.sandbox),
        # A relative name can sit in settings; what the user needs to see
        # is the resolved form.
        "root": str(box.root),
        "project_root": str(box.project) if box.project else "",
        "project_error": block or "",
        "project_note": box.note,
        "recent": sandbox.recent_projects(config.state_dir),
    }


def snapshot(config: Config) -> dict[str, Any]:
    """Everything the settings page draws. Key values never go in."""
    keys = load_keys(config.state_dir)
    return {
        "model": asdict(config.model),
        "context": asdict(config.context),
        "permissions": asdict(config.permissions),
        "sandbox": _sandbox_snapshot(config),
        "voice": {**asdict(config.voice), "available": voice_module.available()},
        # Location and autostart. Both ship off: one sends the user's
        # address to a third-party service, the other writes a record into startup.
        "place": asdict(config.place),
        # Does it really exist on the machine. Showing a non-existent device
        # as switchable means making the user click a button that does nothing.
        # Installed layout (via the wizard)? The UI picks the missing-feature
        # text by this: in the installed layout pip is not suggested, the wizard is.
        "installed": environment.is_installed(),
        # The field question "which version is installed?" had no answer:
        # the Machine tab shows it read-only, installed/dev distinction from installed.
        "surum": environment.version(),
        "hardware": {
            "microphone": organs.has_microphone(),
            "camera": organs.has_camera(),
            "gpu": _gpu_snapshot(),
        },
        "startup": {
            "available": startup.available(),
            "enabled": startup.enabled(),
            "command": startup.current() or startup.command(),
        },
        "shell_assoc": {
            "available": shell_assoc.available(),
            "enabled": shell_assoc.enabled(),
        },
        "camera": asdict(config.camera),
        "browser": asdict(config.browser),
        "mail": [
            {**entry, "filled": bool(keys.get(entry["env"]) or os.environ.get(entry["env"]))}
            for entry in MAIL_FIELDS
        ],
        "listen": {
            **asdict(config.listen),
            "available": listen_module.available(),
            "sizes": list(listen_module.SIZES),
        },
        "provider": provider_of(config.model),
        "providers": [
            {
                **entry,
                # A key coming from the environment counts as "present" too:
                # if the user gave it in their shell the settings page must
                # not say "missing".
                "has_key": bool(
                    entry["env"] and (keys.get(entry["env"]) or os.environ.get(entry["env"]))
                ),
                "from_env": bool(
                    entry["env"] and not keys.get(entry["env"]) and os.environ.get(entry["env"])
                ),
            }
            for entry in PROVIDERS
        ],
        "modes": list(PERMISSION_MODES),
        "workspace": str(config.workspace),
        "state_dir": str(config.state_dir),
    }


# -- window detection ---------------------------------------------------
#
# The symptom of a wrong context-window setting is insidious: compaction
# never triggers, the prompt exceeds the model's real limit and the server
# silently drops the **head** of the prompt. At that point the model has
# forgotten who it is and what was asked — from the outside it looks like
# it is "going haywire".
#
# The default 200_000 is Claude's window; on a local model it is mostly
# 8k–32k. If we can ask the server and learn, let's not guess.

PROBE_TIMEOUT = 2.0
# Cloud catalogues (NVIDIA, OpenRouter…) can be slower than local; 2 s was
# silently falling to an empty list — it looked like "the model won't load".
REMOTE_PROBE_TIMEOUT = 10.0

# The field names compatible servers report the window under. Not standard,
# every server uses its own name.
# Order matters: `loaded_context_length` is the window the model is
# **currently loaded with**, `max_context_length` the largest it supports.
# LM Studio can load a model with 4096 even though it supports 262144;
# writing the large one never triggers compaction and leads the server to
# drop the head of the prompt. The real one is the loaded one.
WINDOW_FIELDS = (
    "loaded_context_length",
    "context_length",
    "context_window",
    "n_ctx",
    "max_context_length",
    "max_model_len",
)


def _openai_models_payload(
    config: Config,
) -> tuple[dict[str, Any] | None, str | None]:
    """OpenAI-compatible `{base}/models`.

    Returns: (payload, error). Keyed endpoints want Bearer (Gemini…).
    The error is short Turkish — so the settings page shows the reason
    instead of 'no list'.
    """
    if config.model.provider != "openai" or not config.model.base_url:
        return None, None

    import urllib.error
    import urllib.request

    url = config.model.base_url.rstrip("/") + "/models"
    headers = {"User-Agent": "dornick"}
    env = config.model.api_key_env
    if env and (key := os.environ.get(env)):
        headers["Authorization"] = f"Bearer {key}"
    timeout = (
        PROBE_TIMEOUT
        if lmstudio.is_local_url(config.model.base_url)
        else REMOTE_PROBE_TIMEOUT
    )
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except TimeoutError:
        return None, "zaman aşımı"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return None, str(reason)[:80]
    if not isinstance(payload, dict):
        return None, "beklenmeyen yanıt"
    return payload, None


def detect_window(config: Config) -> int | None:
    """Asks the server for the model's real window size.

    Returns None if it cannot find it — making it up is worse than silently
    continuing with the wrong setting.
    """
    caps = detect_caps(config)
    window = caps.get("max_context")
    return int(window) if isinstance(window, int) and window > 0 else None


def detect_caps(config: Config) -> dict[str, Any]:
    """The selected model's capabilities from the catalogue. No unknown fields.

    The shape changes per provider: OpenRouter `context_length` +
    `architecture.input_modalities` + `supported_parameters`; LM Studio
    `max_context_length` + `capabilities`; Anthropic's list has no window,
    thinking/vision are assumed on Claude chat models; OpenAI's official
    list lacks these fields — they are not invented.
    """
    name = (config.model.name or "").strip()
    if not name or name.lower() == "oto":
        return {}
    caps: dict[str, Any] = {}
    for entry in scan_models(config):
        if entry.get("id") == name:
            caps = {
                key: entry[key]
                for key in ("max_context", "vision", "thinking", "tools")
                if key in entry
            }
            break
    # Ollama `/v1/models` only gives ids; window/capabilities are asked of
    # the selected model via `/api/show` — no N calls in the catalogue, only Detect.
    if any(key not in caps for key in ("max_context", "vision", "thinking")):
        for key, value in _ollama_show_caps(config, name).items():
            caps.setdefault(key, value)
    return caps


def _caps_of(entry: dict[str, Any]) -> dict[str, Any]:
    """Known capabilities from a single `/models` record. Missing fields are not added."""
    ident = str(entry.get("id") or entry.get("key") or "")
    out: dict[str, Any] = {"id": ident}
    shown = entry.get("name") or entry.get("display_name")
    if shown:
        out["name"] = str(shown)

    window = _window_of(entry)
    top = entry.get("top_provider")
    if window is None and isinstance(top, dict):
        window = _window_of(top)
    if window is not None:
        out["max_context"] = window

    arch = entry.get("architecture")
    if isinstance(arch, dict):
        modalities = arch.get("input_modalities")
        if isinstance(modalities, list):
            out["vision"] = any(str(m).lower() in ("image", "vision") for m in modalities)
        elif isinstance(arch.get("modality"), str):
            out["vision"] = "image" in arch["modality"].lower()

    params = entry.get("supported_parameters")
    if isinstance(params, list):
        low = {str(p).lower() for p in params}
        out["tools"] = "tools" in low or "tool_choice" in low
        out["thinking"] = bool(
            low & {"reasoning", "include_reasoning", "reasoning_effort"}
        )

    skills = entry.get("capabilities")
    if isinstance(skills, dict):
        if "vision" in skills and "vision" not in out:
            out["vision"] = bool(skills["vision"])
        if "trained_for_tool_use" in skills and "tools" not in out:
            out["tools"] = bool(skills["trained_for_tool_use"])
        for key in ("reasoning", "think", "thinking"):
            if key in skills:
                out["thinking"] = bool(skills[key])
                break
    elif isinstance(skills, list) and "vision" not in out:
        out["vision"] = any(str(s).lower() in ("vision", "image") for s in skills)

    return out


def _window_of(entry: dict[str, Any]) -> int | None:
    for field in WINDOW_FIELDS:
        value = entry.get(field)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def scan_models(config: Config) -> list[dict[str, Any]]:
    """The models on the server, with their capabilities.

    Listing only names was not enough: there is no point opening the camera
    on a model that does not accept images, or expecting tools from a model
    not trained for tool use. LM Studio tells us these.
    """
    return scan_models_result(config)["models"]


def batch_only_model(ident: str) -> bool:
    """OpenRouter `:batch` variant — not live chat, specific to the Batch API.

    These models give 404 with `/v1/chat/completions`; they belong to the
    asynchronous `/api/beta/batches` endpoint (can take hours, does not fit
    the tool turn loop). Dropped from the catalogue and on save.
    """
    text = str(ident or "").strip()
    if ":" not in text:
        return False
    return text.rsplit(":", 1)[-1].lower() == "batch"


def scan_models_result(config: Config) -> dict[str, Any]:
    """`{models, error}` — so the settings page shows the reason on an empty list."""
    # LM Studio management only on localhost — probing /api/v1/models on
    # NVIDIA/OpenRouter is wrong and a delay.
    if lmstudio.is_local_url(config.model.base_url):
        found = lmstudio.models(config.model.base_url)
        if found:
            models = []
            for m in found:
                row: dict[str, Any] = {
                    "id": m.key,
                    "name": m.name,
                    "max_context": m.max_context,
                    "vision": m.vision,
                    "tools": m.tools,
                    "loaded": [
                        {"id": i.id, "context": i.context} for i in m.instances
                    ],
                }
                if m.thinking is not None:
                    row["thinking"] = m.thinking
                models.append(row)
            return {"models": models, "error": None}

    if config.model.provider == "anthropic":
        entries, err = _anthropic_catalog(config)
        return {"models": entries, "error": err if not entries else None}

    payload, err = _openai_models_payload(config)
    raw_list = payload.get("data") if isinstance(payload, dict) else None
    entries: list[dict[str, Any]] = []
    if isinstance(raw_list, list):
        for raw in raw_list:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            if raw.get("type") in ("embeddings", "embedding"):
                continue
            ident = str(raw.get("id"))
            if "embed" in ident.lower():
                continue
            # `:batch` is not live chat — if selected, 404 + Batch API warning.
            if batch_only_model(ident):
                continue
            entries.append(_caps_of(raw))
    if provider_of(config.model) == "openrouter":
        from .config import OTO_MODEL

        entries.insert(0, {"id": OTO_MODEL, "name": "Oto — ücretsiz model havuzu"})
    return {"models": entries, "error": err if not entries else None}


def _anthropic_catalog(config: Config) -> tuple[list[dict[str, Any]], str | None]:
    """Claude model list. No window in the list; chat models accept images
    and thinking — this is a provider fact, not a number coming from the endpoint.
    """
    import urllib.error
    import urllib.request

    env = config.model.api_key_env or "ANTHROPIC_API_KEY"
    key = os.environ.get(env) or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return [], "anahtar yok"
    url = (config.model.base_url or "https://api.anthropic.com").rstrip("/")
    if url.endswith("/v1"):
        url = url + "/models"
    else:
        url = url + "/v1/models"
    req = urllib.request.Request(
        url,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "dornick",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REMOTE_PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        return [], f"HTTP {exc.code}"
    except TimeoutError:
        return [], "zaman aşımı"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return [], str(reason)[:80]
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return [], "liste yok"
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        ident = str(raw["id"])
        if "embed" in ident.lower():
            continue
        item = _caps_of(raw)
        # Claude chat models accept images and thinking; no window in the
        # list — no number is invented.
        item.setdefault("vision", True)
        item.setdefault("thinking", True)
        item.setdefault("tools", True)
        out.append(item)
    return out, None


def _ollama_show_caps(config: Config, name: str) -> dict[str, Any]:
    """Ollama `/api/show` — empty if the endpoint does not say. Not called in the catalogue."""
    base = config.model.base_url or ""
    if "11434" not in base and "ollama" not in base.lower():
        return {}
    import urllib.error
    import urllib.request

    root = lmstudio.root_of(base)
    req = urllib.request.Request(
        root.rstrip("/") + "/api/show",
        data=json.dumps({"name": name}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "dornick"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    info = payload.get("model_info") or payload.get("modelinfo") or {}
    if isinstance(info, dict):
        for key, value in info.items():
            if not str(key).endswith("context_length"):
                continue
            if isinstance(value, (int, float)) and value > 0:
                out["max_context"] = int(value)
                break
    skills = payload.get("capabilities")
    if isinstance(skills, list):
        low = {str(s).lower() for s in skills}
        out["vision"] = "vision" in low or "image" in low
        out["thinking"] = bool(low & {"thinking", "reasoning"})
        out["tools"] = "tools" in low
    return out


def available_models(config: Config) -> list[str]:
    """The model ids the server offers."""
    names, _err = available_models_with_error(config)
    return names


def available_models_with_error(config: Config) -> tuple[list[str], str | None]:
    """The model ids the server offers + error summary."""
    payload, err = _openai_models_payload(config)
    if not payload:
        return [], err

    entries = payload.get("data")
    if not isinstance(entries, list):
        return [], err or "liste yok"

    names = [
        str(entry.get("id"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("id")
        # Embedding models cannot chat; showing them in the list leads to a
        # wrong pick and the error only surfaces on the first message.
        and entry.get("type") not in ("embeddings", "embedding")
        and "embed" not in str(entry.get("id")).lower()
        # `:batch` is only the asynchronous Batch API — not in the live chat list.
        and not batch_only_model(str(entry.get("id")))
    ]
    return sorted(dict.fromkeys(names)), None


def loaded_models(config: Config) -> list[dict[str, Any]]:
    """The models currently loaded on the server.

    When a second request hits a busy model LM Studio loads a **second copy**
    of the model: `qwen3.5-9b`, `qwen3.5-9b:2`, `qwen3.5-9b:3`… Three copies
    of a 6.5 GB model mean 20 GB and the machine cannot take it.

    The real fix is prevention — `model.max_calls = 1` keeps a single
    request in flight to the server. This is diagnosis: how many copies are
    sitting there should be visible so the user understands what happened.

    `/api/v0/models` is LM Studio specific; returns empty on servers without it.
    """
    if config.model.provider != "openai" or not config.model.base_url:
        return []

    import urllib.error
    import urllib.request

    # `/api/v0` instead of `/v1`: only that endpoint gives state information.
    root = config.model.base_url.rstrip("/")
    root = root[: -len("/v1")] if root.endswith("/v1") else root

    try:
        with urllib.request.urlopen(f"{root}/api/v0/models", timeout=PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return []

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []

    return [
        {
            "id": entry.get("id", ""),
            "kind": entry.get("type", ""),
            "window": _window_of(entry),
            # Copies are told apart by `:2`, `:3` appended to the name; the
            # base name is needed to find how many copies each model has.
            "base": str(entry.get("id", "")).split(":")[0],
        }
        for entry in entries
        if isinstance(entry, dict) and entry.get("state") == "loaded"
    ]


# -- writing -----------------------------------------------------------


# Margin left so the output ceiling does not overflow the context (prompt + tools).
_TOKEN_RESERVE = 2048


def adopt_caps(config: Config, model: ModelConfig) -> ModelConfig:
    """Fills the model capabilities via catalogue/detect. Nothing invented.

    Writes window/thinking/vision if known; leaves them alone if not.
    max_tokens is clamped if larger than the window.
    """
    name = (model.name or "").strip()
    if not name or name.lower() == "oto":
        return _clamp_max_tokens(model)

    from dataclasses import replace as _replace

    probe = _replace(config, model=model)
    try:
        caps = detect_caps(probe)
    except Exception:
        return _clamp_max_tokens(model)

    fields: dict[str, Any] = {}
    window = caps.get("max_context")
    if isinstance(window, int) and window > 0:
        fields["context_window"] = window
    if "thinking" in caps:
        fields["can_think"] = bool(caps["thinking"])
        fields["thinking"] = bool(caps["thinking"])
    if "vision" in caps:
        fields["vision"] = bool(caps["vision"])
    if fields:
        model = _replace(model, **fields)
    return _clamp_max_tokens(model)


def _clamp_max_tokens(model: ModelConfig) -> ModelConfig:
    from dataclasses import replace as _replace

    window = int(model.context_window or 0)
    if window <= 0:
        return model
    ceiling = max(256, window - _TOKEN_RESERVE)
    if model.max_tokens <= ceiling:
        return model
    return _replace(model, max_tokens=ceiling)


def apply(config: Config, patch: dict[str, Any]) -> Config:
    """Writes the settings to disk and returns the updated configuration.

    Validation is done here, not in the UI: the settings page is not the
    only client (the file can be hand-edited too) and a broken value turns
    into a program that crashes on startup.
    """
    # The base is the on-disk state, not what the caller holds. The settings
    # page sends partial patches ("I only changed the permission mode") and
    # with a stale Config in hand the untouched fields silently reverted to
    # their old values.
    base = _from_disk(config)

    model = _model_patch(base.model, patch)
    patch_model = patch.get("model") or {}
    # If the model identity changed fill the context from the API (Detect not required).
    # If the user sent context_window in the same patch, leave it alone.
    identity_changed = (
        model.name != base.model.name
        or model.provider != base.model.provider
        or (model.base_url or "") != (base.model.base_url or "")
    )
    if identity_changed and "context_window" not in patch_model:
        try:
            model = adopt_caps(base, model)
        except Exception:
            model = _clamp_max_tokens(model)
    else:
        model = _clamp_max_tokens(model)

    context = _section(ContextConfig, base.context, patch.get("context"))
    permissions = _section(PermissionConfig, base.permissions, patch.get("permissions"))
    workshop = _section(SandboxConfig, base.sandbox, patch.get("sandbox"))
    speech = _section(VoiceConfig, base.voice, patch.get("voice"))
    located = _section(PlaceConfig, base.place, patch.get("place"))

    # Autostart is written to the registry, not a file; there is no point
    # holding it in the settings object, the real state is the registry itself.
    if (wanted := (patch.get("startup") or {}).get("enabled")) is not None:
        startup.apply(bool(wanted))
    if (wanted := (patch.get("shell_assoc") or {}).get("enabled")) is not None:
        shell_assoc.apply(bool(wanted))
    hearing = _section(ListenConfig, base.listen, patch.get("listen"))
    eye = _section(CameraConfig, base.camera, patch.get("camera"))
    surfing = _section(BrowserConfig, base.browser, patch.get("browser"))

    if permissions.mode not in {m["id"] for m in PERMISSION_MODES}:
        raise ValueError(f"Bilinmeyen izin kipi: {permissions.mode}")
    # The OpenRouter key is verified live BEFORE being saved: a wrongly
    # pasted key only blew up on the first message and the error was far
    # from the settings page. Without network the verification is skipped —
    # an offline setup must not lock up.
    _verify_openrouter_key(patch.get("keys") or {})
    if model.max_tokens < 256:
        raise ValueError("max_tokens en az 256 olmalı.")
    if model.context_window < model.max_tokens:
        raise ValueError("Bağlam penceresi max_tokens'tan küçük olamaz.")
    if not workshop.directory.strip():
        raise ValueError("Atölye klasörü boş olamaz.")
    # Selecting a project widens the write permission: validation is here,
    # not in the UI. An invalid root (drive root, system folder) would only
    # blow up when the agent tried to write there, and that is far too late.
    if (project := workshop.project.strip()):
        if (block := sandbox.root_block(Path(project).expanduser())) is not None:
            raise ValueError(block)

    updated = replace(
        base,
        model=model,
        context=context,
        permissions=permissions,
        sandbox=workshop,
        voice=speech,
        place=located,
        listen=hearing,
        camera=eye,
        browser=surfing,
    )
    _write_config(updated)

    # If the project CHANGED, write to the recent-projects notebook. Not on
    # every save: when the user changes the voice the top of the notebook
    # must not get shuffled.
    if project and project != base.sandbox.project.strip():
        sandbox.remember_project(updated.state_dir, str(Path(project).expanduser()))

    if keys := patch.get("keys"):
        _write_keys(config.state_dir, keys)
        # The user EXPLICITLY changed a key from the settings page: even if
        # the environment holds an old value it must be overwritten.
        # `export_keys` says "leave it if already set" (so the shell key
        # comes before the file); but an explicit change is the exception
        # to that rule — otherwise the new key never reached the running
        # process and only took effect after a restart.
        for name, value in keys.items():
            if value:
                os.environ[name] = value
        export_keys(config.state_dir)

    return updated


def _verify_openrouter_key(keys: dict[str, Any]) -> None:
    """Probes the OpenRouter key in the patch before saving.

    On 401 a ValueError: the settings page prints it as a red line and
    NOTHING is written to disk. Without network (undetermined) skip-and-save;
    the note falls to the terminal — an offline setup must not lock up.
    """
    candidate = str(keys.get("OPENROUTER_API_KEY") or "").strip()
    if not candidate or candidate == MASK:
        return

    from . import automode

    status = automode.verify_key(candidate)
    if status == "gecersiz":
        raise ValueError(
            "OpenRouter anahtarı geçersiz (401) — kaydedilmedi. "
            "openrouter.ai/keys sayfasından anahtarı kontrol et."
        )
    if status == "belirsiz":
        print(
            "[dornick] OpenRouter anahtarı doğrulanamadı (ağ yok?) — "
            "doğrulama atlandı, anahtar kaydedildi.",
            flush=True,
        )


def _from_disk(config: Config) -> Config:
    """The on-disk state of the configuration.

    `Config.load` is not used: it also mixes in environment variables, and
    a transient value from the shell would end up written to the persistent file.
    """
    path = config.state_dir / CONFIG_FILE
    if not path.exists():
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return config

    return replace(
        config,
        model=_section(ModelConfig, ModelConfig(), raw.get("model")),
        context=_section(ContextConfig, ContextConfig(), raw.get("context")),
        permissions=_section(PermissionConfig, PermissionConfig(), raw.get("permissions")),
        sandbox=_section(SandboxConfig, SandboxConfig(), raw.get("sandbox")),
        voice=_section(VoiceConfig, VoiceConfig(), raw.get("voice")),
        place=_section(PlaceConfig, PlaceConfig(), raw.get("place")),
        listen=_section(ListenConfig, ListenConfig(), raw.get("listen")),
        camera=_section(CameraConfig, CameraConfig(), raw.get("camera")),
    )


def _model_patch(current: ModelConfig, patch: dict[str, Any]) -> ModelConfig:
    fields = dict(patch.get("model") or {})

    # Choosing a provider determines the address and the key variable
    # together; leaving the user to keep all three consistent by hand is an
    # invitation to error.
    if chosen := patch.get("provider"):
        entry = next((e for e in PROVIDERS if e["id"] == chosen), None)
        if entry is None:
            raise ValueError(f"Bilinmeyen sağlayıcı: {chosen}")
        fields.setdefault("provider", entry["provider"])
        fields.setdefault("base_url", entry["base_url"])
        fields.setdefault("api_key_env", entry["env"])

    unknown = set(fields) - set(ModelConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"Bilinmeyen model alanı: {', '.join(sorted(unknown))}")

    for name in ("max_tokens", "context_window"):
        if name in fields and fields[name] is not None:
            fields[name] = int(fields[name])
    for name in ("vision", "can_think"):
        if name in fields and fields[name] is not None:
            fields[name] = bool(fields[name])

    # When local opt is switched on prevent the double copy — pull to 1
    # unless the user explicitly wrote max_calls.
    if fields.get("local_optimize") is True and "max_calls" not in fields:
        fields["max_calls"] = 1

    # OpenRouter `:batch` does not accept live chat completions; fall back
    # to the same model's synchronous id (google/…:batch → google/…).
    if "name" in fields and batch_only_model(str(fields.get("name") or "")):
        raw = str(fields["name"]).strip()
        fields["name"] = raw.rsplit(":", 1)[0]

    return replace(current, **fields)


def _section(kind: type, current: Any, data: Any) -> Any:
    if not data:
        return current
    unknown = set(data) - set(kind.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{kind.__name__} için bilinmeyen alan: {', '.join(sorted(unknown))}")
    return replace(current, **data)


def _write_config(config: Config) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": asdict(config.model),
        "context": asdict(config.context),
        "permissions": asdict(config.permissions),
        "sandbox": asdict(config.sandbox),
        "voice": asdict(config.voice),
        "place": asdict(config.place),
        "listen": asdict(config.listen),
        "camera": asdict(config.camera),
        "browser": asdict(config.browser),
        # The mail identity is not here: it is in `keys.json`, just like the
        # API keys. config.json can end up in a project and fall into
        # version control.
    }
    _atomic(config.state_dir / CONFIG_FILE, json.dumps(payload, ensure_ascii=False, indent=2))


def _write_keys(state_dir: Path, incoming: dict[str, Any]) -> None:
    """Merges and writes the keys.

    A masked incoming field means "unchanged": the settings page never saw
    the real value so it cannot send it back either. An empty string is a
    delete request.
    """
    keys = load_keys(state_dir)
    for name, value in incoming.items():
        text = str(value or "").strip()
        if text == MASK:
            continue
        if text:
            keys[name] = text
        else:
            keys.pop(name, None)

    path = state_dir / KEYS_FILE
    state_dir.mkdir(parents=True, exist_ok=True)
    _atomic(path, json.dumps(keys, ensure_ascii=False, indent=2))
    try:
        # Only the owner should be able to read. On Windows this call is
        # silently a no-op; there the file already sits under the user profile.
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _atomic(path: Path, text: str) -> None:
    """A half-written settings file makes the program unable to start."""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)
