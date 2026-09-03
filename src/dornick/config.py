"""Configuration.

Precedence: explicit argument > environment variable > config file > default.
Config file: <workspace>/.dornick/config.json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from . import sandbox
from .listen import ListenConfig
from .place import PlaceConfig
from .voice import VoiceConfig

# Model ids are not guessed. See platform.claude.com/docs -> models.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"

# The fresh-install default is OpenRouter + "oto": many providers with a
# single key and a setup that runs on free models the moment the key is
# entered (see automode.py). Existing users are unaffected — the settings
# page writes the model section with ALL its fields, and the values in the
# file override these defaults.
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OTO_MODEL = "oto"
DEFAULT_MODEL = OTO_MODEL

# Above this value without streaming there is an HTTP-timeout risk in the SDK.
NONSTREAM_TOKEN_CEILING = 16_000


@dataclass(slots=True)
class ModelConfig:
    name: str = DEFAULT_MODEL
    # Output ceiling for a single reply. 32k is excessive on many flash/small
    # endpoints; the default is enough for agentic work, catalogue/detect
    # tightens it to the window.
    max_tokens: int = 16_384
    # The model's context window. Compaction triggers against this. 200k was
    # a lie on many models (compaction comes late, the server drops the
    # head). Conservative base; on selection the API/catalogue writes the
    # real value (Detect is not required).
    context_window: int = 65_536
    # low | medium | high | xhigh | max — at least high for agentic work.
    # Anthropic only; ignored on local providers.
    effort: str = "high"
    # Adaptive thinking. budget_tokens was removed on Opus 4.7+, returns 400.
    thinking: bool = True
    # "omitted" is the default; "summarized" if we are going to show thinking to the user.
    thinking_display: str = "summarized"
    # From the catalogue: does the model accept images / does it have a thinking field.
    # None = unknown (try, learn if rejected). False = never send.
    vision: bool | None = None
    can_think: bool | None = None

    # The model that steps in when the primary model PERMANENTLY fails
    # (credit ran out, credentials invalid, model removed) instead of the
    # turn dying. If empty, today's behaviour: the error surfaces as-is.
    # Transient errors (connection, 429, 5xx) never come here — they are
    # already retried and falling back would hide them.
    fallback_model: str = ""

    # anthropic | openai
    # "openai" covers every OpenAI-compatible server: LM Studio, Ollama, vLLM,
    # llama.cpp server, OpenRouter, OpenAI itself.
    provider: str = "openai"
    # LM Studio: http://localhost:1234/v1 · Ollama: http://localhost:11434/v1
    base_url: str | None = OPENROUTER_URL
    # The environment variable the API key is read from. Local servers do
    # not want a key but the client expects a value.
    api_key_env: str | None = "OPENROUTER_API_KEY"
    # Useful on local models; sent only on the openai provider because
    # Anthropic 4.7+ returns 400.
    temperature: float | None = None
    # How long the model stays loaded on the server (seconds). LM Studio
    # understands it as `ttl`, Ollama as `keep_alive`; both are sent and each
    # ignores the field it does not know. 0 = do not touch, the server's own
    # behaviour applies. Reloading on every request takes tens of seconds
    # and makes the first answer wait.
    keep_loaded: int = 0
    # Maximum concurrent requests to the server. Must be 1 on local servers:
    # when a second request hits a busy model LM Studio loads a **second
    # copy** of the model. Three sub-agents mean three copies — 20 GB on a
    # 6.5 GB model. Official APIs have no such problem, it can be raised there.
    max_calls: int = 1
    # Local LLM optimisation (opt-in). When on: unload the other models,
    # keep a single copy, lower the context to VRAM/model size. When off,
    # today's behaviour — whatever the user wrote.
    local_optimize: bool = False

    @property
    def is_local(self) -> bool:
        return self.provider == "openai"

    def thinking_param(self) -> dict[str, Any] | None:
        if self.can_think is False:
            return None
        if not self.thinking:
            return {"type": "disabled"}
        return {"type": "adaptive", "display": self.thinking_display}


@dataclass(slots=True)
class ContextConfig:
    """Context and cache policy.

    cache_message_breakpoints: number of breakpoints placed in the message list.
        The total limit is 4; one goes to the system prompt, the rest here.
    lookback_blocks: maximum number of content blocks between two breakpoints.
        The API scans backwards at most 20 blocks; exceed 20 and the cache
        silently misses. 15 to leave a safety margin.
    keep_recent_images: the last N images kept in history. Earlier ones are
        replaced with a text placeholder (screenshots are heavy: ~1.5-4.8k tokens).
    clear_tool_uses: server-side context editing (beta). Clears old tool_result
        blocks. Because it changes the prefix it drops the cache from that
        point on — trigger it rarely and predictably.
    """

    cache_message_breakpoints: int = 3
    lookback_blocks: int = 15
    keep_recent_images: int = 3
    clear_tool_uses: bool = False
    compact: bool = False
    # Maximum tools that may run concurrently. The model can ask for ten
    # tools in one turn; starting them all at once exhausts memory and CPU
    # on a weak machine. Sub-agents are inside this limit too.
    max_parallel: int = 4
    # Maximum SUB-AGENTS that may run concurrently. Separate from the tool
    # limit: a sub-agent is far heavier than a single tool (its own model
    # calls, its own tools). A spawn hitting the limit waits, it is not
    # refused — the work queues. 1 makes sense on a local server with a
    # single model copy.
    max_agents: int = 3


@dataclass(slots=True)
class PermissionConfig:
    """Permission policy.

    mode:
        auto  — everything non-mutating is free, mutating ones are asked
        ask   — every tool is asked (except those on the allow list)
        plan  — no mutating tool runs (read-only exploration)
        yolo  — nothing is asked. Your own risk.

    Rules are fnmatch patterns in the form "tool_name:argument-pattern":
        "shell:git *"      -> allow git commands
        "write_file:*"     -> allow all writes
        "shell:*"          -> all shell commands
    """

    mode: str = "ask"
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SandboxConfig:
    """The agent's own folder.

    enabled: if switched off the write restriction lifts and the agent can
        write anywhere. Switching it off must be a conscious decision — on
        is the default.
    directory: relative to the workspace or an absolute path.
    """

    enabled: bool = True
    directory: str = sandbox.DEFAULT_DIR
    # The project folder the user picked. If empty only the workshop is
    # writable (the behaviour so far). If set, that place becomes writable
    # too: the selection itself is the consent — the user has said "work
    # here". A project is not a SESSION: changing it does not affect the
    # mind, memories or conversation history, only where the work happens.
    project: str = ""


@dataclass(slots=True)
class CameraConfig:
    """Camera.

    Ships off. Switching it on lights the LED and streams the preview;
    switching it off releases the device (no restart needed). Frames do not
    go to the chat model on their own: with an NVIDIA GPU objects are read
    locally and text goes to the model; without a GPU a snapshot is taken
    when you ask.

    `cloud_ok`: on motion detection, may the frame also go to the CLOUD
    model? Default no — a home-camera frame does not leave the machine
    without the user's explicit consent. Ignored while a local model is
    selected. If GPU analysis succeeds the frame does not go anyway.
    """

    enabled: bool = False
    cloud_ok: bool = False


@dataclass(slots=True)
class BrowserConfig:
    """dornick chrome — the browser driven through the DevTools port.

    Ships off: an assistant that opens pages on its own is more unsettling
    than one that talks on its own. When on, the browser runs with
    Dornick's separate profile (`.dornick/chrome/`) — the user's everyday
    browser is not touched.
    """

    enabled: bool = False
    port: int = 9222


@dataclass(slots=True)
class Config:
    workspace: Path
    state_dir: Path
    model: ModelConfig = field(default_factory=ModelConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    permissions: PermissionConfig = field(default_factory=PermissionConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    # Location: the answer to "what's the weather tomorrow?" depends on it.
    place: PlaceConfig = field(default_factory=PlaceConfig)
    listen: ListenConfig = field(default_factory=ListenConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    # Extra system-prompt piece (personality / standing directive).
    persona_path: Path | None = None

    @property
    def sessions_dir(self) -> Path:
        return self.state_dir / "sessions"

    @property
    def mind_dir(self) -> Path:
        return self.state_dir / "mind"

    def open_sandbox(self) -> "sandbox.Sandbox":
        return sandbox.Sandbox.open(
            self.workspace, self.sandbox.directory, enabled=self.sandbox.enabled,
            project=self.sandbox.project, state_dir=self.state_dir,
        )

    def ensure_dirs(self) -> None:
        for d in (self.state_dir, self.sessions_dir, self.mind_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, workspace: Path | str | None = None) -> Config:
        ws = _resolve_workspace(workspace)
        state = Path(os.getenv("DORNICK_STATE_DIR") or (ws / ".dornick"))
        if not os.getenv("DORNICK_STATE_DIR"):
            _adopt_legacy_state(ws, state)

        cfg = cls(workspace=ws, state_dir=state)

        raw = _read_json(state / "config.json")
        if raw:
            cfg = _merge(cfg, raw)

        # Environment variables override the file.
        if model := os.getenv("DORNICK_MODEL"):
            cfg.model = replace(cfg.model, name=model)
        if effort := os.getenv("DORNICK_EFFORT"):
            cfg.model = replace(cfg.model, effort=effort)
        if provider := os.getenv("DORNICK_PROVIDER"):
            cfg.model = replace(cfg.model, provider=provider)
        if base_url := os.getenv("DORNICK_BASE_URL"):
            cfg.model = replace(cfg.model, base_url=base_url)
        if mode := os.getenv("DORNICK_PERMISSION_MODE"):
            cfg.permissions.mode = mode

        if cfg.persona_path is None:
            candidate = state / "persona.md"
            if candidate.exists():
                cfg.persona_path = candidate

        return cfg


# Workspace (home) resolution. The problem: the home was derived from
# `Path.cwd()`, so when dornick was launched from another directory (e.g. a
# parent folder) it set up `.dornick` and `atolye` THERE, scattering its data
# wherever it happened to be — the user: "it must not step outside the place
# we assigned it". Now once the home is determined it is PINNED: wherever
# you launch Dornick from, it uses the same home.
#
# Precedence: explicit argument (test/caller; does not pin) > DORNICK_WORKSPACE
# (pins) > pinned home pointer > an existing .dornick upwards from cwd (like
# git finding .git; pins) > cwd (pins).
def _home_pointer() -> Path:
    return Path.home() / ".dornick" / "home"


# neo→Dornick transition (01.09.2026): old installs' data must not be lost.
# If the new pointer is missing the old one is read; if the workspace has
# no .dornick but has .neocp the folder is adopted as-is (not a copy — a
# rename; brain/sessions/settings move over unchanged).
_LEGACY_POINTER = Path.home() / ".neocp" / "home"
_LEGACY_STATE_NAME = ".neocp"


def _read_home() -> Path | None:
    for candidate in (_home_pointer(), _LEGACY_POINTER):
        try:
            txt = candidate.read_text(encoding="utf-8").strip()
            if txt:
                return Path(txt).expanduser().resolve()
        except Exception:
            continue
    return None


def _adopt_legacy_state(ws: Path, state: Path) -> None:
    """Adopts the old `.neocp` state folder under the new name (one time)."""
    if state.exists():
        return
    legacy = ws / _LEGACY_STATE_NAME
    if not legacy.is_dir():
        return
    try:
        legacy.rename(state)
    except OSError:
        pass   # if locked, leave it; the new folder is set up from scratch


def _pin_home(ws: Path) -> None:
    try:
        p = _home_pointer()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(ws), encoding="utf-8")
    except Exception:
        pass


def _resolve_workspace(explicit: Path | str | None) -> Path:
    # 1. Explicit argument: definitive and does NOT pin (tests pass tmp_path;
    #    the home pointer must not be sacrificed to a test).
    if explicit:
        return Path(explicit).expanduser().resolve()
    # 2. DORNICK_WORKSPACE: the user's conscious choice — pins.
    env = os.getenv("DORNICK_WORKSPACE")
    if env:
        ws = Path(env).expanduser().resolve()
        _pin_home(ws)
        return ws
    # 3. Pinned home: the same home wherever it is launched from.
    pinned = _read_home()
    if pinned and pinned.is_dir():
        return pinned
    # 4. Look upwards from cwd for an existing home, pin it when found.
    cur = Path.cwd().resolve()
    for cand in [cur, *cur.parents]:
        if (cand / ".dornick").is_dir():
            _pin_home(cand)
            return cand
    # 5. None of them: cwd becomes the home and is pinned.
    _pin_home(cur)
    return cur


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        # utf-8-sig: on Windows Notepad saves config.json with a BOM and a
        # plain utf-8 read made the program UNABLE TO START with "Unexpected
        # UTF-8 BOM" (seen live in the 1.1.0 install smoke test). On a
        # BOM-less file the behaviour is byte-identical.
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} okunamadı: {exc}") from exc


def _merge(cfg: Config, raw: dict[str, Any]) -> Config:
    if m := raw.get("model"):
        cfg.model = replace(cfg.model, **_only_fields(ModelConfig, m))
    if c := raw.get("context"):
        cfg.context = replace(cfg.context, **_only_fields(ContextConfig, c))
    if p := raw.get("permissions"):
        cfg.permissions = replace(cfg.permissions, **_only_fields(PermissionConfig, p))
    if s := raw.get("sandbox"):
        cfg.sandbox = replace(cfg.sandbox, **_only_fields(SandboxConfig, s))
    if v := raw.get("voice"):
        cfg.voice = replace(cfg.voice, **_only_fields(VoiceConfig, v))
    if v := raw.get("place"):
        cfg.place = replace(cfg.place, **_only_fields(PlaceConfig, v))
    if l := raw.get("listen"):
        cfg.listen = replace(cfg.listen, **_only_fields(ListenConfig, l))
    if c := raw.get("camera"):
        cfg.camera = replace(cfg.camera, **_only_fields(CameraConfig, c))
    if b := raw.get("browser"):
        cfg.browser = replace(cfg.browser, **_only_fields(BrowserConfig, b))
    if persona := raw.get("persona_path"):
        cfg.persona_path = (cfg.state_dir / persona).resolve()
    return cfg


def _only_fields(kind: type, data: dict[str, Any]) -> dict[str, Any]:
    known = set(kind.__dataclass_fields__)
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"{kind.__name__} için bilinmeyen alan: {', '.join(sorted(unknown))}")
    return data
