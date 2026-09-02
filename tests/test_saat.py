"""Enjekte edilebilir saat.

Hafızanın bundan sonraki bütün mekaniği (bozunma, pekişme, tazelik) zamana
bakıyor. Zaman doğrudan `datetime.now()` ile okunursa "otuz gün sonra ne
olur" sorusu ancak otuz gün beklenerek yanıtlanabilir — yani hiç. Buradaki
testler enjekte edilen saatin diske yazılan HER damgaya ulaştığını ve
doğrudan çağrının geri sızmadığını zorluyor.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dornick.mind import open_mind
from dornick.recall import open_store
from dornick.recall.saat import coz, damga

KOK = Path(__file__).resolve().parents[1]


class Takvim:
    """Elle ilerletilen saat."""

    def __init__(self, baslangic: datetime) -> None:
        self.an = baslangic

    def __call__(self) -> datetime:
        return self.an

    def gun_ekle(self, gun: int) -> None:
        self.an += timedelta(days=gun)


BASLANGIC = datetime(2025, 1, 6, 9, 0, tzinfo=timezone.utc)


# -- depo --------------------------------------------------------------


def test_enjekte_saat_created_alanina_ulasir(tmp_path: Path) -> None:
    takvim = Takvim(BASLANGIC)
    store = open_store(tmp_path, saat=takvim)
    try:
        node = store.remember("ilk gün yazılan kayıt", kind="fact")
        assert node.created.startswith("2025-01-06T09:00")
        takvim.gun_ekle(40)
        sonraki = store.remember("kırk gün sonra yazılan kayıt", kind="fact")
        assert sonraki.created.startswith("2025-02-15T09:00")
    finally:
        store.close()


def test_enjekte_saat_last_used_alanina_ulasir(tmp_path: Path) -> None:
    takvim = Takvim(BASLANGIC)
    store = open_store(tmp_path, saat=takvim)
    try:
        node = store.remember("kullanılacak kayıt", kind="fact")
        takvim.gun_ekle(10)
        store.open(node.id)
        tazelenmis = store.peek(node.id)
        assert tazelenmis is not None
        assert tazelenmis.last_used.startswith("2025-01-16")
        assert tazelenmis.uses == 1
        # Yazım anı geride kaldı: kullanım onu değiştirmiyor.
        assert tazelenmis.created.startswith("2025-01-06")
    finally:
        store.close()


def test_saat_verilmezse_duvar_saati(tmp_path: Path) -> None:
    """Ürün davranışı değişmemeli: parametre verilmeyince gerçek zaman."""
    store = open_store(tmp_path)
    try:
        node = store.remember("bugün yazıldı", kind="fact")
        yazim = coz(node.created)
        assert yazim is not None
        assert abs((datetime.now(timezone.utc) - yazim).total_seconds()) < 60
    finally:
        store.close()


# -- zihin -------------------------------------------------------------


def test_zihin_saati_depoya_ve_hedeflere_gecirir(tmp_path: Path) -> None:
    takvim = Takvim(BASLANGIC)
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "t", saat=takvim)
    try:
        hafiza = mind.remember("kullanıcı Ankara'da yaşıyor", kind="user")
        hedef = mind.push_goal("kurulum paketini imzala")
        assert hafiza.ts.startswith("2025-01-06")
        assert hedef.ts.startswith("2025-01-06")

        takvim.gun_ekle(30)
        sonraki = mind.remember("kullanıcı taşındı", kind="user")
        kapanan = mind.set_goal_status(hedef.id, "done")
        assert sonraki.ts.startswith("2025-02-05")
        assert kapanan is not None and kapanan.ts.startswith("2025-02-05")
    finally:
        mind.store.close()


def test_zihin_ve_depo_ayni_saati_gorur(tmp_path: Path) -> None:
    """İki katman farklı takvimlerden okusa tazelik sıralaması bozulurdu."""
    takvim = Takvim(BASLANGIC)
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "t", saat=takvim)
    try:
        assert mind.store._saat is takvim
        assert mind._simdi() == damga(takvim)
    finally:
        mind.store.close()


# -- kural -------------------------------------------------------------


def test_dogrudan_datetime_now_cagrisi_kalmadi() -> None:
    """`_now()` yerine `_simdi()`.

    Yeni bir mekanik yazarken doğrudan `datetime.now()` çağırmak, o mekaniği
    sessizce ölçülemez yapar — benchmark sanal saati o çağrıya ulaşamaz.
    Kural grep ile zorlanıyor; tek istisna `recall/saat.py`, zamanın okunduğu
    tek yer.
    """
    for goreli in ("src/dornick/recall/store.py", "src/dornick/mind/store.py"):
        # Yorum satırları elenir: kuralı ANLATAN bir yorum kuralı çiğnemiş
        # sayılmamalı.
        satirlar = [
            satir
            for satir in (KOK / goreli).read_text(encoding="utf-8").splitlines()
            if not satir.lstrip().startswith("#")
        ]
        bulunan = re.findall(r"datetime\.now\(", " ".join(satirlar))
        assert not bulunan, (
            f"{goreli}: doğrudan datetime.now() çağrısı var. "
            "Zamanı `self._simdi()` üzerinden oku (bkz. recall/saat.py)."
        )
