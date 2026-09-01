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
# `komut`: `kos` aracının tespiti geçersiz kılan alanı. Burada olmasaydı
# elle verilen bir komut kapıya `path` olarak görünürdü — yani kural
# komutu değil klasörü eşleştirirdi ve "şu klasörde test koş" izni, aynı
# klasörde HERHANGİ bir komuta izin haline gelirdi.
SUBJECT_KEYS = ("command", "komut", "path", "url", "target", "query", "pattern")


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

        # Ajanın KENDİ defterine yazması mutasyon sayılmıyor: `mind_memory
        # save` için kullanıcıya onay penceresi açmak (plan kipinde ise
        # düpedüz reddetmek) zihni durduruyordu — konuşma dökümü akarken
        # kalıcı bellek iki gün boyunca hiçbir tercih/ders/olgu yazmadı.
        # Silmek (forget) hâlâ mutasyon ve gated kalıyor.
        mutating = spec.mutates and not _safe_action(spec, args)

        if self.mode == "plan":
            if mutating:
                return Decision.DENY, "mode:plan"
            return Decision.ALLOW, "mode:plan"

        if self.mode == "auto":
            return (Decision.ASK if mutating else Decision.ALLOW), "mode:auto"

        # mode == "ask": her şey sorulur. TEK istisna, aracın açıkça güvenli
        # ilan ettiği eylemler (ajanın kendi defterine yazması) — yoksa her
        # hatıra bir onay penceresi olur ve model kaydetmeyi bırakır.
        # Okuma/yazma gibi asıl işler burada aynen sorulmaya devam ediyor.
        if _safe_action(spec, args):
            return Decision.ALLOW, "mode:ask"
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


def _safe_action(spec: "ToolSpec", args: dict[str, Any]) -> bool:
    """Bu çağrı, aracın onaysız yapabileceğini ilan ettiği eylem mi?

    Çok-eylemli araçlarda (`action` enum'u) tek bir `mutates` bayrağı fazla
    kaba kalıyor: `mind_memory save` ajanın kendi not defterine yazmak,
    `forget` ise kalıcı silme. İkisini aynı kefeye koymak zihni durdurdu.
    """
    safe = getattr(spec, "safe_actions", ()) or ()
    if not safe:
        return False
    return str(args.get("action") or "") in safe


def _first_match(subject: str, rules: list[str]) -> str | None:
    tool = subject.split(":", 1)[0]
    for rule in rules:
        if rule == "*" or fnmatch(subject, rule) or fnmatch(tool, rule):
            return rule
    return None
