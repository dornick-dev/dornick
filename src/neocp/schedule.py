"""Zamanlanmış görevler.

"Her sabah borsayı kontrol et", "cuma günleri raporu hazırla" — bunlar
ajanın kendi kendine yapabileceği işler ama birinin saati tutması gerekiyor.
Burası o saat.

Tasarımın üç kararı:

    görünür    Görevler diskte düz JSON olarak duruyor ve ayar sayfasında
               listeleniyor. Ajanın kurduğu bir otomasyonun kullanıcıdan
               gizli çalışması kabul edilemez — ne olduğunu, ne zaman
               çalıştığını ve en son ne olduğunu görebilmeli.
    arka plan  Zamanı gelen görev sohbet balonu değil: arka plan yardımcı
               olarak koşuyor. Rapor Orkestra / Görevler'de; tıklanınca
               Viewer. Ana sohbet Q&A alanı kalıyor.
    sessiz     Biten zamanlı iş ana ajanı "haber ver" turuna zorlamaz —
               kullanıcı sormadıkça sohbete dökülmez.

Cron sözdizimi bilinçli olarak yok. Beş yıldızlı ifadeyi doğru yazmak
kullanıcının işi değil; "her N dakikada" ve "her gün saat HH:MM" pratikte
istenen her şeyi karşılıyor ve ikisi de tek bakışta okunuyor.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as clock, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

TASKS_FILE = "tasks.json"

# İki tekrar biçimi. Cron ifadesi yerine bunlar: okunması ve doğrulanması
# kolay, ve pratikte istenen her şeyi karşılıyor.
KINDS = ("every", "daily")

# Bir görev bundan sık çalışamaz. Dakikada bir tetiklenen bir ajan turu hem
# maliyet hem gürültü.
MIN_INTERVAL_S = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Task:
    """Tek bir zamanlanmış iş.

    prompt: ajana gönderilecek metin. Kullanıcının yazdığı bir mesajdan farkı
        yok — o yüzden eksiksiz olmalı, "yine yap" gibi bir şey işe yaramaz.
    at: `daily` için "HH:MM" (yerel saat). `every` için kullanılmıyor.
    every_s: `every` için saniye.
    """

    id: str
    title: str
    prompt: str
    kind: str = "every"
    every_s: int = 3600
    at: str = "09:00"
    enabled: bool = True
    created: str = field(default_factory=lambda: _now().isoformat(timespec="seconds"))
    last_run: str = ""
    last_status: str = ""
    # Son (veya koşan) yardımcının kimliği — detayda "raporu aç" / durum.
    last_child_id: str = ""
    # Bir sonraki tetiklenme; kaydedilmesi şart, yoksa program her açıldığında
    # geçmiş görevler yeniden tetikleniyor.
    next_run: str = ""
    # Arayüz tipi: simple = tek prompt; automation = workflow grafiği.
    kind_ui: str = "simple"  # simple | automation
    # kind_ui=automation iken bağlı iş akışı kimliği; simple'da boş.
    workflow_id: str = ""

    def describe(self) -> str:
        if self.kind == "daily":
            return f"her gün {self.at}"
        if self.every_s % 3600 == 0:
            return f"her {self.every_s // 3600} saatte"
        return f"her {max(1, self.every_s // 60)} dakikada"


def validate(task: Task) -> Task:
    """Bozuk bir görev sessizce hiç çalışmayan bir görevdir."""
    if task.kind not in KINDS:
        raise ValueError(f"Bilinmeyen tekrar biçimi: {task.kind}. Geçerli: {', '.join(KINDS)}")
    # İki görev türünün taşıyıcı alanı farklı: basit görevde prompt, otomasyonda
    # akış kimliği. Otomasyondan da prompt istemek, çağıranı `prompt="."` gibi
    # anlamsız bir değer uydurmaya itiyordu — ve o değer, akış bir gün
    # bulunamazsa koşucunun sessizce "." promptunu işletmesi demekti.
    if task.kind_ui == "automation":
        if not task.workflow_id.strip():
            raise ValueError("Otomasyon görevi bir akış kimliği (workflow_id) ister.")
    elif not task.prompt.strip():
        raise ValueError("Boş görev metni. Ajana ne söyleneceğini yaz.")
    if task.kind == "every" and task.every_s < MIN_INTERVAL_S:
        raise ValueError(f"En sık {MIN_INTERVAL_S} saniyede bir çalışabilir.")
    if task.kind == "daily":
        _parse_clock(task.at)
    return task


def _parse_clock(text: str) -> clock:
    try:
        hour, minute = (int(p) for p in str(text).split(":", 1))
        return clock(hour=hour, minute=minute)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Saat 'HH:MM' biçiminde olmalı: {text!r}") from exc


def next_after(task: Task, moment: datetime) -> datetime:
    """Verilen andan sonraki ilk tetiklenme.

    `daily` yerel saate göre hesaplanıyor: kullanıcı "sabah 9" derken UTC
    değil kendi saatini kastediyor.
    """
    if task.kind == "every":
        return moment + timedelta(seconds=max(MIN_INTERVAL_S, task.every_s))

    wanted = _parse_clock(task.at)
    local = moment.astimezone()
    target = local.replace(hour=wanted.hour, minute=wanted.minute, second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


class Schedule:
    """Görev listesinin sahibi.

    Hem arayüz thread'inden hem ajanın döngüsünden okunuyor; bu yüzden
    kilitli ve her değişiklikte diske yazıyor. Liste kısa (onlarca görev),
    yazma maliyeti önemsiz.
    """

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / TASKS_FILE
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._load()

    # -- okuma ---------------------------------------------------------

    def all(self) -> list[Task]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: (not t.enabled, t.next_run or "~"))

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def overdue(self, moment: datetime | None = None) -> list[Task]:
        """Zamanı geçmiş görevler — `next_run` İLERLETİLMEZ.

        Program kapalıyken kaçırılan tetiklenmeleri göstermek için: kullanıcı
        "şimdi yap / atla" demeden defterdeki sıra değişmemeli.
        """
        moment = moment or _now()
        with self._lock:
            ripe = [
                task for task in self._tasks.values()
                if task.enabled and task.next_run
                and datetime.fromisoformat(task.next_run) <= moment
            ]
        return sorted(ripe, key=lambda t: t.next_run or "")

    def due(
        self,
        moment: datetime | None = None,
        *,
        only: Iterable[str] | None = None,
    ) -> list[Task]:
        """Zamanı gelmiş görevler. Sıradaki zamanları da ilerletiliyor.

        İlerletme burada yapılıyor, çalıştırıldıktan sonra değil: iş uzun
        sürerse aynı görev ikinci kez tetiklenmemeli.

        `only`: yalnızca bu kimlikler (açılışta kaçırılanlar için).
        """
        moment = moment or _now()
        want = set(only) if only is not None else None
        fired: list[Task] = []

        with self._lock:
            for task in self._tasks.values():
                if want is not None and task.id not in want:
                    continue
                if not task.enabled or not task.next_run:
                    continue
                if datetime.fromisoformat(task.next_run) > moment:
                    continue
                task.next_run = next_after(task, moment).isoformat(timespec="seconds")
                fired.append(task)
            if fired:
                self._write()
        return fired

    def skip_occurrence(self, task_id: str, moment: datetime | None = None) -> bool:
        """Bu tetiklenmeyi koşmadan atla; bir sonraki slota geç."""
        moment = moment or _now()
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or not task.enabled or not task.next_run:
                return False
            if datetime.fromisoformat(task.next_run) > moment:
                return False
            task.next_run = next_after(task, moment).isoformat(timespec="seconds")
            task.last_status = "atlandı"
            self._write()
        return True

    # -- yazma ---------------------------------------------------------

    def add(self, task: Task) -> Task:
        validate(task)
        task.id = task.id or f"job_{uuid4().hex[:8]}"
        task.next_run = next_after(task, _now()).isoformat(timespec="seconds")
        with self._lock:
            self._tasks[task.id] = task
            self._write()
        return task

    def update(self, task_id: str, **changes: Any) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None

            known = set(Task.__dataclass_fields__)
            for name, value in changes.items():
                if name in known and name != "id":
                    setattr(task, name, value)
            validate(task)

            # Zamanlama değiştiyse sıradaki an da değişmeli; yoksa yeni
            # ayar bir sonraki tetiklenmeye kadar geçersiz kalıyor.
            if {"kind", "every_s", "at", "enabled"} & set(changes):
                task.next_run = next_after(task, _now()).isoformat(timespec="seconds")

            self._write()
            return task

    def remove(self, task_id: str) -> bool:
        with self._lock:
            gone = self._tasks.pop(task_id, None) is not None
            if gone:
                self._write()
        return gone

    def note_run(self, task_id: str, status: str) -> None:
        with self._lock:
            if task := self._tasks.get(task_id):
                task.last_run = _now().isoformat(timespec="seconds")
                task.last_status = status[:200]
                self._write()

    def mark_running(self, task_id: str, child_id: str) -> None:
        """Görev arka plan yardımcıya bağlandı — detay paneli 'koşuyor' görsün."""
        with self._lock:
            if task := self._tasks.get(task_id):
                task.last_child_id = str(child_id or "")
                task.last_run = _now().isoformat(timespec="seconds")
                task.last_status = "koşuyor"
                self._write()

    # -- disk ----------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        known = set(Task.__dataclass_fields__)
        for entry in raw if isinstance(raw, list) else []:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            # Bilinmeyen alanları atmak, elle düzenlenmiş bir dosyanın
            # programı açılmaz hale getirmesini engelliyor.
            self._tasks[entry["id"]] = Task(**{k: v for k, v in entry.items() if k in known})

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(t) for t in self._tasks.values()], ensure_ascii=False, indent=2)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(payload, encoding="utf-8")
        temp.replace(self.path)


async def run_forever(
    schedule: Schedule,
    submit: Callable[[Task], None],
    *,
    tick_s: float = 20.0,
    sleep: Callable[[float], Any] | None = None,
    paused: Callable[[], bool] | None = None,
) -> None:
    """Zamanı gelen görevleri `submit` ile başlatır (arka plan yardımcı).

    Eski yol sohbet kuyruğuydu; artık `submit` köprüde `run_scheduled`
    olmalı — çıktı sohbete değil Orkestra'ya düşer.

    `paused`: True iken tetikleme yapılmaz — açılışta kaçırılan görevler
    kullanıcı "şimdi yap / atla" demeden bekletilir.
    """
    import asyncio

    naptime = sleep or asyncio.sleep
    while True:
        if not (paused and paused()):
            for task in schedule.due():
                try:
                    submit(task)
                except Exception:  # tek bir görev zamanlayıcıyı düşürmemeli
                    schedule.note_run(task.id, "başlatılamadı")
        await naptime(tick_s)


def payload(tasks: Iterable[Task]) -> list[dict[str, Any]]:
    """Arayüze giden hal: okunabilir tarif de ekli."""
    return [{**asdict(task), "describe": task.describe()} for task in tasks]
