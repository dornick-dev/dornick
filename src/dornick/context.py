"""Bağlam ve önbellek politikası.

Tek değişmez kural: **önbellek bir önek eşleşmesidir.** Önekte herhangi bir
bayt değişirse o noktadan sonraki her şey geçersiz olur. Render sırası
tools -> system -> messages. Buradaki her karar bu kuraldan türer.

Bu modül geçmişi asla yerinde değiştirmez; API'ye gidecek bir kopya üretir.
Olay günlüğü ham gerçeği tutmaya devam eder.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .config import ContextConfig, ModelConfig

if TYPE_CHECKING:  # pragma: no cover
    from .prompt import SystemPrompt

Block = dict[str, Any]
Message = dict[str, Any]

EPHEMERAL: Block = {"type": "ephemeral"}

# API isteğinde toplam breakpoint sınırı. Biri sistem promptuna ayrılır.
MAX_BREAKPOINTS = 4

# Sunucu tarafı bağlam düzenleme beta bayrağı.
CONTEXT_EDIT_BETA = "context-management-2025-06-27"
COMPACT_BETA = "compact-2026-01-12"

IMAGE_PLACEHOLDER = "[eski ekran görüntüsü bağlamdan çıkarıldı]"

# Eski araç yüklerinin kısaltma eşiği (harf) ve dokunulmayan kuyruk.
#
# Ölçülen yara: bir web sayfası yazımında HTML'in tamamı `write_file`
# argümanında geçmişe giriyor ve SONRAKİ HER İSTEKLE yeniden gönderiliyor —
# 51.608 token'lik gerçek bir istemin ~12-14k'sı buydu. Dosya diskte zaten
# duruyor; modelin geçmişte ihtiyacı olan şey "ne yaptım"ın izi, baytların
# kendisi değil. Gerekirse read_file ile açar.
#
# Kuyruk korunuyor: model az önce yazdığı/okuduğu içeriğe hâlâ atıf
# yapabilir. Anthropic'in sunucu-taraflı `clear_tool_uses` betası aynı işi
# yapıyor ama yalnız Anthropic arka ucunda; bu yol her arka uçta çalışıyor.
TRIM_TOOL_CHARS = 1_600
TRIM_KEEP_MESSAGES = 6
# Browser / büyük dump araçları: son 1–2 mesaj hariç daha agresif kısalt.
TRIM_BROWSER_CHARS = 600
TRIM_BROWSER_KEEP = 2
TRIM_NOTE = "… [{gone:,} harf geçmişten kısaltıldı — gerekirse dosyadan/araçtan yeniden oku]"

# Bu araçların sonuçları HTML/DOM/ağ dökümü taşıyor; geçmişte tutmak
# Market Lens tarzı taramalarda istemi şişiriyor.
_HEAVY_TOOLS = frozenset({
    "browser", "fetch", "read_file", "write_file", "edit_file",
})


@dataclass(slots=True)
class Prepared:
    """API'ye gönderilmeye hazır istek parçaları."""

    system: list[Block]
    messages: list[Message]
    betas: list[str]
    context_management: dict[str, Any] | None

    def request_kwargs(self, model: ModelConfig, tools: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model.name,
            "max_tokens": model.max_tokens,
            "system": self.system,
            "messages": saglayici_alanlarini_at(self.messages),
            "tools": tools,
            "output_config": {"effort": model.effort},
        }
        if (thinking := model.thinking_param()) is not None:
            kwargs["thinking"] = thinking
        if self.context_management:
            kwargs["context_management"] = self.context_management
        if self.betas:
            kwargs["betas"] = self.betas
        return kwargs

    @property
    def needs_beta_client(self) -> bool:
        return bool(self.betas)


class ContextPolicy:
    def __init__(self, cfg: ContextConfig) -> None:
        self.cfg = cfg

    def prepare(self, system: "SystemPrompt", messages: list[Message]) -> Prepared:
        system_blocks = build_system(system)
        prepared = copy.deepcopy(messages)
        prune_images(prepared, keep=self.cfg.keep_recent_images)
        prune_tool_payloads(prepared)
        place_breakpoints(
            prepared,
            limit=min(
                self.cfg.cache_message_breakpoints,
                MAX_BREAKPOINTS - len(system_blocks),
            ),
            stride=self.cfg.lookback_blocks,
        )

        betas: list[str] = []
        edits: list[Block] = []
        if self.cfg.clear_tool_uses:
            betas.append(CONTEXT_EDIT_BETA)
            edits.append({"type": "clear_tool_uses_20250919"})
        if self.cfg.compact:
            betas.append(COMPACT_BETA)
            edits.append({"type": "compact_20260112"})

        return Prepared(
            system=system_blocks,
            messages=prepared,
            betas=betas,
            context_management={"edits": edits} if edits else None,
        )


def saglayici_alanlarini_at(messages: list[Message]) -> list[Message]:
    """Anthropic'e giderken sağlayıcıya özel alanları ayıklar.

    `tool_use` bloklarında OpenAI-uyumlu sağlayıcıların kendi alanları
    taşınıyor (Gemini'nin `thought_signature`'ı gibi) — o sağlayıcıya geri
    göndermek ZORUNLU, ama Anthropic tanımadığı alanı reddediyor. Aynı
    konuşma iki sağlayıcı arasında taşınabildiği için (yedek model, model
    değiştirme) bu ayıklama şart.

    Gereksiz kopya yok: böyle bir alan taşıyan blok yoksa liste olduğu gibi
    dönüyor — bu, mesajların ezici çoğunluğu için geçerli.
    """
    if not any(
        isinstance(b, dict) and "saglayici" in b
        for m in messages
        for b in (m.get("content") or [] if isinstance(m.get("content"), list) else [])
    ):
        return messages

    temiz: list[Message] = []
    for m in messages:
        icerik = m.get("content")
        if not isinstance(icerik, list):
            temiz.append(m)
            continue
        temiz.append({
            **m,
            "content": [
                {k: v for k, v in b.items() if k != "saglayici"}
                if isinstance(b, dict) and "saglayici" in b else b
                for b in icerik
            ],
        })
    return temiz


def build_system(system: "SystemPrompt") -> list[Block]:
    """Sistem promptunu önbelleklenen bloklara böler.

    İki blok, iki breakpoint:

        [0] core     — her oturumda birebir aynı. Aynı çalışma alanında
                       açılan bir sonraki oturum burayı önbellekten okur.
        [1] identity — diskteki zihinden gelen ruh; oturumlar arasında değişir.

    Önek eşleşmesi olduğu için ruh değiştiğinde core hâlâ geçerli kalır.
    Tek blok olsaydı her yeni hatıra tüm önbelleği düşürürdü.

    Araçlar sistemden ÖNCE render edilir, yani [0]'daki breakpoint onları da
    kapsar. Bu yüzden buraya asla saat, aktif pencere, oturum kimliği gibi
    tur başına değişen şey koyma — sonraki her şeyi çöpe atarsın.
    """
    blocks = [{"type": "text", "text": system.core, "cache_control": EPHEMERAL}]
    if system.identity:
        blocks.append({"type": "text", "text": system.identity, "cache_control": EPHEMERAL})
    return blocks


def place_breakpoints(messages: list[Message], *, limit: int, stride: int) -> None:
    """Mesaj listesine önbellek breakpoint'leri yerleştirir (yerinde).

    İki şeyi aynı anda çözer:

    1. **20 bloklu geri-bakış penceresi.** Her breakpoint önceki önbellek
       girdisini ararken geriye doğru en fazla 20 içerik bloğu tarar. Ajanik
       bir turda 15 araç çağrısı 30 blok demek — pencereyi aşarsan önbellek
       sessizce ıskalar ve tam fiyat ödersin. `stride` bunu 20'nin altında
       tutar.

    2. **Breakpoint kayması.** Her turda breakpoint'i sadece sona koyarsan
       her istek yeni bir önbellek girdisi yazar. Ara breakpoint'ler kümülatif
       blok sayısının `stride` katlarına çıpalanır; böylece konuşma büyürken
       yerlerinde kalır ve okuma isabeti sürer.
    """
    if limit <= 0 or not messages:
        return

    clear_breakpoints(messages)

    # Her mesajın bittiği kümülatif blok indeksi.
    ends: list[int] = []
    total = 0
    for msg in messages:
        content = msg.get("content")
        total += len(content) if isinstance(content, list) else 1
        ends.append(total)

    targets: list[int] = []

    # En yeni mesaj her zaman breakpoint alır: yeni yazılan önek burasıdır.
    if _mark_last_block(messages[-1]):
        targets.append(len(messages) - 1)

    # Geriye doğru stride katlarına çıpalanmış sabit breakpoint'ler.
    anchor = (total // stride) * stride
    while len(targets) < limit and anchor > 0:
        idx = _message_at(ends, anchor)
        if idx is not None and idx not in targets and _mark_last_block(messages[idx]):
            targets.append(idx)
        anchor -= stride


def clear_breakpoints(messages: list[Message]) -> None:
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict):
                block.pop("cache_control", None)


def _message_at(ends: list[int], block_index: int) -> int | None:
    for i, end in enumerate(ends):
        if end >= block_index:
            return i
    return None


def _mark_last_block(msg: Message) -> bool:
    """Mesajın son bloğuna cache_control koyar. Metin içerikli mesaj alamaz."""
    content = msg.get("content")
    if not isinstance(content, list) or not content:
        return False
    last = content[-1]
    if not isinstance(last, dict):
        return False
    last["cache_control"] = EPHEMERAL
    return True


def prune_images(messages: list[Message], *, keep: int) -> None:
    """En yeni `keep` görüntü dışındaki tüm görüntüleri metinle değiştirir.

    Bir ekran görüntüsü kabaca 1.5k-4.8k token. Otuz adımlık bir görevde
    budamazsan bağlam yarı yolda dolar. Sondaki birkaç görüntü modelin
    "az önce ne gördüm" sorusuna cevap vermesi için yeterli.
    """
    if keep < 0:
        return

    holders = [
        (block, container)
        for msg in messages
        for block, container in _iter_image_blocks(msg)
    ]
    for block, container in holders[: max(0, len(holders) - keep)]:
        index = container.index(block)
        container[index] = {"type": "text", "text": IMAGE_PLACEHOLDER}


def prune_tool_payloads(
    messages: list[Message],
    *,
    cap: int = TRIM_TOOL_CHARS,
    keep: int = TRIM_KEEP_MESSAGES,
) -> None:
    """Eski araç yüklerini kısaltır: dev argümanlar ve şişkin sonuçlar.

    Son `keep` mesaj DOKUNULMAZ — model az önceki içeriğe atıf yapabilir.
    Daha eskisinde: tool_use girdilerindeki ve tool_result içeriklerindeki
    `cap`'i aşan metinler baş+son korunarak kısaltılır. Browser / fetch /
    dosya dump'ları için daha sıkı keep+cap uygulanır.
    """
    if cap <= 0:
        return

    def shorten(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        head = limit * 2 // 3
        tail = limit // 3
        note = TRIM_NOTE.format(gone=len(text) - head - tail)
        return text[:head] + note + text[-tail:]

    # Önce genel pencere.
    _prune_range(messages, end_keep=keep, cap=cap, shorten=shorten)
    # Ağır araçlar: daha kısa kuyruk + daha düşük tavan.
    _prune_range(
        messages,
        end_keep=TRIM_BROWSER_KEEP,
        cap=TRIM_BROWSER_CHARS,
        shorten=shorten,
        only_heavy=True,
    )


def _prune_range(
    messages: list[Message],
    *,
    end_keep: int,
    cap: int,
    shorten,
    only_heavy: bool = False,
) -> None:
    for msg in messages[: max(0, len(messages) - end_keep)]:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = str(block.get("name") or "")
                if only_heavy and name not in _HEAVY_TOOLS:
                    continue
                arguments = block.get("input")
                if isinstance(arguments, dict):
                    for key, value in arguments.items():
                        if isinstance(value, str) and len(value) > cap:
                            arguments[key] = shorten(value, cap)
            elif block.get("type") == "tool_result":
                if only_heavy and not _result_looks_heavy(block):
                    continue
                inner = block.get("content")
                if isinstance(inner, str) and len(inner) > cap:
                    block["content"] = shorten(inner, cap)
                elif isinstance(inner, list):
                    for sub in inner:
                        if (isinstance(sub, dict) and sub.get("type") == "text"
                                and isinstance(sub.get("text"), str)
                                and len(sub["text"]) > cap):
                            sub["text"] = shorten(sub["text"], cap)


def _result_looks_heavy(block: dict[str, Any]) -> bool:
    """tool_result'ta ad yok; HTML/DOM/URL ipuçlarıyla browser dump say."""
    inner = block.get("content")
    text = inner if isinstance(inner, str) else ""
    if isinstance(inner, list):
        parts = []
        for sub in inner:
            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                parts.append(sub["text"])
        text = "\n".join(parts)
    # Çok büyük dump'lar her zaman ağır sayılır.
    if len(text) > TRIM_TOOL_CHARS:
        return True
    head = text[:400].lower()
    return any(k in head for k in (
        "<html", "<!doctype", "http://", "https://", "konsol",
        "başarısız istek", "dom", "screenshot", "ekran",
    ))


def _iter_image_blocks(msg: Message):
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image":
            yield block, content
        elif block.get("type") == "tool_result":
            inner = block.get("content")
            if isinstance(inner, list):
                for sub in inner:
                    if isinstance(sub, dict) and sub.get("type") == "image":
                        yield sub, inner


def cache_report(usage: Any) -> dict[str, int]:
    """usage nesnesinden önbellek sağlığını çıkarır.

    read sürekli 0 kalıyorsa sessiz bir bozucu var: sistem promptunda
    değişen bir değer, oturum ortasında değişen araç listesi ya da
    20 bloğu aşan bir geri-bakış boşluğu.
    """
    get = (lambda k: getattr(usage, k, 0) or 0) if usage is not None else (lambda k: 0)
    read = get("cache_read_input_tokens")
    write = get("cache_creation_input_tokens")
    fresh = get("input_tokens")
    return {
        "cache_read": read,
        "cache_write": write,
        "uncached": fresh,
        "output": get("output_tokens"),
        # Gerçek prompt boyutu üçünün toplamıdır; input_tokens sadece artıktır.
        "prompt_total": read + write + fresh,
    }
