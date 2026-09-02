"""Hatırlama deposu.

Tasarımın çıkış noktası tek bir şikâyet: bellek büyüdükçe yavaşlamamalı.
Önceki hal her sorguda bütün oturum günlüklerini okuyup tarıyordu — on
oturumda fark edilmez, on bin oturumda kullanılamaz.

Burada tarama yok. SQLite'ın FTS5 indeksi terimden kayda gidiyor; sorgu
maliyeti toplam hacme değil, eşleşen kayıt sayısına bağlı. Ek bağımlılık da
yok: sqlite3 standart kütüphanede.

İki katman:

    disk    Kalıcı. Bilgisayar kapansa da durur. Tek dosya: recall.db
    RAM     SQLite'ın kendi sayfa önbelleği. Sınırı yapılandırılabilir
            (varsayılan 2 GB). Dolunca en az kullanılan sayfalar düşer —
            ama veri kaybolmaz, diskte durmaya devam eder.

Bu ikinci katmanı elle yazmıyoruz çünkü SQLite'ınki tam olarak istenen şey:
sıcak olan RAM'de kalır, soğuyan diske iner, hiçbir şey silinmez.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Any, Iterable, Sequence
from uuid import uuid4

from . import aktivasyon, anahtar, vector
from .saat import Saat, coz, damga, duvar_saati

KINDS = ("fact", "preference", "lesson", "procedure", "user", "voice", "goal", "episode")

# Varsayılan RAM bütçesi. Kullanıcı artırabilir; dolunca en az kullanılan
# sayfalar düşer, kayıt diskte kalır.
DEFAULT_CACHE_BYTES = 2 * 1024**3

# Yayılan aktivasyonda her sıçramada zayıflama. 1.0 olsaydı uzak çağrışımlar
# doğrudan eşleşmeler kadar güçlü görünürdü.
# Imza kanalinin puani bu carpanla oleceklenir. Birebir gecen bir terim,
# benzer duran bir metinden daha guclu bir kanit oldugu icin bir altinda.
SIGNATURE_WEIGHT = 0.9

# Terimden govde tahmini icin alinan harf sayisi. Kisaltmak alakasiz
# eslesme, uzatmak eki yakalayamamak demek.
STEM_CHARS = 5

# Bir kaydın "aynı konuda zaten var olanı" sayılması için gereken benzerlik.
# Kalibrasyon (yaşam bench, `--celiski-esik`, 2026-09-02): 24 düzeltme
# olayında doğru önceki sürümü yakalama oranı, 60 gürültü kaydında yanlış
# alarm sayısına karşı tarandı:
#     0.50 → yakalama 0.79, yanlış 24     0.60 → yakalama 0.25, yanlış 2
#     0.55 → yakalama 0.75, yanlış  5     0.75 → yakalama 0.00, yanlış 1
# Yol haritasının önerdiği başlangıç 0.75 hiçbir şey yakalamıyor; eğri
# 0.55–0.60 arasında dikleşiyor. Diz noktası seçildi: dörtte üç yakalama,
# altmış gürültü kaydında beş uyarı. Uyarı bir öneridir, kayıt her hâlükârda
# yazılır — yanlış alarmın maliyeti bir cümle, kaçırmanınki bir çelişki.
# Bkz. docs/charts/celiski-esigi.md.
CELISKI_ESIK = 0.55

HOP_DECAY = 0.45
MIN_ACTIVATION = 0.02

_WORD = re.compile(r"\w+", re.UNICODE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS node (
    id        TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    title     TEXT NOT NULL,
    body      TEXT NOT NULL,
    tags      TEXT NOT NULL DEFAULT '',
    session   TEXT NOT NULL DEFAULT '',
    created   TEXT NOT NULL,
    last_used TEXT,
    uses      INTEGER NOT NULL DEFAULT 0,
    deleted   INTEGER NOT NULL DEFAULT 0,
    sig       BLOB,
    -- Kullanım geçmişi: son 30 kullanım, JSON dizi.
    --   [{"t": "<ISO>", "w": 1.0, "etiket": "acildi"}, ...]
    -- Yazım anı ilk kullanımdır (w = 1.0; Faz 4 bunu sürprizle değiştirir).
    -- w negatif olabilir (Faz 3 ters tekrar): hataya götüren kullanım izi
    -- zayıflatır. etiket: yazildi | acildi | basari | hata | sema | yakalandi.
    -- Faz 1'de yalnız ilk ikisi yazılır; alan baştan bu biçimde açılıyor ki
    -- sonraki fazlar şema değiştirmesin.
    -- `uses`/`last_used` korunuyor (arayüz okuyor) ama aktivasyon bu
    -- sütundan hesaplanıyor — sayaç zamanı bilmiyor.
    kullanimlar TEXT NOT NULL DEFAULT '[]',
    -- Güncelleme zinciri. Silme değil YER DEĞİŞTİRME: eski satır diskte,
    -- `series`'te ve açık aramada kalır; yalnız tohumlamadan ve ruhtan
    -- düşer, ve kendisine gelen çağrışım yeni sürüme yönlenir.
    supersedes    TEXT NOT NULL DEFAULT '',   -- bu kayıt kimin yerini aldı
    superseded_by TEXT NOT NULL DEFAULT ''    -- bu kaydın yerini kim aldı
);
CREATE INDEX IF NOT EXISTS node_kind ON node(kind) WHERE deleted = 0;
-- node_superseded indeksi _add_missing_columns'ta kuruluyor: eski bir
-- belleği açarken sütun henüz eklenmemiş oluyor ve buradaki CREATE INDEX
-- bütün şema betiğini düşürürdü.

CREATE TABLE IF NOT EXISTS link (
    src    TEXT NOT NULL,
    dst    TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS link_dst ON link(dst);

CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
    title, body, tags,
    content='node', content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 0'
);

CREATE TRIGGER IF NOT EXISTS node_ai AFTER INSERT ON node BEGIN
    INSERT INTO node_fts(rowid, title, body, tags)
    VALUES (new.rowid, new.title, new.body, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS node_ad AFTER DELETE ON node BEGIN
    INSERT INTO node_fts(node_fts, rowid, title, body, tags)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS node_au AFTER UPDATE ON node BEGIN
    INSERT INTO node_fts(node_fts, rowid, title, body, tags)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags);
    INSERT INTO node_fts(rowid, title, body, tags)
    VALUES (new.rowid, new.title, new.body, new.tags);
END;
"""


def _new_id() -> str:
    return f"n_{uuid4().hex[:10]}"


@dataclass(slots=True)
class Node:
    id: str
    kind: str
    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    session: str = ""
    created: str = ""
    last_used: str | None = None
    uses: int = 0
    # Taban seviyesi aktivasyon (ACT-R B). Okuma anında hesaplanıyor: bir
    # izin "şu an ne kadar canlı" olduğu diskte durabilecek bir sayı değil,
    # zamanın fonksiyonu.
    aktivasyon: float = aktivasyon.TABAN_YOK
    # Güncelleme zinciri. `superseded_by` doluysa bu kayıt geçmiştir:
    # aranmaz, ruha girmez — ama silinmemiştir.
    supersedes: str = ""
    superseded_by: str = ""
    deleted: bool = False

    def headline(self) -> str:
        """Modele önce bu gider: kimlik ve tek satır. Gövde açılınca gelir."""
        tags = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"{self.id} ({self.kind}) {self.title}{tags}"


@dataclass(slots=True)
class Step:
    """Aktivasyonun bir adımı — hatırlarken uğranan yer.

    Arayüz bunu sırayla canlandırıyor: sinapsın ateşlendiği yol.
    """

    node: str
    kind: str
    activation: float
    hop: int
    via: str  # "query" ya da aktivasyonu ileten düğümün kimliği


@dataclass(slots=True)
class Recollection:
    query: str
    hits: list[Node]
    trace: list[Step]

    def headlines(self) -> str:
        return "\n".join(h.headline() for h in self.hits)


class RecallStore:
    def __init__(
        self,
        path: Path,
        *,
        cache_bytes: int = DEFAULT_CACHE_BYTES,
        saat: Saat | None = None,
    ) -> None:
        self.path = path
        # Zaman tek bir yerden okunuyor (bkz. saat.py): ürün duvar saatini
        # kullanır, benchmark sanal takvimi verir. Doğrudan datetime.now()
        # çağrısı "otuz gün sonra ne olur" sorusunu ölçülemez yapardı.
        self._saat: Saat = saat or duvar_saati
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row

        # WAL: okuyucu yazarı bloke etmiyor. Birden fazla süreç aynı belleği
        # açtığında (ajan + arayüz + MCP istemcisi) bu şart.
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        # Negatif değer KiB cinsinden bütçe demek; sayfa sayısı değil.
        self._db.execute(f"PRAGMA cache_size={-(cache_bytes // 1024)}")
        self._db.executescript(SCHEMA)
        self._add_missing_columns()
        self._db.commit()
        # Imza indeksi ilk aramada yukleniyor: bellegi hic aramadan acan
        # surecler (yalnizca yazan bir MCP istemcisi gibi) bedelini odemesin.
        # Oturum acan surec `warm()` ile arka planda erkenden RAM'e alabilir.
        self._index: vector.Index | None = None
        self._index_lock = threading.Lock()

    def _simdi(self) -> str:
        """Diske yazılacak "şu an" damgası."""
        return damga(self._saat)

    def _add_missing_columns(self) -> None:
        """Once acilmis bir belleği yeni sutunla surdurur.

        Kullanicinin diskindeki hatiralar surum yukseltmesinde silinmemeli;
        eksik sutun eklenip imzalar ilk aramada geriye donuk uretiliyor.
        """
        have = {row["name"] for row in self._db.execute("PRAGMA table_info(node)")}
        if "sig" not in have:
            self._db.execute("ALTER TABLE node ADD COLUMN sig BLOB")
        for sutun in ("supersedes", "superseded_by"):
            if sutun not in have:
                self._db.execute(
                    f"ALTER TABLE node ADD COLUMN {sutun} TEXT NOT NULL DEFAULT ''")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS node_superseded ON node(superseded_by)"
            " WHERE superseded_by != ''")
        if "kullanimlar" not in have:
            self._db.execute(
                "ALTER TABLE node ADD COLUMN kullanimlar TEXT NOT NULL DEFAULT '[]'")
            # Sütun boş kalsa da okuma tarafı created/last_used/uses'tan
            # geriye dönük üretiyor (aktivasyon.coz_kullanimlar); burada bir
            # kez diske yazmak o hesabı her okumadan kaldırıyor.
            self._kullanimlari_doldur()

    def _kullanimlari_doldur(self) -> None:
        """`kullanimlar` sütunu yokken yazılmış kayıtları kabaca doldurur.

        Bu olmadan sütun eklendiği anda kullanıcının yıllarca biriktirdiği
        bütün hatıralar "hiç kullanılmamış" sayılır ve bellek tek bir sürüm
        yükseltmesinde sıfırlanmış gibi davranırdı.
        """
        satirlar = []
        for row in self._db.execute(
                "SELECT id, created, last_used, uses FROM node"
                " WHERE kullanimlar IN ('', '[]')"):
            gecmis = aktivasyon.coz_kullanimlar(
                "", created=row["created"], last_used=row["last_used"],
                uses=int(row["uses"] or 0))
            if not gecmis:
                continue
            satirlar.append((aktivasyon.kodla(gecmis), row["id"]))
        if satirlar:
            self._db.executemany(
                "UPDATE node SET kullanimlar=? WHERE id=?", satirlar)

    def kullanim_ekle(self, node_id: str, *, w: float = 1.0,
                      etiket: str = aktivasyon.ACILDI) -> bool:
        """İze bir kullanım işler — sayaç artırmadan.

        `open()` modelin kaydı okumasıdır; bu ise sistemin ona bir pay
        vermesidir: gece tekrarı başarıya götüren düğüme artı, hataya
        götürene eksi ağırlık yazıyor. `uses` dokunulmuyor çünkü kayıt
        gerçekten "kullanılmadı" — sorumluluğu dağıtıldı.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT created, last_used, uses, kullanimlar FROM node"
                " WHERE id=? AND deleted=0", (node_id,)).fetchone()
            if row is None:
                return False
            gecmis = aktivasyon.coz_kullanimlar(
                row["kullanimlar"], created=row["created"],
                last_used=row["last_used"], uses=int(row["uses"] or 0))
            self._db.execute(
                "UPDATE node SET kullanimlar=? WHERE id=?",
                (aktivasyon.ekle(gecmis, self._saat(), w=w, etiket=etiket), node_id))
            self._db.commit()
        return True

    def sicil(self, node_id: str) -> tuple[int, int]:
        """Bir hatıranın (başarı, hata) sicili. Model bunu görürse
        "bu bazen yanıltıyor" bilgisini de görür."""
        return aktivasyon.sicil(self.kullanimlar(node_id))

    def _dugum(self, row: sqlite3.Row) -> Node:
        """Satırı düğüme çevirir ve o anki aktivasyonunu hesaplar."""
        return _to_node(row, seviye=self._taban_seviyesi(row))

    def _taban_seviyesi(self, row: sqlite3.Row) -> float:
        gecmis = aktivasyon.coz_kullanimlar(
            _alan(row, "kullanimlar"),
            created=_alan(row, "created"),
            last_used=_alan(row, "last_used"),
            uses=int(_alan(row, "uses") or 0),
        )
        return aktivasyon.taban_aktivasyon(gecmis, self._saat())

    def kullanimlar(self, node_id: str) -> list:
        """Bir kaydın kullanım geçmişi. İçgözlem ve ölçüm için."""
        with self._lock:
            row = self._db.execute(
                "SELECT created, last_used, uses, kullanimlar FROM node WHERE id=?",
                (node_id,),
            ).fetchone()
        if row is None:
            return []
        return aktivasyon.coz_kullanimlar(
            row["kullanimlar"], created=row["created"],
            last_used=row["last_used"], uses=int(row["uses"] or 0))

    @property
    def index(self) -> vector.Index:
        """Imzalarin RAM'deki hali; ilk erisimde diskten kuruluyor."""
        if self._index is None:
            # Çift kilit: warm() arka planda kurarken ilk arama da gelirse
            # indeks iki kez inşa edilmesin.
            with self._index_lock:
                if self._index is None:
                    self._index = self._load_index()
        return self._index

    def warm(self) -> None:
        """İmza indeksini arka planda diskten RAM'e alır.

        Oturum açılışında çağrılıyor: hatıralar model daha ilk mesajı
        almadan RAM'de hazır oluyor ve ilk hatırlama indeks kurulumunu
        beklemiyor. Ayrı iş parçacığında — açılışı bloke etmek,
        hızlandırmak istediğimiz şeyi yavaşlatmak olurdu.
        """
        if self._index is None:
            threading.Thread(
                target=lambda: self.index, name="recall-warm", daemon=True
            ).start()

    def _load_index(self) -> vector.Index:
        # Episode'lar (tur dökümleri) BİLEREK indekste: kendiliğinden
        # önyükleme ve hasat onları dışlıyor ama model-güdümlü `mind_recall`
        # bir konuşmayı eşanlamlı kelimelerle de bulabilmeli — imza kanalı
        # tam da bunu sağlıyor, FTS yalnız birebir kelimeyi yakalar. Bedeli
        # taramanın büyümesi; ölçüldü: kayıt başına iş tek XOR+popcount,
        # 50k kayıtta ~3-5 ms — bir model çağrısının binde biri. Episode
        # sayısı taramayı gerçekten yorana kadar (yüz binler) bu takas doğru.
        with self._lock:
            rows = self._db.execute(
                "SELECT id, title, body, tags, sig FROM node WHERE deleted=0"
                + self._gecmis_suzgeci()
            ).fetchall()

        index = vector.Index()
        backfill: list[tuple[bytes, str]] = []
        for row in rows:
            value = vector.from_blob(row["sig"])
            if not value:
                # Imzasiz kayit: bu surumden once yazilmis. Bir kez uretilip
                # diske yaziliyor, bir daha hesaplanmiyor.
                value = vector.signature(f"{row['title']} {row['body']} {row['tags']}")
                if value:
                    backfill.append((vector.to_blob(value), row["id"]))
            index.add(row["id"], value)

        if backfill:
            with self._lock:
                self._db.executemany("UPDATE node SET sig=? WHERE id=?", backfill)
                self._db.commit()
        return index

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- yazma ---------------------------------------------------------

    def remember(
        self,
        body: str,
        *,
        kind: str = "fact",
        title: str = "",
        tags: Iterable[str] = (),
        session: str = "",
        links: Iterable[str] = (),
        supersedes: str = "",
        kullanimlar: str = "",
    ) -> Node:
        if kind not in KINDS:
            raise ValueError(f"Bilinmeyen tür: {kind}. Geçerli olanlar: {', '.join(KINDS)}")
        body = body.strip()
        if not body:
            raise ValueError("Boş içerik kaydedilmez.")

        node = Node(
            id=_new_id(),
            kind=kind,
            title=(title.strip() or _first_line(body))[:140],
            body=body,
            tags=[t.strip() for t in tags if t.strip()],
            session=session,
            created=self._simdi(),
            supersedes=supersedes,
        )
        tag_text = " ".join(node.tags)
        sign = vector.signature(f"{node.title} {node.body} {tag_text}")
        with self._lock:
            self._db.execute(
                "INSERT INTO node(id, kind, title, body, tags, session, created,"
                " sig, kullanimlar, supersedes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (node.id, node.kind, node.title, node.body,
                 tag_text, node.session, node.created, vector.to_blob(sign),
                 kullanimlar or aktivasyon.ilk_damga(node.created),
                 supersedes),
            )
            for other in links:
                self._link(node.id, other, 1.0, "birlikte kaydedildi")
            self._db.commit()

        # Yeni imza hem diske (yukaridaki INSERT) hem RAM'e yaziliyor. RAM
        # eklemesi indeks kilidinin altinda: warm() arka planda indeksi
        # kurarken bu kayit ne diskten okunan anlik goruntuye ne de RAM'e
        # girmeden aradan dusmesin. Indeks henuz kurulmadiysa eklemeye gerek
        # yok — kuruldugunda bu satiri zaten diskten okuyacak.
        with self._index_lock:
            if self._index is not None:
                self._index.add(node.id, sign)

        # Ag kendiliginden orulsun: yeni kayit, icerigine en yakin birkac
        # hatiraya baglanir. Elle baglama beklemek agin hic olusmamasi
        # demekti; cagrisim da bu baglarin uzerinden yuruyor.
        self._weave(node)
        return node

    def guncelle(
        self,
        eski_id: str,
        body: str,
        *,
        kind: str = "",
        title: str = "",
        tags: Iterable[str] = (),
        session: str = "",
    ) -> Node:
        """Bir kaydın yerine yenisini yazar. Eskisi SİLİNMEZ.

        Dört iş bir arada:

        1. Yeni kayıt `supersedes=eski_id` ile yazılır.
        2. Eskiye `superseded_by=yeni_id` yazılır; `deleted` 0 kalır.
        3. İkisi "günceller" gerekçeli bir kenarla bağlanır — arayüz zinciri
           çizebilsin, çağrışım o yoldan yürüyebilsin.
        4. Eskinin kullanım geçmişi yeniye **kopyalanır**. Pekişme mirası
           olmasaydı düzeltme sıfırdan başlar ve ruhta düzelttiği şeyin
           altında kalırdı — düzeltmenin bütün amacının tersi.

        Eski kayıt imza indeksinden düşürülüyor: aranmaz, ruha girmez, ama
        diskte, `series`'te ve açık aramada durmaya devam eder.
        """
        eski = self.peek(eski_id)
        if eski is None:
            raise ValueError(f"Güncellenecek kayıt yok: {eski_id}")

        # Miras + yeni yazım anı: düzeltme, düzelttiği şeyin pekişmesini
        # devralır ve üstüne kendi tazeliğini koyar.
        miras = aktivasyon.ekle(self.kullanimlar(eski_id), self._saat(),
                                etiket=aktivasyon.YAZILDI)
        yeni = self.remember(
            body,
            kind=kind or eski.kind,
            title=title,
            tags=tags or eski.tags,
            session=session or eski.session,
            supersedes=eski_id,
            kullanimlar=miras,
        )
        with self._lock:
            self._db.execute("UPDATE node SET superseded_by=? WHERE id=?",
                             (yeni.id, eski_id))
            self._link(yeni.id, eski_id, 1.0, "günceller")
            self._db.commit()
        # Eski sürüm imza kanalından düşüyor; FTS'te kalıyor (birebir
        # kelimeyle hâlâ bulunur — "ipucuyla uyanır").
        with self._index_lock:
            if self._index is not None:
                self._index.drop(eski_id)
        return yeni

    def celiski_adayi(self, body: str, kind: str, *,
                      esik: float = CELISKI_ESIK) -> Node | None:
        """Bu gövde, aynı türden var olan bir kaydın güncellemesi olabilir mi?

        Model `supersedes` vermeyi unutursa sistem sessiz kalmamalı: en yakın
        birkaç komşuya bakılıyor, aynı türden ve yeterince benzer olan varsa
        araç yanıtında adı geçiyor. Karar modelin — kayıt her hâlükârda
        yazılıyor. Kaçırmamak, temiz olmaktan önemli.
        """
        if not anahtar.AKTIF.supersede:
            return None
        for node_id, score, aday_kind in self._seed(body[:400], 3):
            if aday_kind == kind and score >= esik:
                return self.peek(node_id)
        return None

    def gecerli_surum(self, node_id: str) -> str:
        """Zincirin ucundaki kayıt. Döngü korumalı.

        Elle bozulmuş bir db'de A→B, B→A yazılabilir; hatırlama o zaman
        sonsuza kadar dönerdi. Görülen kimlik ikinci kez gelirse durulur.
        """
        gorulen = {node_id}
        simdiki = node_id
        while True:
            with self._lock:
                row = self._db.execute(
                    "SELECT superseded_by FROM node WHERE id=?", (simdiki,)
                ).fetchone()
            sonraki = (row["superseded_by"] if row else "") or ""
            if not sonraki or sonraki in gorulen:
                return simdiki
            gorulen.add(sonraki)
            simdiki = sonraki

    def komsular_gerekceli(self, node_id: str) -> list[tuple[Node, float, str]]:
        """Komşular, bağın gerekçesiyle birlikte.

        `neighbours` yalnız ağırlık döndürüyor; gerekçe hem arayüzün
        (supersede kenarını farklı çizmek) hem `mind_recall` çıktısının
        (modele "neden bağlı" bilgisini vermek) ihtiyacı.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT n.*, l.weight, l.reason FROM link l"
                " JOIN node n ON n.id = l.dst"
                " WHERE l.src=? AND n.deleted=0 ORDER BY l.weight DESC",
                (node_id,),
            ).fetchall()
        return [(self._dugum(r), float(r["weight"]), r["reason"]) for r in rows]

    def _weave(self, node: Node, neighbours: int = 3) -> None:
        seeds = self._seed(f"{node.title} {node.body}"[:400], neighbours + 1)
        with self._lock:
            for position, (other, _score, _kind) in enumerate(seeds):
                if other == node.id:
                    continue
                self._link(node.id, other, round(0.8 - position * 0.15, 3), "benzer icerik")
            self._db.commit()

    def baglan(self, src: str, dst: str, *, weight: float = 1.0, reason: str = "",
               birikimli: bool = False, yalniz_yeni: bool = False) -> bool:
        """Bağ kurar; kenarın gerçekten değişip değişmediğini döndürür.

        `birikimli`: aynı gerekçeli bağ tekrar geldiğinde ağırlık MAX'ta
        donmasın, birikerek 1.0'a yaklaşsın. Sıkça birlikte kullanılan iki
        şey güçlü bağlanmalı — beş oturumda peş peşe gelen bir çift, tek
        seferlikle aynı ağırlıkta kalmamalı.

        `yalniz_yeni`: kenar zaten varsa dokunma. Dikiş (Adım 4) böyle
        çalışıyor — yaşanmış bir bağın üstüne varsayım yazılmaz.
        """
        if src == dst or not src or not dst:
            return False
        with self._lock:
            mevcut = self._db.execute(
                "SELECT weight FROM link WHERE src=? AND dst=?", (src, dst)
            ).fetchone()
            if mevcut is not None and yalniz_yeni:
                return False
            if birikimli and mevcut is not None:
                weight = min(1.0, float(mevcut["weight"]) + weight * 0.5)
            self._link(src, dst, weight, reason)
            self._db.commit()
        return True

    def cold_nodes(self, cutoff: datetime) -> tuple[list[str], int]:
        """Nodes nothing has touched since `cutoff`, and how many were skipped.

        "Touched" means the last usage stamp, not the write time: a record
        written a year ago but opened yesterday is warm. Local sleep uses
        this to stay out of the region that is currently being learned.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created, last_used, uses, kullanimlar FROM node"
                " WHERE deleted=0" + self._gecmis_suzgeci()).fetchall()
        soguk: list[str] = []
        sicak = 0
        for row in rows:
            gecmis = aktivasyon.coz_kullanimlar(
                row["kullanimlar"], created=row["created"],
                last_used=row["last_used"], uses=int(row["uses"] or 0))
            son = max((k.t for k in gecmis), default=None)
            if son is not None and son >= cutoff:
                sicak += 1
            else:
                soguk.append(row["id"])
        return soguk, sicak

    def shrink_edges_between(self, node_ids: Sequence[str], epsilon: float,
                             taban: float) -> tuple[int, int]:
        """Shrink only the edges whose BOTH ends are in `node_ids`.

        An edge with one end in the active region is left alone: shrinking it
        would touch a trace that is still being strengthened, which is the
        single thing downscaling must never do while learning is in progress.
        """
        if not node_ids:
            return 0, 0
        kucult = silinen = 0
        with self._lock:
            for i in range(0, len(node_ids), 400):
                parca = list(node_ids[i:i + 400])
                yer = ",".join("?" * len(parca))
                kucult += self._db.execute(
                    f"UPDATE link SET weight = weight * ?"
                    f" WHERE src IN ({yer}) AND dst IN ({yer})",
                    (1.0 - epsilon, *parca, *parca)).rowcount
                silinen += self._db.execute(
                    f"DELETE FROM link WHERE weight < ?"
                    f" AND src IN ({yer}) AND dst IN ({yer})",
                    (taban, *parca, *parca)).rowcount
            self._db.commit()
        return int(kucult), int(silinen)

    def strengthening(self) -> float:
        """Küçültülmemiş güçlenme: toplam kenar ağırlığı / düğüm.

        Uyku basıncının ana terimi (SHY). Eşik bu büyüklüğe karşı ölçüldü
        (bkz. docs/charts/basinc-bozulma.md); aynı büyüklük olmasaydı eşik
        başka bir şeyin eşiği olurdu.
        """
        with self._lock:
            toplam = self._db.execute(
                "SELECT COALESCE(SUM(weight), 0) FROM link").fetchone()[0]
            dugum = self._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=0").fetchone()[0]
        return round(float(toplam) / max(int(dugum), 1), 4)

    def checkpoint(self) -> int:
        """WAL'ı tam kapatır. Yazar yokken yapılır — yani yalnız uykuda."""
        with self._lock:
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.commit()
        try:
            return (self.path.parent / f"{self.path.name}-wal").stat().st_size
        except OSError:
            return 0

    def optimize_fts(self) -> bool:
        """FTS b-tree birleştirme: I/O yoğun, uyanıkken yapılmamalı."""
        with self._lock:
            self._db.execute(
                "INSERT INTO node_fts(node_fts) VALUES('optimize')")
            self._db.commit()
        return True

    def vacuum(self) -> bool:
        """Özel kilit ister; canlı bir oturumun altında imkânsız."""
        with self._lock:
            self._db.execute("VACUUM")
        return True

    def kenar_guncelle(self, src: str, dst: str, *, weight: float | None = None,
                       reason: str | None = None) -> bool:
        """Var olan bir kenarın ağırlığını ya da gerekçesini ÜSTÜNE yazar.

        `baglan` bilinçli olarak yalnız güçlendiriyor (max/birikim); bu ise
        bilerek zayıflatabiliyor. Tek kullanıcısı damıtmanın kenar gerekçesi
        adımı: model "bu ikili ilişkisiz" dediğinde bağ kesilmiyor ama
        ağırlığı düşüyor, ve "neden ilişkili" cümlesi kenarda duruyor —
        SimHash'in eşanlam bilmemesini embedding'siz telafi eden tek yer.
        """
        if src == dst or not src or not dst:
            return False
        with self._lock:
            degisti = 0
            for a, b in ((src, dst), (dst, src)):
                if weight is not None and reason is not None:
                    degisti += self._db.execute(
                        "UPDATE link SET weight=?, reason=? WHERE src=? AND dst=?",
                        (weight, reason, a, b)).rowcount
                elif weight is not None:
                    degisti += self._db.execute(
                        "UPDATE link SET weight=? WHERE src=? AND dst=?",
                        (weight, a, b)).rowcount
                elif reason is not None:
                    degisti += self._db.execute(
                        "UPDATE link SET reason=? WHERE src=? AND dst=?",
                        (reason, a, b)).rowcount
            self._db.commit()
        return bool(degisti)

    def kenarlari_kucult(self, epsilon: float, taban: float) -> tuple[int, int]:
        """Bütün kenarları orantılı küçültür, tabanın altındakini siler.

        Sinaptik homeostaz (Tononi-Cirelli): gündüz güçlenen her şey gece
        orantılı küçülür. Güçlü olan güçlü kalır, zayıf olan gürültü altına
        iner ve budanır. Tek SQL — 300k kenarda bir saniyenin altında.
        """
        with self._lock:
            kucult = self._db.execute(
                "UPDATE link SET weight = weight * ?", (1.0 - epsilon,)).rowcount
            silinen = self._db.execute(
                "DELETE FROM link WHERE weight < ?", (taban,)).rowcount
            self._db.commit()
        return int(kucult), int(silinen)

    def link(self, src: str, dst: str, *, weight: float = 1.0, reason: str = "") -> None:
        """İki hatırayı birbirine bağlar. Çağrışım bu bağların üstünden yürür."""
        with self._lock:
            self._link(src, dst, weight, reason)
            self._db.commit()

    def _link(self, src: str, dst: str, weight: float, reason: str) -> None:
        if src == dst:
            return
        # Bağ çift yönlü: hatırlamada yön yok.
        for a, b in ((src, dst), (dst, src)):
            self._db.execute(
                "INSERT INTO link(src, dst, weight, reason) VALUES (?,?,?,?)"
                " ON CONFLICT(src, dst) DO UPDATE SET"
                "   weight=max(weight, excluded.weight),"
                # Gerekçe ağırlıkla birlikte taşınıyor: daha güçlü bağ daha
                # iyi bir açıklama demek. "benzer icerik" üstüne yazılan
                # "günceller" kaybolmamalı — arayüz zinciri ondan çiziyor.
                "   reason=CASE WHEN excluded.weight >= weight"
                "               THEN excluded.reason ELSE reason END",
                (a, b, weight, reason),
            )

    def merge_from(self, other_path: Path) -> dict[str, int]:
        """Başka bir belleği bu belleğe birleştirir (üzerine yazmadan).

        Taşınabilirlik için: Dornick'in başka bir makinede biriktirdiği anılar
        ve bağlar buraya katılıyor. `INSERT OR IGNORE` — kimlik birincil
        anahtar olduğundan aynı anı iki kez girmiyor (idempotent); yalnızca
        yeni olanlar ekleniyor. İki makinenin öğrendikleri tek bir Dornick'te
        toplanabiliyor. FTS trigger'la kendiliğinden güncelleniyor; imza
        indeksi bir sonraki aramada diskten yeniden kuruluyor.
        """
        if not Path(other_path).exists():
            return {"nodes": 0, "links": 0}
        with self._lock:
            # ATTACH bir işlem içinde çalışmaz: önce beklemedeki her şeyi yaz.
            self._db.commit()
            before_n = self._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            before_l = self._db.execute("SELECT COUNT(*) FROM link").fetchone()[0]
            self._db.execute("ATTACH DATABASE ? AS incoming", (str(other_path),))
            try:
                cols = [r["name"] for r in self._db.execute("PRAGMA incoming.table_info(node)")]
                known = ["id", "kind", "title", "body", "tags", "session",
                         "created", "last_used", "uses", "deleted", "sig",
                         "kullanimlar", "supersedes", "superseded_by"]
                common = ",".join(c for c in known if c in cols)
                if common:
                    self._db.execute(
                        f"INSERT OR IGNORE INTO node({common}) SELECT {common} FROM incoming.node")
                has_link = self._db.execute(
                    "SELECT 1 FROM incoming.sqlite_master WHERE type='table' AND name='link'"
                ).fetchone()
                if has_link:
                    self._db.execute(
                        "INSERT OR IGNORE INTO link(src, dst, weight, reason)"
                        " SELECT src, dst, weight, reason FROM incoming.link")
                self._db.commit()
                after_n = self._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
                after_l = self._db.execute("SELECT COUNT(*) FROM link").fetchone()[0]
            finally:
                self._db.execute("DETACH DATABASE incoming")
        # İmza indeksi baştan kurulsun: yeni imzalar RAM'e girsin.
        with self._index_lock:
            self._index = None
        return {"nodes": after_n - before_n, "links": after_l - before_l}

    def backup_to(self, dest_path: Path) -> None:
        """Belleğin tutarlı, tek dosyalık bir kopyasını yazar (WAL dahil).

        Ham dosyayı kopyalamak WAL'daki son yazımları kaçırabilir; SQLite
        yedek API'si tam ve kilitlenmeden bir kopya üretiyor. Dışa aktarma
        bunu kullanıyor.
        """
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            dest = sqlite3.connect(str(dest_path))
            try:
                self._db.backup(dest)
            finally:
                dest.close()

    def reset(self) -> int:
        """Bütün anıları ve bağları kaldırır; kaç kaydın gittiğini döndürür.

        Geri dönüşsüz — çağıran önce yedeğini almış olmalı (backup_to).
        Satır satır DELETE: node_ad trigger'ı FTS'i her satır için zaten
        temizliyor, ayrı bir 'delete-all' yoluna gerek yok. İmza indeksi
        boş bir indeksle değiştiriliyor ki RAM'de hayalet kayıt kalmasın
        ve canlı uygulama dosyayı kapatmadan sıfırlanabilsin.
        """
        with self._lock:
            n = self._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            self._db.execute("DELETE FROM node")
            self._db.execute("DELETE FROM link")
            self._db.commit()
        with self._index_lock:
            self._index = vector.Index()
        return int(n)

    def forget(self, node_id: str) -> bool:
        """Mezar taşı bırakır: neyin ne zaman unutulduğu da bilginin parçası."""
        with self._lock:
            changed = self._db.execute(
                "UPDATE node SET deleted=1 WHERE id=? AND deleted=0", (node_id,)
            ).rowcount
            self._db.commit()
        if changed:
            # remember() ile ayni gerekce: warm() indeksi kurarken silinen
            # kaydin RAM'de canli kalmamasi icin kilit altinda dusuruluyor.
            with self._index_lock:
                if self._index is not None:
                    self._index.drop(node_id)
        return bool(changed)

    # -- okuma ---------------------------------------------------------

    def _gecmis_suzgeci(self, onek: str = "") -> str:
        """Geçmiş sürümleri dışarıda bırakan SQL parçası.

        Mekanik kapalıyken boş dönüyor: ablation koşusu ürünün kendi
        kodundan geçsin, bench'e kopyalanmış bir sürümden değil.
        """
        if not anahtar.AKTIF.supersede:
            return ""
        return f" AND {onek}superseded_by=''"

    def open(self, node_id: str) -> Node | None:
        """Tam kaydı getirir ve izi güçlendirir.

        Kullanılan hatıra güçlenir; kullanılmayan geride kalır. Sıralama
        buna bakıyor.

        Üç alan birlikte güncelleniyor: `uses` ve `last_used` arayüz için
        (ve eski belleklerin geriye dönük doldurulması için), `kullanimlar`
        aktivasyon için. Sayaç kaç kez olduğunu bilir, damga ne zaman
        olduğunu — hatırlamanın ihtiyacı ikincisi.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM node WHERE id=? AND deleted=0", (node_id,)
            ).fetchone()
            if row is None:
                return None
            simdi = self._simdi()
            gecmis = aktivasyon.coz_kullanimlar(
                _alan(row, "kullanimlar"), created=row["created"],
                last_used=row["last_used"], uses=int(row["uses"] or 0))
            self._db.execute(
                "UPDATE node SET uses=uses+1, last_used=?, kullanimlar=? WHERE id=?",
                (simdi, aktivasyon.ekle(gecmis, self._saat(),
                                        etiket=aktivasyon.ACILDI), node_id),
            )
            self._db.commit()
        node = self._dugum(row)
        if node.superseded_by:
            # Model elinde eski bir kimlik tutuyor olabilir; yönü görmeli.
            uc = self.gecerli_surum(node_id)
            node.body = f"{node.body}\n[güncellendi → {uc}]"
        return node

    def peek(self, node_id: str) -> Node | None:
        """Güçlendirmeden bakar. İç işleyiş için; kullanım sayılmaz."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM node WHERE id=? AND deleted=0", (node_id,)
            ).fetchone()
        return self._dugum(row) if row else None

    def neighbours(self, node_id: str) -> list[tuple[Node, float]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT n.*, l.weight FROM link l JOIN node n ON n.id = l.dst"
                " WHERE l.src=? AND n.deleted=0 ORDER BY l.weight DESC",
                (node_id,),
            ).fetchall()
        return [(self._dugum(r), float(r["weight"])) for r in rows]

    def links(self, limit: int = 4000) -> list[tuple[str, str, float]]:
        """Tum baglar. Arayuz agi bununla ciziyor.

        Her bag cift yonlu saklandigi icin yalnizca bir yonu donduruluyor;
        aksi halde her kenar iki kez cizilirdi.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT l.src, l.dst, l.weight FROM link l"
                " JOIN node a ON a.id = l.src AND a.deleted = 0"
                " JOIN node b ON b.id = l.dst AND b.deleted = 0"
                " WHERE l.src < l.dst LIMIT ?",
                (limit,),
            ).fetchall()
        return [(r["src"], r["dst"], float(r["weight"])) for r in rows]

    def count(self, kind: str | None = None) -> int:
        sql = "SELECT count(*) FROM node WHERE deleted=0" + self._gecmis_suzgeci()
        args: tuple[Any, ...] = ()
        if kind:
            sql += " AND kind=?"
            args = (kind,)
        with self._lock:
            return int(self._db.execute(sql, args).fetchone()[0])

    def recent(self, limit: int = 20) -> list[Node]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM node WHERE deleted=0"
                + self._gecmis_suzgeci()
                + " ORDER BY created DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._dugum(r) for r in rows]

    def by_kind_any(self, limit: int = 500, *,
                    tum_surumler: bool = False) -> list[Node]:
        """Silinmemiş kayıtlar, en yeniden eskiye. Etiket taraması için.

        `tum_surumler` zaman dizisi içindir (`series`): orada geçmiş sürümler
        gürültü değil, istenen şeyin ta kendisidir.
        """
        suzgec = "" if tum_surumler else self._gecmis_suzgeci()
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM node WHERE deleted=0" + suzgec
                + " ORDER BY created DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._dugum(r) for r in rows]

    def by_kind(self, kind: str, limit: int = 50) -> list[Node]:
        """Bir türün kayıtları, en canlı izden en soluğuna.

        Sıralama SQL'de yapılamıyor: aktivasyon zamanın fonksiyonu, diskte
        duran bir sayı değil. Bu yüzden aday kümesi SQL'de daraltılıp
        (kullanım ve tazelik, ikisi de aktivasyonla aynı yöne bakar)
        sıralama Python'da yapılıyor. Aday kümesi istenenin katı kadar
        geniş tutuluyor ki ön eleme gerçekten canlı bir izi düşürmesin.

        Eski hal `ORDER BY uses DESC` idi ve zamanı bilmiyordu: yıllar önce
        çok kullanılmış bir kayıt, dünkü düzeltmeyi ruhun dışında
        tutabiliyordu.
        """
        if not anahtar.AKTIF.aktivasyon:
            # Ablation: mekanik kapalıyken eski SQL sırası (kullanım, sonra
            # tazelik) olduğu gibi dönüyor.
            with self._lock:
                rows = self._db.execute(
                    "SELECT * FROM node WHERE deleted=0 AND kind=?"
                    + self._gecmis_suzgeci()
                    + " ORDER BY uses DESC, created DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            return [self._dugum(r) for r in rows]

        aday = max(limit * 4, 50)
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM node WHERE deleted=0 AND kind=?"
                + self._gecmis_suzgeci()
                + " ORDER BY uses DESC, created DESC LIMIT ?",
                (kind, aday),
            ).fetchall()
        dugumler = [self._dugum(r) for r in rows]
        # Kararlı sıralama: eşit aktivasyonda SQL'in verdiği sıra (kullanım,
        # sonra tazelik) korunuyor.
        dugumler.sort(key=lambda n: -n.aktivasyon)
        return dugumler[:limit]

    # -- hatırlama -----------------------------------------------------

    def recall(self, query: str, *, limit: int = 8, hops: int = 2) -> Recollection:
        """Sorgudan tohumlanır, bağlar üzerinden yayılır.

        Dönen `trace`, aktivasyonun uğradığı yerleri sırayla taşır: arayüz
        bunu canlandırıp hatırlamanın kendisini gösterebiliyor.

        Sorgu önce sinonim köprüsünden geçer: "bitcoin" yazan kullanıcı
        "BTC" yazılmış kaydı bulabilmeli. Köprü yalnız arama tarafında —
        kayıt yazıldığı gibi durur, tablo değişince indeks yeniden kurulmaz.
        """
        from . import bridge

        query = bridge.expand(query)
        if not _match_expression(query):
            # Bos sorgu bir arama degil, bir goz atma: en yeni kayitlar.
            recent = self.recent(limit)
            return Recollection(
                query=query,
                hits=recent,
                trace=[Step(node=n.id, kind=n.kind, activation=1.0, hop=0, via="query")
                       for n in recent],
            )

        seeds = self._seed(query, limit * 2)
        activation: dict[str, float] = {}
        trace: list[Step] = []

        frontier: list[tuple[str, float, str]] = []
        for node_id, score, kind in seeds:
            activation[node_id] = score
            trace.append(Step(node=node_id, kind=kind, activation=score, hop=0, via="query"))
            frontier.append((node_id, score, kind))

        for hop in range(1, hops + 1):
            nxt: list[tuple[str, float, str]] = []
            for node_id, strength, _kind in frontier:
                for neighbour, weight in self.neighbours(node_id):
                    # Geçmiş sürüme gelen çağrışım güncel sürüme yönlenir:
                    # eski kaydın komşuluğu kaybolmuyor, taşınıyor.
                    hedef = neighbour
                    if neighbour.superseded_by and anahtar.AKTIF.supersede:
                        uc = self.peek(self.gecerli_surum(neighbour.id))
                        if uc is None or uc.id == node_id:
                            continue
                        hedef = uc
                    # Unutulmuş düğüm çağrışım yolunu iletmez: aktivasyonu
                    # sönmüş bir kaydın üzerinden geçen yol, konudan
                    # uzaklaşmanın en sessiz yoluydu.
                    spread = (strength * weight * HOP_DECAY
                              * aktivasyon.yayilma_carpani(hedef.aktivasyon))
                    if spread < MIN_ACTIVATION or spread <= activation.get(hedef.id, 0.0):
                        continue
                    activation[hedef.id] = spread
                    trace.append(
                        Step(node=hedef.id, kind=hedef.kind,
                             activation=spread, hop=hop, via=node_id)
                    )
                    nxt.append((hedef.id, spread, hedef.kind))
            frontier = nxt
            if not frontier:
                break

        ranked = sorted(activation.items(), key=lambda kv: -kv[1])[:limit]
        hits = [node for node in (self.peek(nid) for nid, _ in ranked) if node]
        return Recollection(query=query, hits=hits, trace=trace)

    def _seed(self, query: str, limit: int) -> list[tuple[str, float, str]]:
        """Sorgunun ilk temas ettigi kayitlar.

        Iki kanal birlikte calisiyor cunku ikisi de tek basina eksik:

            harf   FTS5 indeksi — "postgres" yazan kaydi kesin bulur,
                   "veritabani dokumu" yazani asla bulmaz.
            imza   cagrisim vektoru — kelimeler tutmasa da yakin metni
                   getirir, ama tam eslesmeyi one cikaramaz.

        Ikisinin birlesimi aliniyor, ortak kayitta yuksek puan kaliyor.
        Harf kanali biraz onde tutuluyor: birebir gecen bir terim, benzer
        duran bir metinden daha guclu bir kanittir.
        """
        lit: dict[str, float] = {}
        sig: dict[str, float] = {}
        kinds: dict[str, str] = {}

        for node_id, score, kind in self._seed_literal(query, limit):
            lit[node_id] = score
            kinds[node_id] = kind

        for node_id, score in self._seed_signature(query, limit):
            sig[node_id] = round(score * SIGNATURE_WEIGHT, 4)

        # Noisy-or birleşim: iki bağımsız kanıtı BÜYÜKLÜĞÜ koruyarak birleştir.
        # Skor yüksek, kanallardan BİRİ güvenliyse; düşük, ancak İKİSİ de
        # zayıfsa. Böylece kelime tutmayan paraphrase imza kanalından,
        # birebir eşleşme literalden güven kazanır; boş sorgu (iki kanal da
        # zayıf) düşük kalır ve eşikle ayrılabilir. Eski MAX birleşim literali
        # bastırıp imzayı yutuyordu; eski sıra-tabanlı literal skoru da
        # büyüklüğü atıp top1'i her zaman 1.0 yapıyordu — ikisinin kökü buydu.
        scores: dict[str, float] = {}
        for node_id in set(lit) | set(sig):
            miss = (1.0 - lit.get(node_id, 0.0)) * (1.0 - sig.get(node_id, 0.0))
            scores[node_id] = round(1.0 - miss, 4)

        if missing := [n for n in scores if n not in kinds]:
            kinds.update(self._kinds_of(missing))

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
        return [(node_id, score, kinds.get(node_id, "fact")) for node_id, score in ranked]

    def _seed_literal(self, query: str, limit: int) -> list[tuple[str, float, str]]:
        """FTS ile birebir temas. Tarama yok: indeks terimden kayda gidiyor."""
        expression = _match_expression(query)
        if not expression:
            return []
        with self._lock:
            rows = self._db.execute(
                "SELECT n.id, n.kind, n.uses, n.created, n.last_used,"
                " n.kullanimlar, bm25(node_fts) AS rank"
                " FROM node_fts JOIN node n ON n.rowid = node_fts.rowid"
                " WHERE node_fts MATCH ? AND n.deleted=0"
                + self._gecmis_suzgeci("n.")
                + " ORDER BY rank LIMIT ?",
                (expression, limit),
            ).fetchall()

        out: list[tuple[str, float, str]] = []
        for row in rows:
            # bm25 negatif; -rank = eşleşme gücü (büyük = güçlü). SIRA yerine
            # BÜYÜKLÜK: strength/(1+strength) ile 0..1'e sıkıştır. Zayıf ya da
            # rastlantısal bir eşleşme (boş sorgunun ön-ek genişletmesiyle
            # değdiği kayıt gibi) düşük güven alır; güçlü eşleşme 1'e yaklaşır.
            # Eski `1/(1+pozisyon)` en üste her zaman 1.0 veriyordu — eşleşme
            # gücü ne olursa olsun — ve top1 boş/hafıza ayrımını yapamıyordu.
            strength = max(0.0, -float(row["rank"]))
            conf = strength / (1.0 + strength)
            # Canlı iz daha kolay uyanır. Eski hal `min(0.15, 0.03*uses)`
            # idi: zamanı bilmeyen, doyan ve yalnızca EKLEYEN bir aşinalık
            # payı. Yerine aktivasyon çarpanı geçti — en unutulmuş kayıt
            # bile skorunun yarısını koruyor (bkz. aktivasyon.TOHUM_TABANI),
            # yani geride kalıyor ama aramadan düşmüyor.
            carpan = aktivasyon.tohum_carpani(self._taban_seviyesi(row))
            out.append((row["id"], round(min(1.0, conf * carpan), 4), row["kind"]))
        return out

    def _seed_signature(self, query: str, limit: int) -> list[tuple[str, float]]:
        """Cagrisimsal temas: kelime tutmasa da yakin duran kayitlar."""
        # Indeks ozelligi kendi kilidini aliyor; kilit yeniden girilebilir
        # degil, bu yuzden buraya kilit disinda dokunulmali.
        index = self.index
        if not len(index):
            return []
        bulunan = index.search(vector.signature(query), limit)
        if not bulunan:
            return []
        # İmza kanalı yalnız kimlik ve benzerlik döndürüyor; aktivasyon için
        # tek bir toplu sorgu yetiyor (aday sayısı `limit` kadar, onlarca).
        seviye = self._taban_seviyeleri([n for n, _ in bulunan])
        return [(n, round(p * aktivasyon.tohum_carpani(seviye.get(n, aktivasyon.TABAN_YOK)), 4))
                for n, p in bulunan]

    def _taban_seviyeleri(self, node_ids: Sequence[str]) -> dict[str, float]:
        if not node_ids:
            return {}
        placeholders = ",".join("?" * len(node_ids))
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created, last_used, uses, kullanimlar FROM node"
                f" WHERE id IN ({placeholders}) AND deleted=0",
                tuple(node_ids),
            ).fetchall()
        return {row["id"]: self._taban_seviyesi(row) for row in rows}

    def _kinds_of(self, node_ids: Sequence[str]) -> dict[str, str]:
        placeholders = ",".join("?" * len(node_ids))
        with self._lock:
            rows = self._db.execute(
                f"SELECT id, kind FROM node WHERE id IN ({placeholders}) AND deleted=0",
                tuple(node_ids),
            ).fetchall()
        return {row["id"]: row["kind"] for row in rows}


# ---------------------------------------------------------------------


def _match_expression(query: str) -> str:
    """Sorguyu FTS5 ifadesine cevirir.

    Turkce sondan eklemeli oldugu icin ek her iki yonde de gorunuyor:
    kullanici "rapor" yazip kayitta "raporlari" olabilir ya da tersi.
    Bu yuzden her terim iki kez giriyor —

        "rapor"*    terimin kendisi, eki olan kayitlari da tutar
        "rapor"     govde tahmini, terimin kendisi ekli geldiginde tutar

    Kok bulma (stemming) yapilmiyor: Turkce icin duzgun bir kok bulucu ek
    bagimlilik demek ve yanlis kok, hic eslesmemekten daha kotu. Ilk
    STEM_CHARS harf pratikte ayni isi goruyor.

    Terimler OR'laniyor — biri tutan kayit da cagrisimi baslatabilmeli;
    siralamayi zaten bm25 yapiyor.
    """
    # İşlev kelimeleri elenir (imza tarafıyla aynı liste): "bir", "ne" gibi
    # sözcükler FTS'te genel anıları yanlış uyandırıyordu.
    terms = [t for t in (m.group(0) for m in _WORD.finditer(query or ""))
             if len(t) > 1 and t.lower() not in vector.STOPWORDS]
    if not terms:
        return ""

    parts: list[str] = []
    for term in terms:
        parts.append(f'"{term}"*')
        if len(term) > STEM_CHARS:
            parts.append(f'"{term[:STEM_CHARS]}"*')
    # Ayni govdeyi iki kez sormak bm25'i bozmuyor ama ifadeyi sisiriyor.
    return " OR ".join(dict.fromkeys(parts))


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "(başlıksız)")


def _alan(row: sqlite3.Row, ad: str):
    """Satırda olmayabilecek bir sütunu okur.

    Eski bir bellek göç edilmeden okunabilir ya da bir sorgu sütunu
    seçmemiş olabilir; yokluk hata değil, bilgi eksikliği.
    """
    try:
        return row[ad]
    except (IndexError, KeyError):
        return None


def _to_node(row: sqlite3.Row, *, seviye: float = aktivasyon.TABAN_YOK) -> Node:
    return Node(
        aktivasyon=seviye,
        supersedes=_alan(row, "supersedes") or "",
        superseded_by=_alan(row, "superseded_by") or "",
        deleted=bool(_alan(row, "deleted") or 0),
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        body=row["body"],
        tags=[t for t in (row["tags"] or "").split() if t],
        session=row["session"],
        created=row["created"],
        last_used=row["last_used"],
        uses=int(row["uses"]),
    )


def trace_to_json(trace: Sequence[Step]) -> str:
    return json.dumps([asdict(step) for step in trace], ensure_ascii=False)
