"""Şema göçü: kullanıcının diskindeki bellek sürüm yükseltmesinde açılmalı.

Bu dosya her fazda aynı işi yapıyor: `tests/fixtures/recall-v1.db` — `sig`
sütunu daha eklenmemişken yazılmış gerçek bir şema — açılıyor ve
`recall()` çağrılıyor. Göç sessiz ve geri dönüşsüz veri kaybı olmadan
geçmeli. Bir fazın eklediği sütun eski dosyayı açılamaz yaparsa kullanıcı
hatıralarını kaybeder; bu test o günü engellemek için var.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dornick.recall import RecallStore

FIKSTUR = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"

# Fikstürde ne olduğu (elle yazıldı, dondurulmuş).
BEKLENEN_CANLI = 7          # bir kayıt mezar taşı
BEKLENEN_TOPLAM = 8


@pytest.fixture()
def eski_db(tmp_path: Path) -> Path:
    """Fikstürün kopyası — test dosyanın kendisini değiştirmesin."""
    hedef = tmp_path / "recall.db"
    shutil.copy2(FIKSTUR, hedef)
    return hedef


def test_eski_bellek_acilir_ve_hatirlar(eski_db: Path) -> None:
    store = RecallStore(eski_db)
    try:
        assert store.count() == BEKLENEN_CANLI
        sonuc = store.recall("SCADA WinCC", limit=5)
        kimlikler = {n.id for n in sonuc.hits}
        assert "n_v1scada" in kimlikler
    finally:
        store.close()


def test_goc_hicbir_kaydi_dusurmez(eski_db: Path) -> None:
    """Yeni sütun eklemek satır silmemeli — mezar taşı bile yerinde kalmalı."""
    store = RecallStore(eski_db)
    try:
        store.recall("rapor")           # göçü ve imza doldurmayı tetikler
        with store._lock:               # noqa: SLF001 — göç doğrulaması
            toplam = store._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            silik = store._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=1").fetchone()[0]
        assert toplam == BEKLENEN_TOPLAM
        assert silik == 1
    finally:
        store.close()


def test_eski_kayitlarin_alanlari_korunur(eski_db: Path) -> None:
    store = RecallStore(eski_db)
    try:
        node = store.peek("n_v1rapor")
        assert node is not None
        assert node.body == "Raporları PDF olarak istiyorum."
        assert node.kind == "preference"
        assert node.uses == 2
        assert node.created.startswith("2024-11")
        assert node.last_used is not None
    finally:
        store.close()


def test_imzalar_geriye_donuk_uretilir(eski_db: Path) -> None:
    """v1'de `sig` sütunu yoktu; ilk aramada üretilip diske yazılmalı."""
    store = RecallStore(eski_db)
    try:
        store.recall("kedi")
        with store._lock:               # noqa: SLF001 — göç doğrulaması
            imzasiz = store._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=0 AND sig IS NULL"
            ).fetchone()[0]
        assert imzasiz == 0
    finally:
        store.close()


def test_eski_bellege_yazilabilir(eski_db: Path) -> None:
    """Göçten sonra bellek salt okunur bir kalıntı değil, çalışan bir bellek."""
    store = RecallStore(eski_db)
    try:
        yeni = store.remember("göçten sonra yazılan kayıt", kind="fact")
        assert store.peek(yeni.id) is not None
        assert store.count() == BEKLENEN_CANLI + 1
    finally:
        store.close()
