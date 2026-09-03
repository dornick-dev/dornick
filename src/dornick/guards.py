r"""Hard guards — refusals INDEPENDENT of the permission mode, impossible to lift.

The permission engine's `allow`/`yolo` branches are the user's own
loosening; but a few targets must never be opened in any mode, by any rule,
because opening them collapses the security model itself:

  * `.dornick/keys.json` — API keys and the mail password. Even reading is
    dangerous: a secret that lands in a tool result can be put, via
    injection, into the next `fetch` URL (query string = channel) and leak
    out. NO tool that touches this file has a legitimate reason — the
    application reads the keys internally, not through a tool.
  * `.dornick/config.json`, `.dornick/gate.json` — hold the permission mode,
    the allow/deny rules, the outer gate key. WRITING here means the model
    pulling its own gate to `yolo`. Reading is free (the model must be able
    to see which rule it is under); writing/shell is a hard refusal.
  * Windows startup persistence (`...CurrentVersion\Run`) and the Startup
    folder — code that persists on the machine. Shell/mutation cannot reach
    here.

This is NOT A PRISON, it is an "intent gate" like the one in hooks.py: a
shell command that hides the name (base64, variable assignment) can in
theory get past it. What it closes is the real failure mode — a prompt
injection or an over-compliant model reading and sending the secret /
raising the mode DIRECTLY, in one step. Against a deliberate adversary the
real fence is at the operating-system level.
"""

from __future__ import annotations

import re
from typing import Any

# Files whose reading and writing are both hard refusals (with .dornick in the path).
_SECRET = re.compile(r"\.dornick[\\/]keys\.json", re.IGNORECASE)

# Only WRITE/shell is a hard refusal; reading is free. skills_onayli.json is
# here too: the skill approval manifest — if a tool could write it, an
# injection could write both the file and its digest and bypass the
# startup-exec protection.
_SETTINGS = re.compile(
    r"\.dornick[\\/](?:config|gate|skills_onayli)\.json", re.IGNORECASE)

# Persistence surfaces: shell/mutation cannot reach.
_PERSISTENCE = re.compile(
    r"currentversion[\\/]run\b"                 # HKCU/HKLM ...Run
    r"|start menu[\\/]programs[\\/]startup",    # the Startup folder
    re.IGNORECASE,
)

# These tools can write to disk or run commands — the "write surface".
# Tools that write/run without carrying the mutation flag are here too.
_WRITE_SURFACE = frozenset({
    "shell", "write_file", "edit_file", "copy_in", "hand", "git",
})


def _values(payload: Any) -> list[str]:
    """All string values inside the input (nested dicts/lists included).

    Subject extraction (SUBJECT_KEYS) is not enough: `copy_in`'s source is in
    the `source` field, the `http` node's in `url` — all of it must be
    scanned, or a call reaching keys.json via `source` slips through the gate."""
    out: list[str] = []
    stack = [payload]
    while stack:
        p = stack.pop()
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            stack.extend(p.values())
        elif isinstance(p, (list, tuple)):
            stack.extend(p)
    return out


def sabit_ret(tool: str, mutates: bool, payload: Any) -> str | None:
    """Does this call violate one of the hard guards?

    Returns: a human-language reason if there is a violation (the permission
    engine uses it as DENY and never looks at the mode), otherwise None.
    """
    values = _values(payload)
    if not values:
        return None
    can_write = mutates or tool in _WRITE_SURFACE

    for v in values:
        if _SECRET.search(v):
            return (
                "Bu çağrı `.dornick/keys.json` dosyasına uzanıyor ve sabit "
                "olarak engellendi — bu dosya API anahtarlarını ve posta "
                "parolasını tutuyor, ne okunur ne kopyalanır. Sırlara bir "
                "aracın işi için gerek yok; bir kimlik gerekiyorsa kullanıcıya "
                "sor, dosyayı okuma."
            )
    if not can_write:
        return None  # the rest is only for write/shell
    for v in values:
        if _SETTINGS.search(v):
            return (
                "Bu çağrı `.dornick` ayar/kapı dosyasına YAZMAYA çalışıyor ve "
                "sabit olarak engellendi — izin kipi, kurallar ve dış kapı "
                "buradan yönetilir; bir araçla değiştirilmesi güvenlik kapısını "
                "kendi kendine açmak olurdu. Kip/kural değişikliği kullanıcının "
                "işidir (Ayarlar)."
            )
        if _PERSISTENCE.search(v):
            return (
                "Bu çağrı Windows açılış kalıcılığına (Run anahtarı / Başlangıç "
                "klasörü) yazmaya çalışıyor ve sabit olarak engellendi — "
                "makinede kalıcı, kullanıcının görmediği kod bırakmak bu "
                "araçların işi değil. Gerçekten gerekliyse kullanıcıya söyle."
            )
    return None
