"""Beni tanı: kişisel ince ayar döngüsünün ürün içinden zamanlanması.

Eğitim düzeneği ayrı bir depoda yaşıyor (neocp-base-model); gece döngüsü
(hasat → etiket → ince ayar → sınav kapısı → .neocp/taban.npz) orada.
Burası yalnızca **ne zaman** koşacağına karar veriyor: özellik ayarlardan
açılır, bekçi thread'i on beş dakikada bir yoklar ve ya yeterli yeni anı
birikmişse ya da son koşudan bir gün geçmişse (akıllı tetik, aşağıdaki
sabitler) döngüyü düşük öncelikli bir alt süreç olarak başlatır.

Neden schtasks değil: zamanlama üründe durunca kullanıcı tek anahtarla
açıp kapatabiliyor, koşunun başladığı/bittiği arayüzde görünüyor ve
kurulumsuz makinede özellik sessizce pasif kalıyor.

`son_kosu` koşu BİTİNCE yazılıyor: yarıda kesilen (kapanan bilgisayar,
öldürülen süreç) bir koşu tekrarlanabilir kalmalı. Döngünün kendi durumu
(filigran, eşik) zaten kendi deposunda — yarım koşu veri kaybetmez.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DOSYA = "tanima.json"

# Eğitim düzeneğinin yeri. Önce kurulum düzeni: paket <kök>/src/neocp
# altında yaşıyorsa düzenek <kök>/egitim'de aranıyor (Windows kurulum
# sihirbazı oraya koyuyor). Yoksa geliştirici yolu — bu da yoksa özellik
# pasif: ayar sayfası anahtarın yanında "kurulu değil" notu gösteriyor.
_KURULUM_BETIK = (Path(__file__).resolve().parents[2]
                  / "egitim" / "betikler" / "08_kisisel_dongu.py")
_GELISTIRICI_BETIK = (Path("D:/Projects/ai/neocp-base-model")
                      / "betikler" / "08_kisisel_dongu.py")
DONGU_BETIK = _KURULUM_BETIK if _KURULUM_BETIK.exists() else _GELISTIRICI_BETIK

# Döngünün filigranı: en son hangi anıya kadar hasat edildiği burada.
# Yeni anı sayısı buna göre ölçülüyor; dosya/alan yoksa boş filigran —
# her şey yeni sayılır, ilk kurulumda doğru davranış.
FILIGRAN = DONGU_BETIK.parents[1] / "veri" / "kisisel_durum.json"

# Kullanıcıdan damıtılan soru→terim çiftleri: kişisel eğitimin ham maddesi.
# Taşıma (transfer) ve sıfırlama bu iki dosyayı birlikte ele alıyor.
KORPUS = DONGU_BETIK.parents[1] / "veri" / "kisisel_korpus.jsonl"

# Akıllı tetik: yoklamada iki yoldan biri koşturur.
#   (a) filigrandan beri YENI_ANI_ESIGI anı birikti VE son koşudan en az
#       EN_AZ_ARA_SAAT geçti — taze malzeme varken geceyi beklemek boşuna;
#       alt sınır, yoğun bir sohbet gününde döngünün art arda tetiklenip
#       makineyi meşgul etmesini önlüyor.
#   (b) son koşudan TAZELIK_SAAT geçti — günlük tazeleme sigortası: anı
#       birikmese de hasat + eşik yoklaması günde bir kez koşsun.
YENI_ANI_ESIGI = 25
EN_AZ_ARA_SAAT = 2
TAZELIK_SAAT = 20

# Bekçinin adımları: ilk bakış açılışı yavaşlatmasın diye gecikmeli.
ILK_BEKLEME_SN = 60.0
YOKLAMA_SN = 15 * 60.0

# Süreç modül-global: sunucu thread'li ve "zaten koşuyor mu" sorusunun
# tek bir doğru cevabı olmalı.
_surec: subprocess.Popen | None = None
_kilit = threading.Lock()


def durum(state_dir: Path) -> dict:
    try:
        d = json.loads((state_dir / DOSYA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"on": False, "son_kosu": ""}
    return {"on": bool(d.get("on")), "son_kosu": str(d.get("son_kosu") or "")}


def ayarla(state_dir: Path, on: bool) -> None:
    d = durum(state_dir)
    d["on"] = bool(on)
    (state_dir / DOSYA).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def hazir() -> bool:
    """Eğitim düzeneği bu makinede kurulu mu?"""
    return DONGU_BETIK.exists()


def kosuyor() -> bool:
    return _surec is not None and _surec.poll() is None


def _yeni_ani_sayisi(state_dir: Path) -> int:
    """Filigrandan beri biriken anı sayısı (episode hariç).

    Veritabanı SALT OKUNUR açılıyor (hasat/gate kalıbı): bekçinin işi
    saymak, ajanın zihnine dokunmak değil. Okunamayan db/filigran sıfır
    sayılıyor — akıllı yol susar, günlük sigorta yine çalışır.
    """
    db = state_dir / "mind" / "recall.db"
    if not db.exists():
        return 0
    filigran = ""
    try:
        filigran = str(json.loads(FILIGRAN.read_text(encoding="utf-8")).get("son_created") or "")
    except (OSError, ValueError):
        pass
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            (n,) = con.execute(
                "SELECT COUNT(*) FROM node "
                "WHERE kind != 'episode' AND deleted = 0 AND created > ?",
                (filigran,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return 0
    return int(n)


def belki_baslat(state_dir: Path, hub: Any, *, zorla: bool = False) -> bool:
    """Şartlar uygunsa döngüyü başlatır; başlattıysa True.

    `zorla` yalnızca zaman/birikim şartlarını atlar ("şimdi çalıştır"
    düğmesi); kapalı özelliği, eksik düzeneği ya da koşan süreci atlamaz.
    """
    global _surec
    with _kilit:
        d = durum(state_dir)
        if not d["on"] or not hazir() or kosuyor():
            return False
        if not zorla and d["son_kosu"]:
            try:
                son = datetime.fromisoformat(d["son_kosu"])
                gecen = (datetime.now(timezone.utc) - son).total_seconds()
            except ValueError:
                gecen = float("inf")  # bozuk tarih engel olmasın
            # Akıllı tetik: taze malzeme + kısa ara, ya da günlük sigorta.
            if gecen < TAZELIK_SAAT * 3600 and not (
                gecen >= EN_AZ_ARA_SAAT * 3600
                and _yeni_ani_sayisi(state_dir) >= YENI_ANI_ESIGI
            ):
                return False

        # Günlük dosyaya ekleniyor: döngünün kendi çıktısı burada birikiyor
        # ve canlı doğrulamanın baktığı yer de burası.
        gunluk = (state_dir / "tanima.log").open("a", encoding="utf-8")
        # Düşük öncelik + penceresiz: eğitim fark edilmeden koşmalı, fan
        # sesi ve donan arayüz "gece öğrenmesi"nin tam tersi.
        try:
            # Kendi kökümüz betiğe açıkça geçiliyor: kurulum düzeninde
            # 08'in içindeki geliştirici sabiti geçersiz, .neocp/src/eval
            # yolları buradan türetiliyor. Geliştirici düzeninde aynı yol
            # zaten sabitin kendisi — davranış değişmiyor.
            _surec = subprocess.Popen(
                [sys.executable or "py", str(DONGU_BETIK),
                 "--neocp", str(Path(state_dir).resolve().parent)],
                cwd=str(DONGU_BETIK.parents[1]),
                stdout=gunluk, stderr=subprocess.STDOUT,
                creationflags=(subprocess.BELOW_NORMAL_PRIORITY_CLASS
                               | subprocess.CREATE_NO_WINDOW),
            )
        except OSError:
            gunluk.close()
            return False
        surec = _surec

    hub.emit({"type": "tanima", "state": "basladi"})

    def izle() -> None:
        try:
            surec.wait()
        finally:
            gunluk.close()
        # `son_kosu` bitişte: yarım kalan koşu bir sonraki yoklamada
        # yeniden denenebilsin.
        d2 = durum(state_dir)
        d2["son_kosu"] = datetime.now(timezone.utc).isoformat()
        (state_dir / DOSYA).write_text(json.dumps(d2, ensure_ascii=False), encoding="utf-8")
        hub.emit({"type": "tanima", "state": "bitti"})

    threading.Thread(target=izle, daemon=True, name="neo-tanima").start()
    return True


def sifirla(state_dir: Path) -> dict:
    """Beni tanı'yı taban modele döndürür; kişisel olan her şey yedeğe.

    Silinen yok, taşınan var: .neocp/taban.npz ile eğitim düzeneğindeki
    korpus + filigran .neocp/yedek-<tarih>/tanima/ altına gidiyor. Taban
    önbelleği anında düşürülüyor ki 5 dakikalık sıcak yenilemeyi beklemeden
    ürünle gelen assets/taban.npz konuşmaya başlasın.
    """
    if kosuyor():
        return {"ok": False, "error": "Eğitim şu an koşuyor — bitince sıfırla."}

    import shutil

    from .recall import taban

    yedek = Path(state_dir) / f"yedek-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    tasinan: list[str] = []
    for kaynak in (Path(state_dir) / "taban.npz", KORPUS, FILIGRAN):
        if not kaynak.is_file():
            continue
        hedef = yedek / "tanima" / kaynak.name
        hedef.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(kaynak), str(hedef))
        except OSError as exc:
            return {"ok": False, "error": f"Taşınamadı ({kaynak.name}): {exc}",
                    "tasinan": tasinan}
        tasinan.append(kaynak.name)

    taban.sifirla()
    return {"ok": True, "tasinan": tasinan,
            "yedek": str(yedek) if tasinan else ""}


def gozcu_baslat(state_dir: Path, hub: Any) -> None:
    """Bekçi: arka planda on beş dakikada bir belki_baslat'ı yoklar.

    İlk bakış bir dakika gecikmeli — açılış zaten model yüklüyor, bir de
    eğitim yoklaması eklemenin alemi yok. Hata yutuluyor: bekçinin ölmesi
    özelliğin sessizce durması demek ve bunu kimse fark etmez.
    """
    def don() -> None:
        time.sleep(ILK_BEKLEME_SN)
        while True:
            try:
                belki_baslat(state_dir, hub)
            except Exception:
                pass
            time.sleep(YOKLAMA_SN)

    threading.Thread(target=don, daemon=True, name="neo-tanima-gozcu").start()
