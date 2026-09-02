"""Append-only olay günlüğü.

Tek gerçek kaynak budur. Konuşma geçmişi, zihin durumu, denetim kaydı —
hepsi bu günlüğün bir projeksiyonu. Diske JSONL olarak yazılır; her satır
bağımsız çözülebilir, böylece süreç ortasında ölse bile kayıt tutarlı kalır.

İki olay ailesi var:

    kind="message"  API'ye giden bir konuşma turu (user/assistant/system).
                    content, API'nin beklediği blok yapısını birebir tutar —
                    thinking blokları dahil, değiştirilmeden geri gönderilmeli.

    kind="meta"     Modele gitmeyen kayıtlar: izin kararı, araç süresi,
                    hata, bağlam sıkıştırma işareti, kullanıcı kesmesi.
                    Denetim ve zihin görselleştirmesi bunları okur.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

MESSAGE = "message"
META = "meta"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# Zaman tek bir yerden okunuyor (bkz. recall/saat.py). Gece geçişi oturum
# günlüğündeki damgalara bakıyor — hangi düğüm hangisinden sonra dokunuldu,
# sürprizli olayın ±60 dakikası neresi — ve o damgalar duvar saatinden
# gelseydi doksan günlük bir senaryo ölçülemezdi.
Saat = Callable[[], str]


@dataclass(slots=True)
class Event:
    seq: int
    ts: str
    kind: str
    role: str | None = None
    content: Any = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> Event:
        return cls(**json.loads(line))

    @property
    def is_message(self) -> bool:
        return self.kind == MESSAGE


class EventLog:
    """Sürecin ömrü boyunca açık kalan, satır-tamponlu JSONL yazıcı."""

    def __init__(self, path: Path, *, saat: Saat | None = None) -> None:
        self.path = path
        self._saat: Saat = saat or utcnow
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[Event] = list(_read(path)) if path.exists() else []
        self._seq = self._events[-1].seq + 1 if self._events else 0
        self._lock = threading.Lock()
        self._fh = path.open("a", encoding="utf-8", buffering=1)
        self._listeners: list[Callable[[Event], None]] = []

    def subscribe(self, listener: Callable[[Event], None]) -> Callable[[], None]:
        """Yeni olayları dinler. Geri dönen çağrılabilir aboneliği iptal eder.

        Zihin arayüzü bunu kullanır: günlüğe yazılan her şey aynı anda
        tarayıcıya da akar. Dinleyicideki hata günlüğü yazmayı engellemez —
        arayüz çökerse ajan çalışmaya devam etmeli.
        """
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    # -- yazma ---------------------------------------------------------

    def append(
        self,
        kind: str,
        *,
        role: str | None = None,
        content: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> Event:
        """Olay ekler.

        meta bilinçli olarak **kwargs değil, açık bir sözlük: aksi halde
        "kind", "role", "content" adlı bir meta alanı bu fonksiyonun kendi
        parametreleriyle çakışır ve çağrı TypeError ile düşer. Zihin
        kayıtlarında "kind" gerçekten kullanılıyor.
        """
        with self._lock:
            ev = Event(
                seq=self._seq,
                ts=self._saat(),
                kind=kind,
                role=role,
                content=content,
                meta=dict(meta or {}),
            )
            self._seq += 1
            self._events.append(ev)
            self._fh.write(ev.to_json() + "\n")
            # Kesme/çökme anında son turun kaybolmaması için diske indir.
            self._fh.flush()
            os.fsync(self._fh.fileno())

        for listener in tuple(self._listeners):
            try:
                listener(ev)
            except Exception:  # arayüz çökerse ajan çalışmaya devam etmeli
                pass
        return ev

    def message(self, role: str, content: Any, **meta: Any) -> Event:
        return self.append(MESSAGE, role=role, content=content, meta=meta)

    def note(self, event_type: str, **data: Any) -> Event:
        return self.append(META, content=event_type, meta=data)

    # -- okuma ---------------------------------------------------------

    def __iter__(self) -> Iterator[Event]:
        return iter(tuple(self._events))

    def __len__(self) -> int:
        return len(self._events)

    def messages(self) -> list[Event]:
        return [e for e in self._events if e.is_message]

    def notes(self, event_type: str | None = None) -> list[Event]:
        out = [e for e in self._events if e.kind == META]
        if event_type is not None:
            out = [e for e in out if e.content == event_type]
        return out

    def tail(self, n: int) -> list[Event]:
        return list(self._events[-n:])

    def close(self) -> None:
        with self._lock:
            if not self._fh.closed:
                self._fh.close()

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _read(path: Path) -> Iterator[Event]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield Event.from_json(line)
            except (json.JSONDecodeError, TypeError) as exc:
                # Yarım yazılmış son satır: süreç yazarken öldürülmüş olabilir.
                # Sessizce atla, ama gürültüsüzce de geçme.
                raise ValueError(f"{path}:{lineno} bozuk olay kaydı: {exc}") from exc
