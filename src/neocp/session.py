"""Oturum: olay günlüğünü API mesaj listesine projekte eder.

API durumsuzdur — her turda tüm geçmiş yeniden gönderilir. "Hafıza" diye bir
şey yok; burada tutulan liste var. Bu sınıf o listenin tek sahibidir.

İki katı API kuralı burada zorlanır:

  1. Bir asistan turundaki *tüm* tool_use bloklarının karşılığı *tek bir*
     kullanıcı mesajında dönmeli. Birden fazla mesaja bölmek modeli sessizce
     paralel araç çağırmamaya eğitir.
  2. Hiçbir tool_use karşılıksız kalamaz. Kalırsa bir sonraki istek 400 alır.
     Kesme (ESC) durumunda bile iptal sonucu enjekte edilmek zorunda.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import compaction
from .events import Event, EventLog

Block = dict[str, Any]

# Bağlam sıkıştırmasının bıraktığı işaret. Mesaj projeksiyonu buradan
# başlar; günlüğün kendisi dokunulmadan kalır.
HORIZON = "context_reset"


@dataclass(slots=True)
class PendingToolUse:
    id: str
    name: str
    input: dict[str, Any]


class Session:
    def __init__(self, log: EventLog, session_id: str) -> None:
        self.log = log
        self.id = session_id

    # -- fabrika -------------------------------------------------------

    @classmethod
    def create(cls, sessions_dir: Path) -> Session:
        base = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # Kimlik saniye çözünürlüklü: aynı saniyede iki oturum açılırsa
        # (ör. yeni konuşma butonu, açılıştan hemen sonra) ikisi aynı dosyaya
        # yazardı ve "yeni" konuşma eskisinin üstüne binerdi. Çakışmada kısa
        # bir sonek ekleniyor — biçim bozulmuyor, benzersizlik garanti.
        session_id = base
        for suffix in range(1, 100):
            if not (sessions_dir / f"{session_id}.jsonl").exists():
                break
            session_id = f"{base[:-1]}-{suffix}Z"
        path = sessions_dir / f"{session_id}.jsonl"
        log = EventLog(path)
        log.note("session_start", session_id=session_id)
        return cls(log, session_id)

    @classmethod
    def resume(cls, path: Path) -> Session:
        log = EventLog(path)
        log.note("session_resume")
        return cls(log, path.stem)

    @classmethod
    def latest(cls, sessions_dir: Path) -> Session | None:
        files = sorted(sessions_dir.glob("*.jsonl"))
        return cls.resume(files[-1]) if files else None

    # -- yazma ---------------------------------------------------------

    def add_user_text(self, text: str) -> None:
        self.log.message("user", [{"type": "text", "text": text}])

    def add_user_blocks(self, blocks: list[Block], *, internal: bool = False) -> None:
        """Kullanıcı turuna blok ekler.

        `internal`, kullanıcının yazmadığı turlar için: araçtan gelen bir
        görüntü ya da harness'ın eklediği bir not. Arayüz bunları sohbette
        göstermiyor — kullanıcının yazmadığı bir metin cevap gibi duruyor.
        """
        self.log.message("user", blocks, internal=internal)

    def add_assistant(self, content: Iterable[Any], **meta: Any) -> None:
        """API yanıtının content'ini olduğu gibi saklar.

        Thinking blokları dahil hiçbir blok düzenlenmez — API değiştirilmiş
        blokları reddeder ve aynı modelde devam ederken hepsi geri gitmeli.
        """
        self.log.message("assistant", blocks_to_dicts(content), **meta)

    def add_tool_results(self, results: list[Block]) -> None:
        """Tüm araç sonuçlarını TEK bir kullanıcı mesajı olarak ekler."""
        if not results:
            return
        self.log.message("user", results, tool_results=True)

    def add_system_note(self, text: str) -> None:
        """Konuşma ortası operatör yönergesi.

        messages[] içine role="system" olarak gider (Opus 4.8). Üstteki system
        alanını düzenlemek yerine bunu kullanmak önbelleği korur ve kanal
        taklit edilemez: kullanıcı içeriğine gömülü metin sahtelenebilir,
        role="system" edilemez.

        Kısıt: ilk mesaj olamaz ve bir user mesajını takip etmeli.
        """
        if not self._can_take_system_note():
            self.log.note("system_note_skipped", text=text)
            return
        self.log.message("system", text)

    def add_continuation_note(self, text: str) -> None:
        """Tavana çarpmış bir yanıtı sürdürmesi için dürtü.

        `add_system_note` burada kullanılamıyor: system notu bir user
        mesajını takip etmek zorunda, oysa kesilen turdan sonra sondaki mesaj
        asistanın kendisi. Bu yüzden user kanalından gidiyor.

        `continuation` işareti arayüz için: kullanıcının yazmadığı bir mesaj
        sohbette kullanıcı mesajı gibi görünmemeli.
        """
        self.log.message("user", [{"type": "text", "text": text}], continuation=True)

    # -- okuma ---------------------------------------------------------

    def messages(self) -> list[dict[str, Any]]:
        """API'ye gidecek mesaj listesi.

        Günlük hiçbir zaman kısaltılmıyor — sıkıştırma yalnızca bir ufuk
        işareti bırakıyor ve bu projeksiyon oradan başlıyor. Ham gerçek
        diskte durmaya devam ediyor: geçmiş oturum özeti çıkarmak, hata
        aramak ve zihni yeniden örmek hep o dosyadan yapılıyor.
        """
        horizon = self._horizon()
        if horizon is None:
            return [{"role": e.role, "content": e.content} for e in self.log.messages()]

        return [
            compaction.carry_over(str(horizon.meta.get("summary", ""))),
            *(
                {"role": e.role, "content": e.content}
                for e in self.log.messages()
                if e.seq >= int(horizon.meta.get("from_seq", 0))
            ),
        ]

    def _horizon(self) -> Event | None:
        """En son bağlam sıkıştırması. Yoksa pencere oturumun başından açık."""
        marks = self.log.notes(HORIZON)
        return marks[-1] if marks else None

    def _live_events(self) -> list[Event]:
        """Şu anki pencerede duran mesaj olayları."""
        events = self.log.messages()
        if (horizon := self._horizon()) is None:
            return events
        floor = int(horizon.meta.get("from_seq", 0))
        return [e for e in events if e.seq >= floor]

    # -- sıkıştırma ----------------------------------------------------

    def compaction_plan(self, *, keep: int = compaction.KEEP_MESSAGES) -> tuple[int, str] | None:
        """Neyin özetleneceğini hazırlar: (ilk kalan mesajın seq'i, döküm).

        None dönerse güvenli bir kesme noktası yok — pencerede henüz
        kesilebilecek kadar tamamlanmış tur birikmemiş demektir.
        """
        events = self._live_events()
        projected = [{"role": e.role, "content": e.content} for e in events]
        cut = compaction.cut_point(projected, keep=keep)
        if cut <= 0:
            return None
        return events[cut].seq, compaction.transcript(projected[:cut])

    def compact(self, summary: str, from_seq: int) -> None:
        """Pencereyi özetin arkasına alır.

        Silme yok: yalnızca projeksiyonun nereden başlayacağı işaretleniyor.
        """
        self.log.note(HORIZON, summary=summary, from_seq=from_seq)

    def pending_tool_uses(self) -> list[PendingToolUse]:
        """Karşılığı henüz dönmemiş tool_use blokları.

        Son asistan turuna bakar; ardından gelen kullanıcı turunda hangi
        tool_use_id'lerin karşılandığını çıkarır. Kesme sonrası eksik olanlara
        iptal sonucu üretmek için kullanılır.
        """
        msgs = self.log.messages()
        if not msgs:
            return []

        last_assistant = next((e for e in reversed(msgs) if e.role == "assistant"), None)
        if last_assistant is None:
            return []

        requested = [
            PendingToolUse(id=b["id"], name=b["name"], input=b.get("input") or {})
            for b in last_assistant.content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if not requested:
            return []

        answered: set[str] = set()
        for e in msgs:
            if e.seq <= last_assistant.seq or e.role != "user":
                continue
            for b in e.content if isinstance(e.content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    answered.add(b.get("tool_use_id", ""))

        return [t for t in requested if t.id not in answered]

    def block_count(self) -> int:
        total = 0
        for e in self.log.messages():
            total += len(e.content) if isinstance(e.content, list) else 1
        return total

    def _can_take_system_note(self) -> bool:
        msgs = self._live_events()
        return bool(msgs) and msgs[-1].role == "user"

    def close(self) -> None:
        self.log.note("session_end")
        self.log.close()


def blocks_to_dicts(content: Iterable[Any]) -> list[Block]:
    """SDK blok nesnelerini API'ye geri gönderilebilir sözlüklere çevirir."""
    out: list[Block] = []
    for block in content:
        if isinstance(block, dict):
            out.append(block)
        elif hasattr(block, "model_dump"):
            out.append(block.model_dump(exclude_none=True))
        else:
            raise TypeError(f"Beklenmeyen içerik bloğu: {type(block).__name__}")
    return out


def cancelled_result(tool_use_id: str, reason: str = "Kullanıcı işlemi kesti.") -> Block:
    """Kesme sonrası karşılıksız kalan tool_use için zorunlu iptal sonucu."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": reason,
        "is_error": True,
    }
