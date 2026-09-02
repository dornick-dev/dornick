"""Zaman bazlı aktivasyon — bir izin şu an ne kadar canlı olduğu.

Önceki hal `uses` sayıyordu ve sayı zamanı bilmiyordu: üç yüz gün önce
yazılmış bir kayıt dünkü kadar güçlüydü, çok kullanılmış eski bir kayıt yeni
bir düzeltmeyi ruhun dışında tutabiliyordu. Sayaç bir hatırlama modeli değil,
bir istatistik.

Buradaki formül ACT-R'ın taban seviyesi denklemi, ağırlıklı hâliyle:

    B = ln( Σ w_k · t_k^(-d) )

`t_k` her kullanımın üzerinden geçen süre, `d` bozunma üssü, `w_k` o
kullanımın ağırlığı. Dört şeyi aynı anda veriyor:

    tazelik      yeni kullanım büyük katkı yapar
    sıklık       her kullanım toplama ayrı bir terim ekler
    aralık       aynı sayıda kullanım zamana yayıldığında daha güçlü iz
                 bırakır (aralıklı tekrar etkisi) — sıkışık kullanımların
                 hepsi aynı anda eskir
    sorumluluk   ağırlık negatif olabilir: hataya götüren bir kullanım izi
                 zayıflatır (Faz 3 ters tekrarı). Faz 1'de her ağırlık 1.0
                 ve formül klasik ACT-R'a indirgenir.

Değişmez: **hiçbir şey kaybolmuyor.** "Unutma" burada aktivasyonun eşik
altına inmesi demek; kayıt diskte durmaya ve açık aramayla bulunmaya devam
ediyor. Tohumlama çarpanı bu yüzden sıfıra değil, yarıya iniyor
(`TOHUM_TABANI`): en unutulmuş kayıt bile skorunun yarısını koruyor, geride
kalıyor ama yok olmuyor. Ağırlıklı toplam sıfırın altına inse bile (yalnız
hatalar) sabit bir taban dönüyor — hataya götüren hatıra da silinmiyor,
yanında bir `lesson` ile geride kalıyor.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from . import anahtar
from .saat import coz

# Bozunma üssü. ACT-R literatürünün standart değeri 0.5'tir ve o değer
# saniyeler–dakikalar ölçeğindeki laboratuvar verisine oturtulmuştur; burada
# `t` aylar boyunca saat cinsinden ölçülüyor ve o rejimde 0.5 fazla yavaş
# kalıyor: haftalık bir düzeltme, aylardır düzenli kullanılan bir yordamın
# altında kalıyordu.
# Kalibrasyon (yaşam bench, 2026-09-02, `--etiket f1`): 0.5 / 0.6 / 0.8 /
# 0.9 / 1.0 / 1.1 tarandı. `taze_ruh` 0.68 → 0.72 → 0.78 → 0.81 → 0.82 →
# 0.83; `prime_precision` 0.9'da tepe yapıyor (0.2634), 1.0'dan sonra
# `yasak_sizinti` 57'den 58'e çıkıyor. Diz noktası seçildi.
# Bkz. docs/hafiza-fazlar.md "Faz 1 kalibrasyonu".
BOZUNMA = 0.9

# `t` saat cinsinden ölçülüyor, gün değil: aynı gün içinde sabah ve akşam
# yapılan iki kullanım da ayrışabilmeli.
TABAN_SANIYE = 3600.0

# Sıfıra bölmeyi ve "az önce kullanıldı"nın sonsuza gitmesini engelleyen alt
# sınır (36 saniye). İleri tarihli damgalar da buraya kırpılıyor — saati geri
# alınmış bir makinede gelecekten kullanım görünebilir.
EN_AZ_GECEN_SAAT = 0.01

# Hiç kullanımı olmayan ya da net ağırlığı sıfırın altına inmiş kayıt.
# Matematiksel doğrusu -sonsuz; sonsuzla çarpma yapılamayacağı için sabit.
TABAN_YOK = -10.0

# B'yi 0..1 çarpanına sıkıştıran sigmoidin ölçeği.
# Kalibrasyon (yaşam bench, 2026-09-02): OLCEK ∈ {0.75, 1.0, 1.5, 2.0, 3.0,
# 4.0, 5.0} tarandı; metrikler 1.0–4.0 platosunda birbirinden ayrışmıyor
# (fark ≤ 0.002), uçlar hafifçe kötü. Kalibrasyonun kendi bulgusu şu:
# sonuçlar bu sabite karşı DUYARSIZ — mekaniğin faydası sıralamanın zamanı
# bilmesinden geliyor, sigmoidin dikliğinden değil. Plato ortası seçildi.
OLCEK = 2.0

# Tohumlama skorunun aktivasyondan bağımsız kalan payı. 0.5: en unutulmuş
# kayıt bile skorunun yarısını korur. Sıfır olsaydı eski kayıtlar aramadan
# tamamen düşerdi — mezar taşı felsefesinin ihlali.
TOHUM_TABANI = 0.5

# Kullanım geçmişinde tutulan azami damga (yol haritası 1.1). Sütun sınırsız
# büyümemeli; otuz kullanımın ötesindeki terimler toplamı kayda değer biçimde
# değiştirmiyor — en eskiler zaten en küçük katkıyı yapıyor.
AZAMI_KULLANIM = 30

# Kullanım etiketleri. Faz 1 yalnız ilk ikisini yazar; kalanlar Faz 3'ün
# (ters tekrar, şema tazelemesi, yakalama) ve Faz 4'ün alanı. Alan baştan bu
# biçimde açılıyor ki sonraki fazlar şema değiştirmesin.
YAZILDI = "yazildi"
ACILDI = "acildi"
BASARI = "basari"
HATA = "hata"
SEMA = "sema"
YAKALANDI = "yakalandi"
# Damıtma kaynağı: özü kısa bir `fact`a taşındı, kendisi arka plana çekildi.
# Kendi etiketi olmalı — `sema` sayılsaydı şema tazelemesinin ölçümü
# damıtmanın geri çekmesiyle karışırdı (ölçüldü: `sema_tazeleme` eksiye
# düşüyordu).
DAMITILDI = "damitildi"
ETIKETLER = (YAZILDI, ACILDI, BASARI, HATA, SEMA, YAKALANDI, DAMITILDI)


@dataclass(frozen=True, slots=True)
class Kullanim:
    """Bir izin bir kez uyandığı an."""

    t: datetime
    w: float = 1.0
    etiket: str = ACILDI

    def sozluk(self) -> dict[str, Any]:
        return {"t": self.t.isoformat(timespec="milliseconds"),
                "w": round(self.w, 4), "etiket": self.etiket}


def taban_aktivasyon(kullanimlar: Sequence[Kullanim], simdi: datetime) -> float:
    """B = ln( Σ w_k · t_k^(-d) ). Toplam ≤ 0 ise `TABAN_YOK`."""
    toplam = 0.0
    for k in kullanimlar:
        gecen = max((simdi - k.t).total_seconds() / TABAN_SANIYE, EN_AZ_GECEN_SAAT)
        toplam += k.w * gecen ** (-BOZUNMA)
    return math.log(toplam) if toplam > 0.0 else TABAN_YOK


def aktivasyon_carpani(b: float) -> float:
    """B'yi (0, 1) aralığına sıkıştırır: sigmoid(B / OLCEK)."""
    x = max(-60.0, min(60.0, b / OLCEK))
    return 1.0 / (1.0 + math.exp(-x))


def tohum_carpani(b: float) -> float:
    """Tohumlama skoru bununla çarpılır: `TOHUM_TABANI`..1 arası.

    Mekanik kapalıyken 1.0 — ablation koşusu ürünün kendi kodundan geçsin,
    bench'e kopyalanmış bir "aktivasyonsuz sürüm"den değil.
    """
    if not anahtar.AKTIF.aktivasyon:
        return 1.0
    return TOHUM_TABANI + (1.0 - TOHUM_TABANI) * aktivasyon_carpani(b)


def yayilma_carpani(b: float) -> float:
    """Çağrışım yayılırken komşunun ilettiği pay.

    Burada taban YOK: unutulmuş bir düğüm yolu iletmemeli. Tohumlamada
    yarıyı korumakla çelişmiyor — orada kaydın KENDİSİ aranıyor, burada
    üzerinden geçiliyor.
    """
    if not anahtar.AKTIF.aktivasyon:
        return 1.0
    return aktivasyon_carpani(b)


# -- diskteki biçim ----------------------------------------------------


def coz_kullanimlar(
    ham: Any,
    *,
    created: str | None = None,
    last_used: str | None = None,
    uses: int = 0,
) -> list[Kullanim]:
    """Diskteki kullanım geçmişini okunur hale getirir.

    Üç biçime birden dayanıklı olmak zorunda:

    * bu sürümün yazdığı ağırlıklı girdiler (`{"t", "w", "etiket"}`),
    * yalın ISO damga dizisi (biçim değişmeden önce yazılmış bir bellek),
    * sütunun hiç olmadığı eski bir bellek — o zaman `created` +
      `last_used` × `uses` ile kabaca geriye dönük üretiliyor.

    Üçüncüsü şart: sütun eklenince bütün eski hatıralar bir anda "hiç
    kullanılmamış" sayılsaydı, kullanıcının yıllarca biriktirdiği bellek tek
    bir sürüm yükseltmesinde sıfırlanmış gibi davranırdı.
    """
    girdiler = _girdiler(ham)
    if girdiler:
        return girdiler
    return _geriye_donuk(created, last_used, uses)


def _girdiler(ham: Any) -> list[Kullanim]:
    if isinstance(ham, str):
        if not ham.strip():
            return []
        try:
            ham = json.loads(ham)
        except ValueError:
            return []
    if not isinstance(ham, list):
        return []
    out: list[Kullanim] = []
    for girdi in ham:
        if isinstance(girdi, dict):
            an = coz(girdi.get("t") if isinstance(girdi.get("t"), str) else None)
            if an is None:
                continue
            try:
                w = float(girdi.get("w", 1.0))
            except (TypeError, ValueError):
                w = 1.0
            etiket = str(girdi.get("etiket") or ACILDI)
            out.append(Kullanim(an, w, etiket))
        elif isinstance(girdi, str):
            if (an := coz(girdi)) is not None:
                out.append(Kullanim(an, 1.0, ACILDI))
    out.sort(key=lambda k: k.t)
    return out


def _geriye_donuk(created: str | None, last_used: str | None,
                  uses: int) -> list[Kullanim]:
    """Sütunsuz bir kaydın kaba kullanım geçmişi.

    Yazım anı ilk kullanımdır; kalan `uses` kadar kullanım da en son kullanım
    anına yığılıyor. Gerçek dağılım bilinmiyor — bilinmeyeni uydurmak yerine
    en muhafazakâr varsayım: hepsi aynı anda oldu (sıkışık kullanım,
    aralıklıdan zayıf iz bırakır).
    """
    out: list[Kullanim] = []
    if (yazim := coz(created)) is not None:
        out.append(Kullanim(yazim, 1.0, YAZILDI))
    if (son := coz(last_used)) is not None:
        kalan = max(0, min(int(uses or 0), AZAMI_KULLANIM - len(out)))
        out.extend(Kullanim(son, 1.0, ACILDI) for _ in range(kalan))
    out.sort(key=lambda k: k.t)
    return out


def kodla(kullanimlar: Iterable[Kullanim]) -> str:
    """Diske yazılacak JSON. Son `AZAMI_KULLANIM` girdi tutulur."""
    liste = list(kullanimlar)[-AZAMI_KULLANIM:]
    return json.dumps([k.sozluk() for k in liste], ensure_ascii=False)


def ekle(kullanimlar: Iterable[Kullanim], an: datetime, *, w: float = 1.0,
         etiket: str = ACILDI) -> str:
    """Geçmişe yeni bir kullanım ekleyip diske yazılacak JSON'u verir."""
    return kodla([*kullanimlar, Kullanim(an, float(w), etiket)])


# Faz 4 — kodlama gücü. Her kayıt aynı ağırlıkla doğuyordu: "aynı şeyi beş
# kez kaydettim" dendiğinde beşinci kayıt da tam güçteydi. Güç artık
# sürprizden geliyor — bilinene benzeyen zayıf, yeni olan güçlü kodlanıyor.
# Taban asla sıfır değil: bilinen bir şeyi tekrar duymak da bir bilgidir.
KODLAMA_TABANI = 0.4
KODLAMA_ARALIGI = 0.6
# Hatadan öğrenme ağır basar: aynı gövde `lesson` olarak daha güçlü kodlanır.
DERS_CARPANI = 1.5


def kodlama_gucu(surpriz: float, *, kind: str = "fact",
                 supersedes: str = "") -> float:
    """Yeni bir kaydın doğum ağırlığı.

    `supersedes` tam güç: bir düzeltme, düzelttiği şeye ne kadar benzerse
    benzesin zayıf kodlanmamalı — zaten benzediği için düzeltmedir.
    """
    if not anahtar.AKTIF.kodlama:
        return 1.0
    if supersedes:
        return 1.0
    guc = KODLAMA_TABANI + KODLAMA_ARALIGI * max(0.0, min(1.0, surpriz))
    if kind == "lesson":
        guc = min(1.0, guc * DERS_CARPANI)
    return round(guc, 4)


def ilk_damga(created: str, guc: float = 1.0) -> str:
    """Yeni kaydın kullanım geçmişi: yazım anı ilk kullanımdır.

    Ağırlık kodlama gücü (Faz 4): `taban_aktivasyon` zaten ağırlıklı toplam
    alıyor, o yüzden şema değişmiyor — yalnız ilk girdinin `w`si değişiyor.
    """
    return json.dumps([{"t": created, "w": round(float(guc), 4),
                        "etiket": YAZILDI}], ensure_ascii=False)


def sicil(kullanimlar: Sequence[Kullanim]) -> tuple[int, int]:
    """(başarı, hata) sayacı — `mind_recall` çıktısında modele gösterilir."""
    basari = sum(1 for k in kullanimlar if k.etiket == BASARI)
    hata = sum(1 for k in kullanimlar if k.etiket == HATA)
    return basari, hata
