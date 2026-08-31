"""Zihin deposu.

Dört yüzey:

    semantik    öğrenilen bilgiler, tercihler, dersler   -> memories.jsonl
    prosedürel  işe yarayan yordamlar (kind="procedure")  -> memories.jsonl
    çalışma     hedef yığını                              -> goals.jsonl
    epizodik    geçmiş oturumların olay günlükleri        -> sessions/*.jsonl

Epizodik belleğin ayrı bir deposu yok — oturum günlükleri zaten odur. Zihin
onların üzerine bir arama yüzeyi geçirir. Bu, olay günlüğünü tek gerçek kaynak
tutma kararının doğrudan getirisi.

Yazma biçimi her yerde append-only JSONL: aynı id'ye sahip sonraki kayıt
öncekini geçersiz kılar. Silme diye bir şey yok, tombstone var — zihnin
neyi ne zaman unuttuğu da zihnin bir parçası.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from ..recall import Step, open_store
from .search import Scored, excerpt, rank

# "episode" digerlerinden farkli: onu ajan elle yazmiyor, baglam
# sikistirmasi yaziyor. Ruha girmiyor (soul() turleri tek tek seciyor)
# ama cagrisimla geri gelebiliyor — sikistirmanin kalici olma sebebi bu.
MEMORY_KINDS = ("fact", "preference", "lesson", "procedure", "user", "voice", "episode")
GOAL_STATES = ("active", "done", "dropped")

# Ruh özetine girecek azami kayıt sayısı (tür başına). Ruh sistem promptunun
# parçası; sınırsız büyürse her oturum daha pahalı başlar.
SOUL_LIMIT = 8

# Epizodik aramada taranacak azami oturum sayısı. Günlükler büyüdükçe
# burası bir indeksle değiştirilir.
MAX_SCANNED_SESSIONS = 60


def _now() -> str:
    # Milisaniye çözünürlük: aynı saniye içinde yazılan iki kaydın sırası
    # kaybolmasın (tazelik sıralaması buna bakıyor).
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


@dataclass(slots=True)
class Memory:
    id: str
    ts: str
    kind: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    session_id: str = ""
    deleted: bool = False

    def searchable(self) -> str:
        return f"{self.title}\n{self.content}\n{' '.join(self.tags)}"

    def render(self) -> str:
        tags = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"({self.kind}) {self.title}{tags}\n{self.content}"


@dataclass(slots=True)
class Goal:
    id: str
    ts: str
    text: str
    status: str = "active"
    session_id: str = ""
    note: str = ""


@dataclass(slots=True)
class Soul:
    """Oturumlar arasında hayatta kalan kimlik.

    Diskte duran zihinden türetilir ve oturum başında sistem promptuna
    yerleşir. Ajanın "ben kimim, bu kullanıcı kim, şimdiye kadar ne öğrendim"
    sorusuna, hiçbir araç çağırmadan sahip olduğu cevap.

    Yordamların yalnızca başlıkları girer — detay `mind_recall` ile gelir.
    Her şeyi prompta yığmak kademeli açığa çıkarmanın tersidir ve her oturumu
    gereksiz pahalı başlatır.
    """

    persona: str
    user: list[Memory]
    preferences: list[Memory]
    lessons: list[Memory]
    voice: list[Memory]
    procedures: list[Memory]
    goals: list[Goal]
    sessions: int
    first_seen: str

    @property
    def is_blank(self) -> bool:
        return not any(
            (self.persona, self.user, self.preferences, self.lessons, self.voice,
             self.procedures, self.goals)
        )

    def render(self) -> str:
        if self.is_blank:
            # İlk karşılaşma yönergesi buraya, IDENTITY'ye değil: kalıcı
            # kimliğe yazılsaydı yüzüncü oturumda da "tanışalım" derdi.
            # Ruh dolduğu anda bu blok kendiliğinden düşüyor.
            return (
                "Bu kullanıcıyla ilk kez karşılaşıyorsun; diskteki zihnin henüz "
                "boş. Bu bir eksiklik değil, bir başlangıç — tanışmaya istekli "
                "ol.\n\n"
                "İlk konuşmada:\n"
                "- Kısa ve kendinden emin ol: kendini bir cümleyle tanıt, ne "
                "işe yaradığını bir iki somut örnekle söyle ve dur. Yetenek ya "
                "da donanım envanteri sayma; eksik duyularından (mikrofon, "
                "kamera, ses) kendiliğinden hiç söz etme.\n"
                "- En fazla tek doğal soru sor: adını — o da zaten "
                "söylemediyse (\"adın ne?\" yeter, hitap kalıbı sorulmaz). "
                "Söylenmiş bilgiyi yeniden sorma. Adını öğrenince "
                "`mind_memory` ile kaydet (kind=user); ikinci oturumda ona "
                "adıyla hitap edebilmelisin.\n"
                "- Ne üzerinde çalıştığını, seni ne için kullanmak istediğini "
                "zamanla öğren — sorgu listesi gibi değil.\n\n"
                "Kaydettiğin, kullanıcının söylediği olsun — senin tahminin "
                "değil. Sistem promptunda zaten yazan (çalışma alanı, tarih, "
                "işletim sistemi) hatıra değildir; onlar her oturumda hazır."
            )

        parts = [self._history_line()]
        if self.persona:
            parts.append(self.persona)

        # Konuşma biçimi en başta: cevabın tonunu belirleyen şey, cevabın
        # içeriğinden önce okunmalı.
        if self.voice:
            parts.append(
                "Bu kullanıcıyla nasıl konuştuğun:\n"
                + "\n".join(f"- {m.content}" for m in self.voice)
            )

        for title, items in (
            ("Kullanıcı hakkında bildiklerin", self.user),
            ("Kullanıcının tercihleri", self.preferences),
            ("Çıkardığın dersler", self.lessons),
        ):
            if items:
                parts.append(f"{title}:\n" + "\n".join(f"- {m.content}" for m in items))

        if self.procedures:
            titles = "\n".join(f"- {m.title}" for m in self.procedures)
            parts.append(
                f"Bildiğin yordamlar (detay için mind_recall):\n{titles}"
            )

        if self.goals:
            parts.append(
                "Önceki oturumlardan kalan açık hedefler:\n"
                + "\n".join(f"- [{g.id}] {g.text}" for g in self.goals)
            )

        return "\n\n".join(parts)

    def _history_line(self) -> str:
        if self.sessions <= 1:
            return "Aşağıdakiler diskteki zihninden geliyor — önceki oturumlarda öğrendiklerin."
        since = self.first_seen[:10] if self.first_seen else "bir süredir"
        return (
            f"Aşağıdakiler diskteki zihninden geliyor: {self.sessions} oturumdur "
            f"({since} tarihinden beri) bu kullanıcıyla çalışıyorsun."
        )


@dataclass(slots=True)
class Episode:
    session_id: str
    started: str
    turns: int
    tools: list[str]
    digest: str
    # Bir alt ajanın (yardımcının) oturumu mu? Yardımcı günlüğünün başında
    # `subagent_start(parent=...)` notu var; sohbet listesi bunları saklıyor —
    # kullanıcının konuşma geçmişi kendi konuşmaları, yardımcıların ara
    # işleri değil.
    child: bool = False

    def searchable(self) -> str:
        return f"{self.digest}\n{' '.join(self.tools)}"


class Mind:
    def __init__(self, mind_dir: Path, sessions_dir: Path, session_id: str = "") -> None:
        self.dir = mind_dir
        self.sessions_dir = sessions_dir
        self.session_id = session_id
        self.dir.mkdir(parents=True, exist_ok=True)

        self._goals: dict[str, Goal] = {}
        self._episode_cache: dict[str, tuple[int, Episode]] = {}
        self._lock = threading.Lock()

        # Hatıralar indeksli depoda: arama tarama değil, indeks araması.
        # Hedefler JSONL kalıyor — sayıları sınırlı, taramanın maliyeti yok.
        self.store = open_store(self.dir)
        self.last_trace: list[Step] = []
        self._migrate_jsonl()
        # Diskteki imzalar daha ilk mesaj gelmeden arka planda RAM'e
        # alınıyor: ilk hatırlama indeks kurulumunu beklememeli.
        self.store.warm()

        _load(self.dir / "goals.jsonl", Goal, self._goals)

    def _migrate_jsonl(self) -> None:
        """Eski memories.jsonl kayıtlarını bir kez indeksli depoya taşır."""
        legacy = self.dir / "memories.jsonl"
        if not legacy.exists() or self.store.count():
            return
        old: dict[str, Memory] = {}
        _load(legacy, Memory, old)
        for memory in old.values():
            if memory.deleted:
                continue
            self.store.remember(
                memory.content,
                kind=memory.kind,
                title=memory.title,
                tags=memory.tags,
                session=memory.session_id,
            )
        legacy.rename(legacy.with_suffix(".jsonl.migrated"))

    # -- semantik / prosedürel ----------------------------------------

    def remember(
        self,
        content: str,
        *,
        kind: str = "fact",
        title: str = "",
        tags: Iterable[str] = (),
    ) -> Memory:
        if kind not in MEMORY_KINDS:
            raise ValueError(f"Bilinmeyen bellek türü: {kind}")
        node = self.store.remember(
            content,
            kind=kind,
            title=title,
            tags=tags,
            session=self.session_id,
        )
        return _from_node(node)

    def bridge(self, src: str, dst: str, reason: str = "") -> tuple[Memory, Memory] | None:
        """İki hatırayı bilinçli olarak birbirine bağlar.

        Otomatik örgü (`_weave`) içerik benzerliğine bakıyor — "bunlar
        birbirine benziyor" diyor. Buradaki bağ farklı: **neden** bağlı
        olduğunu ajan söylüyor ve o gerekçe kenarda duruyor.

        Fark pratikte şu: "dün 3,71M, bugün 3,72M" iki ayrı kayıt olarak
        birbirine benzemiyor bile olabilir, ama "aynı ölçümün bir sonraki
        günü" diye bağlanınca zaman dizisi oluşuyor ve çağrışım o zinciri
        yürüyebiliyor.
        """
        first, second = self.store.peek(src), self.store.peek(dst)
        if first is None or second is None:
            return None
        self.store.link(src, dst, weight=1.0, reason=reason.strip() or "ajan bağladı")
        return _from_node(first), _from_node(second)

    def series(self, tag: str, *, limit: int = 20) -> list[Memory]:
        """Aynı etiketi taşıyan kayıtlar, eskiden yeniye.

        Bir ölçümün zaman içindeki hali: "btc-fiyat" etiketiyle kaydedilen
        her gözlem sırasıyla geliyor. "Dünden bugüne ne oldu" sorusunun
        cevabı bu — tek tek hatırlayıp kafadan sıralamak değil.
        """
        wanted = tag.strip().lower()
        if not wanted:
            return []
        found = [
            _from_node(node)
            for node in self.store.by_kind_any(limit=500)
            if wanted in [t.lower() for t in node.tags]
        ]
        found.sort(key=lambda m: m.ts)
        return found[-limit:]

    def forget(self, memory_id: str) -> Memory | None:
        node = self.store.peek(memory_id)
        if node is None or not self.store.forget(memory_id):
            return None
        return _from_node(node, deleted=True)

    def memories(self, kind: str | None = None) -> list[Memory]:
        kinds = [kind] if kind else list(MEMORY_KINDS)
        out: list[Memory] = []
        for k in kinds:
            out.extend(_from_node(n) for n in self.store.by_kind(k, limit=200))
        return sorted(out, key=lambda m: m.ts, reverse=True)

    def recall(self, query: str, *, kind: str | None = None, limit: int = 8) -> list[Scored]:
        """İndeksten tohumlanır, bağlar üzerinden yayılır.

        Aktivasyonun uğradığı yol `last_trace` içinde kalıyor; araç katmanı
        onu olay günlüğüne yazınca arayüz hatırlamayı canlandırabiliyor.
        """
        recollection = self.store.recall(query, limit=limit * 2)
        self.last_trace = recollection.trace

        hits = [n for n in recollection.hits if not kind or n.kind == kind][:limit]
        activation = {step.node: step.activation for step in recollection.trace}
        return [
            Scored(item=_from_node(node), score=activation.get(node.id, 0.0), matched=[])
            for node in hits
        ]

    # -- çalışma belleği ----------------------------------------------

    def push_goal(self, text: str) -> Goal:
        goal = Goal(id=_new_id("goal"), ts=_now(), text=text.strip(), session_id=self.session_id)
        self._write("goals.jsonl", goal)
        self._goals[goal.id] = goal
        return goal

    def set_goal_status(self, goal_id: str, status: str, note: str = "") -> Goal | None:
        if status not in GOAL_STATES:
            raise ValueError(f"Bilinmeyen hedef durumu: {status}")
        goal = self._goals.get(goal_id)
        if goal is None:
            return None
        updated = Goal(**{**asdict(goal), "status": status, "ts": _now(), "note": note})
        self._write("goals.jsonl", updated)
        self._goals[goal_id] = updated
        return updated

    def goals(self, *, active_only: bool = True, all_sessions: bool = False) -> list[Goal]:
        """Hedef defteri SOHBETİN defteridir, zihnin değil.

        Canlı yara: PDF sohbetinin sonunda ajan başka sohbette açılmış "ev
        otomasyonu" hedefini görüp onun muhabbetini yapıyordu — kabul kapısı
        da alakasız sohbetlerin maddeleriyle "bitti mi" pazarlığına giriyordu.
        Varsayılan görünüm aktif oturuma süzülür; beyin grafiği gibi zihnin
        tamamına bakan yerler `all_sessions=True` ister.
        """
        items = list(self._goals.values())
        if active_only:
            items = [g for g in items if g.status == "active"]
        if not all_sessions:
            items = [g for g in items if g.session_id == self.session_id]
        return sorted(items, key=lambda g: g.ts)

    def goal_digest(self) -> str:
        """Aktif hedeflerin tek satırlık özeti.

        Ajan bunu operatör kanalından (role="system") geri alır; böylece
        uzun bir görevin ortasında ne yapmaya çalıştığını unutmaz.
        """
        active = self.goals()
        if not active:
            return ""
        lines = [f"{i}. {g.text}" for i, g in enumerate(active, 1)]
        return "Aktif hedefler:\n" + "\n".join(lines)

    # -- ruh -----------------------------------------------------------

    def soul(self, persona: str = "", limit: int = SOUL_LIMIT) -> Soul:
        """Oturum başında yüklenen kimlik özeti.

        Ajan bunu bir araç çağırarak değil, hazır bulur — kim olduğunu
        hatırlamak için önce "hatırlamayı düşünmesi" gerekmemeli.
        """
        return Soul(
            persona=persona.strip(),
            user=self.memories("user")[:limit],
            preferences=self.memories("preference")[:limit],
            lessons=self.memories("lesson")[:limit],
            voice=self.memories("voice")[:limit],
            procedures=self.memories("procedure")[:limit],
            goals=self.goals(),
            sessions=self._session_count(),
            first_seen=self._first_seen(),
        )

    def _session_count(self) -> int:
        if not self.sessions_dir.is_dir():
            return 0
        return sum(1 for _ in self.sessions_dir.glob("*.jsonl"))

    def _first_seen(self) -> str:
        stems = sorted(p.stem for p in self.sessions_dir.glob("*.jsonl")) if self.sessions_dir.is_dir() else []
        if stems:
            return _stem_to_date(stems[0])
        oldest = min((m.ts for m in self.memories()), default="")
        return oldest[:10]

    # -- epizodik ------------------------------------------------------

    def episodes(self, query: str, *, limit: int = 5, include_current: bool = False) -> list[Scored]:
        """Geçmiş oturumlarda arama.

        Mevcut oturum varsayılan olarak dışarıda: o zaten bağlamda, tekrar
        getirmek token harcamaktan başka bir işe yaramaz.
        """
        pool = [
            ep
            for ep in self._scan_sessions()
            if include_current or ep.session_id != self.session_id
        ]
        return rank(
            query,
            pool,
            text_of=lambda e: e.searchable(),
            time_of=lambda e: e.started,
            limit=limit,
        )

    def episode(self, session_id: str) -> Episode | None:
        return next((e for e in self._scan_sessions() if e.session_id == session_id), None)

    def sessions(self, limit: int = 60) -> list[Episode]:
        """Tüm geçmiş oturumlar, en yeniden eskiye. Sohbet listesi bununla.

        `episodes`'ten farkı sorgusuz olması: arama değil, gezinme. Boş bir
        oturum (tek mesajlık, dijesti çıkmayan) listeye girmiyor — tıklanınca
        boş bir şey açmak iyi bir sohbet listesi değil.
        """
        # Yardımcı (alt ajan) oturumları listeye girmiyor: kullanıcının
        # sohbet geçmişi kendi konuşmaları — arka planda koşan yardımcıların
        # ara işleri değil. Günlükleri diskte duruyor, aramada da varlar.
        eps = [e for e in self._scan_sessions() if not e.child]
        eps.sort(key=lambda e: e.started, reverse=True)
        return eps[:limit]

    def transcript(self, session_id: str) -> list[dict[str, str]]:
        """Bir oturumun konuşma dökümü: yalnızca metin turları.

        Araç çağrıları ve düşünme dışarıda — geçmiş bir sohbete bakan
        kullanıcı ne söylendiğini okumak istiyor, araç argümanlarını değil.

        Harness'ın kendi notları da dışarıda. Bu, kanıtlanmış bir sızıntının
        kökü: canlı akışta hub süzüyordu (`_payload`), ama DÖKÜM süzmüyordu —
        oturum sürdürülünce ya da geçmişten açılınca "Planını yazdın ama
        uygulamadın…" gibi iç dürtüler sohbete KULLANICI MESAJI gibi
        düşüyordu. İşaretler günlükte zaten duruyor (`internal`,
        `continuation`, `tool_results`); tek eksik onlara burada da bakmaktı.
        """
        path = self.sessions_dir / f"{session_id}.jsonl"
        if not path.is_file():
            return []
        out: list[dict[str, str]] = []
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not (line := line.strip()):
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    role = event.get("role")
                    if role not in ("user", "assistant"):
                        continue
                    if _harness_notu(event):
                        continue
                    text = "\n".join(_plain_text(event.get("content"))).strip()
                    if text:
                        out.append({"role": role, "text": text})
        except OSError:
            return []
        return out

    # -- projeler (sohbet klasörleri) --------------------------------------
    #
    # Bir konuşmayı bir projeye bağlamak: gezinme kolaylığı, anı DEĞİL.
    # Atama basit bir eşleme dosyasında (oturum → proje adı); günlükler
    # değişmiyor. Anılar hâlâ konuşmalardan ayrıca oluşuyor.

    def _projects_path(self) -> Path:
        return self.sessions_dir / "_projects.json"

    def projects(self) -> dict[str, str]:
        """Oturum → proje adı eşlemesi. Atanmamışlar burada yok."""
        path = self._projects_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def set_project(self, session_id: str, project: str) -> dict[str, str]:
        """Bir oturumu bir projeye bağlar; boş ad bağlamayı kaldırır."""
        with self._lock:
            mapping = self.projects()
            name = (project or "").strip()
            if name:
                mapping[session_id] = name
            else:
                mapping.pop(session_id, None)
            try:
                self.sessions_dir.mkdir(parents=True, exist_ok=True)
                self._projects_path().write_text(
                    json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            return mapping

    # -- oturum kimliği (ad + etiket) --------------------------------------
    #
    # Başlık bugüne kadar dijestin ilk sözcüklerinden türetiliyordu: ucuz
    # ama kullanıcının seçtiği bir ad değil. "Şu CMS işi neredeydi?" diye
    # bakan biri kendi verdiği adı arıyor.
    #
    # Ad ve etiketler `_oturumlar.json` içinde, projelerle AYNI kalıpta:
    # ayrı bir eşleme dosyası, ham günlüklere hiç dokunmadan. Günlük
    # değişmez olmalı — anılar ondan üretiliyor ve elle düzenlenen bir ad
    # geçmişi yeniden yazmak anlamına gelirdi.

    def _meta_path(self) -> Path:
        return self.sessions_dir / "_oturumlar.json"

    def session_meta(self) -> dict[str, dict[str, Any]]:
        """Oturum → {ad, etiketler, path, model, provider}.

        Kaydı olmayan oturumlar burada yok. `path` çalışma klasörü;
        `model`/`provider` bu sohbete özel model (geçişte uygulanır).
        """
        path = self._meta_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            etiketler = value.get("etiketler")
            out[str(key)] = {
                "ad": str(value.get("ad") or ""),
                "etiketler": [str(e) for e in etiketler] if isinstance(etiketler, list) else [],
                "path": str(value.get("path") or "").strip(),
                "model": str(value.get("model") or "").strip(),
                "provider": str(value.get("provider") or "").strip(),
            }
        return out

    def set_session_meta(
        self,
        session_id: str,
        *,
        ad: str | None = None,
        etiketler: list[str] | None = None,
        path: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Ad / etiket / klasör / model yazar; None verilen alan dokunulmaz.

        Boş ad türetilmiş başlığa döner. Hepsi boşsa kayıt silinir.
        """
        with self._lock:
            mapping = self.session_meta()
            kayit = mapping.get(session_id, {
                "ad": "", "etiketler": [], "path": "", "model": "", "provider": "",
            })
            if ad is not None:
                kayit["ad"] = " ".join(str(ad).split())[:80]
            if etiketler is not None:
                temiz: list[str] = []
                for etiket in etiketler:
                    flat = " ".join(str(etiket).split()).strip().lower()[:24]
                    if flat and flat not in temiz:
                        temiz.append(flat)
                kayit["etiketler"] = temiz[:8]
            if path is not None:
                kayit["path"] = str(path or "").strip()[:500]
            if model is not None:
                kayit["model"] = str(model or "").strip()[:120]
            if provider is not None:
                kayit["provider"] = str(provider or "").strip()[:40]

            if (kayit.get("ad") or kayit.get("etiketler")
                    or kayit.get("path") or kayit.get("model")
                    or kayit.get("provider")):
                mapping[session_id] = kayit
            else:
                mapping.pop(session_id, None)

            try:
                self.sessions_dir.mkdir(parents=True, exist_ok=True)
                self._meta_path().write_text(
                    json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            return mapping.get(session_id, {
                "ad": "", "etiketler": [], "path": "", "model": "", "provider": "",
            })

    def archive_session(self, session_id: str) -> dict[str, Any]:
        """Oturumu listeden çıkarır; günlüğü sessions/.arsiv'e taşır.

        Kalıcı silme yok — uygulamalar panelindeki .geri-donusum ile aynı
        fikir: yanlış tık geri alınabilsin. Açık oturum taşınmaz (önce
        başka sohbete geç); yoksa koşan şeridin günlüğü kaybolur.
        """
        sid = str(session_id or "").strip()
        if not sid:
            return {"ok": False, "error": "geçersiz oturum"}
        if sid == self.session_id:
            return {"ok": False, "error": "açık sohbet arşivlenemez — önce başka birine geç"}
        src = self.sessions_dir / f"{sid}.jsonl"
        if not src.is_file():
            return {"ok": False, "error": "oturum bulunamadı"}
        with self._lock:
            dest_dir = self.sessions_dir / ".arsiv"
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / f"{sid}.jsonl"
                if dest.exists():
                    dest = dest_dir / f"{sid}-{uuid4().hex[:8]}.jsonl"
                src.replace(dest)
            except OSError as exc:
                return {"ok": False, "error": f"taşınamadı: {exc}"}
            self._episode_cache.pop(sid, None)
            meta = self.session_meta()
            if sid in meta:
                meta.pop(sid, None)
                try:
                    self._meta_path().write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                except OSError:
                    pass
            projects = self.projects()
            if sid in projects:
                projects.pop(sid, None)
                try:
                    self._projects_path().write_text(
                        json.dumps(projects, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                except OSError:
                    pass
        return {"ok": True, "id": sid}

    # -- döküm araması -----------------------------------------------------

    def search_transcripts(
        self,
        query: str,
        *,
        limit: int = 40,
        per_session: int = 3,
    ) -> dict[str, list[dict[str, str]]]:
        """Oturum günlüklerinin İÇİNDE metin arar.

        Panelin arama kutusu bugüne kadar yalnızca başlığı süzüyordu:
        "borsa taramasını nerede konuşmuştuk" sorusunun cevabı listede
        görünmüyordu çünkü söz başlıkta değil, konuşmanın ortasındaydı.

        Sınırlar bilinçli ve ucuzluk için: yalnızca SON `limit` oturum
        taranıyor (eskiler zaten anılara süzülmüş oluyor), her oturumdan en
        çok `per_session` eşleşme dönüyor ve satırlar kırpılıyor. Amaç
        "hangi konuşmaydı" sorusunu cevaplamak; tam metin arama motoru
        olmak değil.
        """
        needle = " ".join((query or "").split()).lower()
        if len(needle) < 2:
            return {}

        found: dict[str, list[dict[str, str]]] = {}
        for episode in self.sessions()[:limit]:
            hits: list[dict[str, str]] = []
            for turn in self.transcript(episode.session_id):
                text = turn.get("text") or ""
                at = text.lower().find(needle)
                if at < 0:
                    continue
                hits.append({"role": turn.get("role", ""), "text": _cevre(text, at, len(needle))})
                if len(hits) >= per_session:
                    break
            if hits:
                found[episode.session_id] = hits
        return found

    def _scan_sessions(self) -> list[Episode]:
        if not self.sessions_dir.is_dir():
            return []
        paths = sorted(self.sessions_dir.glob("*.jsonl"), reverse=True)[:MAX_SCANNED_SESSIONS]
        out: list[Episode] = []
        for path in paths:
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            cached = self._episode_cache.get(path.stem)
            if cached and cached[0] == mtime:
                out.append(cached[1])
                continue
            episode = _digest_session(path)
            if episode is not None:
                self._episode_cache[path.stem] = (mtime, episode)
                out.append(episode)
        return out

    def links(self) -> list[tuple[str, str, float]]:
        """Hatiralar arasindaki cagrisim baglari. Arayuz agi bununla ciziyor."""
        return self.store.links()

    def close(self) -> None:
        self.store.close()

    # -- yazma ---------------------------------------------------------

    def _write(self, filename: str, record: Any) -> None:
        path = self.dir / filename
        with self._lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


# ---------------------------------------------------------------------


def _load(path: Path, kind: type, into: dict[str, Any]) -> None:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not (line := line.strip()):
                continue
            try:
                record = kind(**json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue  # ileri sürüm alanı ya da yarım satır: atla
            into[record.id] = record  # sonraki kayıt öncekini geçersiz kılar



def _from_node(node, *, deleted: bool = False) -> Memory:
    """Depo kaydini eski Memory bicimine cevirir.

    Arayuz, ruh ve graf katmanlari bu bicimi bekliyor; depo degisimi
    onlara sizmasin diye tek noktada cevriliyor.
    """
    return Memory(
        id=node.id,
        ts=node.created,
        kind=node.kind,
        title=node.title,
        content=node.body,
        tags=list(node.tags),
        session_id=node.session,
        deleted=deleted,
    )

def _stem_to_date(stem: str) -> str:
    """20260822T203420Z -> 2026-08-22. Tanınmayan biçimi olduğu gibi bırakır."""
    digits = stem[:8]
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return stem


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "(başlıksız)")


def _digest_session(path: Path) -> Episode | None:
    """Bir oturum günlüğünü aranabilir tek bir özete indirger."""
    started = ""
    turns = 0
    tools: list[str] = []
    fragments: list[str] = []
    child = False

    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not (line := line.strip()):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                started = started or event.get("ts", "")

                if event.get("kind") == "meta":
                    if event.get("content") == "tool_start":
                        name = event.get("meta", {}).get("tool")
                        if name and name not in tools:
                            tools.append(name)
                    # Yardımcının kendi günlüğündeki doğum notu: `parent`
                    # alanı yalnız çocukta var (ana ajandaki eş nota
                    # `session` yazılıyor).
                    elif (event.get("content") == "subagent_start"
                          and event.get("meta", {}).get("parent")):
                        child = True
                    continue

                role = event.get("role")
                if role == "assistant":
                    turns += 1
                if role not in ("user", "assistant"):
                    continue
                fragments.extend(_text_of(event.get("content")))
    except OSError:
        return None

    if not fragments:
        return None

    return Episode(
        session_id=path.stem,
        started=started,
        turns=turns,
        tools=tools,
        digest=" ".join(fragments)[:8000],
        child=child,
    )


# Kullanıcının yazmadığı turların günlükteki işaretleri. Üçü de aynı şeyi
# söylüyor: bu satırı harness koydu, sohbette mesaj gibi görünmemeli.
HARNESS_ISARETLERI = ("internal", "continuation", "tool_results")


def _cevre(text: str, at: int, length: int, span: int = 60) -> str:
    """Eşleşmenin çevresinden okunur bir alıntı çıkarır.

    Turun tamamını döndürmek listeyi duvara çevirirdi; aranan sözcük
    bağlamıyla birlikte görünmeli ki "hangi konuşmaydı" bir bakışta
    anlaşılsın.
    """
    flat = " ".join(text.split())
    # Boşluk sadeleştirmesi indeksi kaydırıyor; alıntıyı sadeleşmiş metin
    # üzerinde yeniden bulmak, kayan bir pencereden daha doğru.
    yeni = flat.lower().find(text[at:at + length].strip().lower())
    if yeni < 0:
        yeni = 0
    bas = max(0, yeni - span)
    son = min(len(flat), yeni + length + span)
    return ("…" if bas else "") + flat[bas:son].strip() + ("…" if son < len(flat) else "")


def _harness_notu(event: dict[str, Any]) -> bool:
    """Bu günlük satırı harness'ın kendi notu mu?

    Kullanıcı turu gibi yazılırlar (bazıları user kanalından gitmek
    ZORUNDA — bkz. `Session.add_continuation_note`), ama kullanıcı
    yazmadı; dökümde gösterilirlerse kullanıcı kendi ağzından çıkmamış
    bir cümle okur.
    """
    meta = event.get("meta")
    if not isinstance(meta, dict):
        return False
    return any(meta.get(isaret) for isaret in HARNESS_ISARETLERI)


def _plain_text(content: Any) -> list[str]:
    """Yalnızca metin blokları — araç çağrısı ve düşünme dışarıda.

    `_text_of`'tan farkı: o arama için tool_use'u da metne çeviriyor;
    burada insana gösterilecek konuşma dökümü isteniyor, o yüzden sadece
    gerçek söz alınıyor.
    """
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [str(b.get("text", "")) for b in content
            if isinstance(b, dict) and b.get("type") == "text"]


def _text_of(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            out.append(str(block.get("text", "")))
        elif block.get("type") == "tool_use":
            out.append(f"{block.get('name', '')} {json.dumps(block.get('input', {}), ensure_ascii=False)}")
    return out


def render_hits(hits: list[Scored], *, text_of, header: str) -> str:
    if not hits:
        return f"{header}: sonuç yok."
    lines = [header + ":"]
    for hit in hits:
        lines.append(excerpt(text_of(hit.item), hit.matched))
    return "\n\n".join(lines)
