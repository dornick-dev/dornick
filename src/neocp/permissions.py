"""İzin motoru.

Kritik tasarım kararı: bu kapı **döngünün dışındadır**. Modelin onayladığı
bir şey değil, harness'ın uyguladığı bir şey. Politikayı ajanın mantığına
gömersen, model onu ikna edebilir hale gelir.

Kural biçimi: "araç_adı:argüman-deseni" (fnmatch).
    "shell:git *"     git komutları
    "shell:*"         tüm kabuk komutları
    "write_file:*"    tüm dosya yazmaları
    "*"               her şey

Reddetme her zaman kazanır.
"""

from __future__ import annotations

import json
from enum import Enum
from fnmatch import fnmatch
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .tools.base import ToolSpec

# Bir aracın "neyi hedeflediğini" temsil eden argümanlar, öncelik sırasıyla.
SUBJECT_KEYS = ("command", "path", "url", "target", "query", "pattern")


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionEngine:
    def __init__(self, mode: str, allow: list[str], deny: list[str]) -> None:
        if mode not in ("auto", "ask", "plan", "yolo"):
            raise ValueError(f"Bilinmeyen izin modu: {mode}")
        self.mode = mode
        self.allow = list(allow)
        self.deny = list(deny)

    @classmethod
    def from_config(cls, cfg: Any) -> PermissionEngine:
        return cls(cfg.mode, cfg.allow, cfg.deny)

    def evaluate(self, spec: "ToolSpec", args: dict[str, Any]) -> tuple[Decision, str]:
        subject = f"{spec.name}:{describe(args)}"

        if rule := _first_match(subject, self.deny):
            return Decision.DENY, rule

        if rule := _first_match(subject, self.allow):
            return Decision.ALLOW, rule

        if self.mode == "yolo":
            return Decision.ALLOW, "mode:yolo"

        if self.mode == "plan":
            if spec.mutates:
                return Decision.DENY, "mode:plan"
            return Decision.ALLOW, "mode:plan"

        if self.mode == "auto":
            return (Decision.ASK if spec.mutates else Decision.ALLOW), "mode:auto"

        # mode == "ask"
        return Decision.ASK, "mode:ask"

    def remember_allow(self, spec: "ToolSpec", args: dict[str, Any]) -> str:
        """Kullanıcı 'bir daha sorma' derse üretilecek kural."""
        rule = f"{spec.name}:{describe(args)}" if describe(args) else f"{spec.name}:*"
        if rule not in self.allow:
            self.allow.append(rule)
        return rule


def describe(args: dict[str, Any]) -> str:
    """Argümanlardan eşleştirilebilir tek satırlık bir özne çıkarır."""
    for key in SUBJECT_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    if not args:
        return ""
    return json.dumps(args, ensure_ascii=False, sort_keys=True)[:200]


def _first_match(subject: str, rules: list[str]) -> str | None:
    tool = subject.split(":", 1)[0]
    for rule in rules:
        if rule == "*" or fnmatch(subject, rule) or fnmatch(tool, rule):
            return rule
    return None
