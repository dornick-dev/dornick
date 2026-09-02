"""Zaman bazlı aktivasyon — bir izin şu an ne kadar canlı olduğu.

Önceki hal `uses` sayıyordu ve sayı zamanı bilmiyordu: üç yüz gün önce
yazılmış bir kayıt dünkü kadar güçlüydü, çok kullanılmış eski bir kayıt yeni
bir düzeltmeyi ruhun dışında tutabiliyordu. Sayaç bir hatırlama modeli değil,
bir istatistik.

Buradaki formül ACT-R'ın taban seviyesi (base-level activation) denklemi:

    B = ln( Σ_k  t_k^(-d) )

`t_k` her kullanımın üzerinden geçen süre, `d` bozunma üssü. Üç şeyi aynı
anda veriyor ve üçü de insan hafızasında ölçülmüş:

    tazelik      yeni kullanım büyük katkı yapar
    sıklık       her kullanım toplama ayrı bir terim ekler
    aralık       aynı sayıda kullanım zamana yayıldığında daha güçlü iz
                 bırakır (aralıklı tekrar etkisi) — çünkü sıkışık
                 kullanımların hepsi aynı anda eskir

Değişmez: **hiçbir şey kaybolmuyor.** "Unutma" burada aktivasyonun eşik
altına inmesi demek; kayıt diskte durmaya ve açık aramayla bulunmaya devam
ediyor. Tohumlama çarpanı bu yüzden sıfıra değil, yarıya iniyor
(`TOHUM_TABANI`): en unutulmuş kayıt bile skorunun yarısını koruyor, geride
kalıyor ama yok olmuyor.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Iterable, Sequence

from . import anahtar
from .saat import coz

# Bozunma üssü. ACT-R literatürünün standart değeri; insan verisine
# oturtulmuş bir sabit, bu depoya göre ayarlanmadı.
BOZUNMA = 0.5

# `t` saat cinsinden ölçülüyor, gün değil: aynı gün içinde sabah ve akşam
# yapılan iki kullanım da ayrışabilmeli.
TABAN_SANIYE = 3600.0

# Sıfıra bölmeyi ve "az önce kullanıldı"nın sonsuza gitmesini engelleyen
# alt sınır (36 saniye). Aynı zamanda ileri tarihli damgaları da buraya
# kırpıyor — saati geri alınmış bir makinede gelecekten kullanım görünebilir.
EN_AZ_GECEN_SAAT = 0.01

# Hiç kullanımı olmayan kayıt. Matematiksel doğrusu -sonsuz; sonsuzla
# çarpma yapılamayacağı için çok düşük bir sabit.
TABAN_YOK = -10.0

# B'yi 0..1 çarpanına sıkıştıran sigmoidin ölçeği. Küçük değer sert ayrım
# (unutulmuş kayıt neredeyse görünmez), büyük değer yumuşak.
# Kalibrasyon: yaşam bench'inde 0.75 / 1.0 / 2.0 / 3.0 denendi;
# bkz. docs/hafiza-fazlar.md "Faz 1 kalibrasyonu". Sihirli sayı değil,
# ölçülmüş seçim.
OLCEK = 2.0

# Tohumlama skorunun aktivasyondan bağımsız kalan payı. 0.5: en unutulmuş
# kayıt bile skorunun yarısını korur. Sıfır olsaydı eski kayıtlar aramadan
# tamamen düşerdi — mezar taşı felsefesinin ihlali.
TOHUM_TABANI = 0.5

# Kullanım geçmişinde tutulan azami damga. Sütun sınırsız büyümemeli;
# yirmi kullanımın ötesindeki terimler toplamı kayda değer biçimde
# değiştirmiyor (en eskiler zaten en küçük katkıyı yapıyor).
AZAMI_KULLANIM = 20


def taban_aktivasyon(kullanimlar: Sequence[datetime], simdi: datetime) -> float:
    """B = ln( Σ t_k^(-d) ). Kullanım yoksa `TABAN_YOK`."""
    toplam = 0.0
    for an in kullanimlar:
        gecen = max((simdi - an).total_seconds() / TABAN_SANIYE, EN_AZ_GECEN_SAAT)
        toplam += gecen ** (-BOZUNMA)
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
    yarıyı korumakla bunun çelişkisi yok — orada kaydın KENDİSİ aranıyor,
    burada üzerinden geçiliyor.
    """
    if not anahtar.AKTIF.aktivasyon:
        return 1.0
    return aktivasyon_carpani(b)


def coz_kullanimlar(
    ham: Any,
    *,
    created: str | None = None,
    last_used: str | None = None,
    uses: int = 0,
) -> list[datetime]:
    """Diskteki kullanım geçmişini okunur hale getirir.

    Üç biçime birden dayanıklı olmak zorunda:

    * bu sürümün yazdığı ISO damga dizisi,
    * Faz 4'ün yazacağı ağırlıklı girdiler (`{"t": ..., "w": ...}`),
    * sütunun hiç olmadığı eski bir bellek — o zaman
      `created` + `last_used` × `uses` ile kabaca geriye dönük üretiliyor.

    Üçüncüsü şart: sütun eklenince bütün eski hatıralar bir anda "hiç
    kullanılmamış" sayılsaydı, kullanıcının yıllarca biriktirdiği bellek
    tek bir sürüm yükseltmesinde sıfırlanmış gibi davranırdı.
    """
    girdiler = _girdiler(ham)
    if girdiler:
        return girdiler
    return _geriye_donuk(created, last_used, uses)


def _girdiler(ham: Any) -> list[datetime]:
    if isinstance(ham, str):
        if not ham.strip():
            return []
        try:
            ham = json.loads(ham)
        except ValueError:
            return []
    if not isinstance(ham, list):
        return []
    out: list[datetime] = []
    for girdi in ham:
        metin = girdi.get("t") if isinstance(girdi, dict) else girdi
        if (an := coz(metin if isinstance(metin, str) else None)) is not None:
            out.append(an)
    return sorted(out)


def _geriye_donuk(created: str | None, last_used: str | None, uses: int) -> list[datetime]:
    """Sütunsuz bir kaydın kaba kullanım geçmişi.

    Yazım anı ilk kullanımdır; kalan `uses` kadar kullanım da en son
    kullanım anına yığılıyor. Gerçek dağılım bilinmiyor — bilinmeyeni
    uydurmak yerine en muhafazakâr varsayım: hepsi aynı anda oldu (sıkışık
    kullanım, aralıklıdan zayıf iz bırakır).
    """
    yazim = coz(created)
    son = coz(last_used)
    out: list[datetime] = []
    if yazim is not None:
        out.append(yazim)
    if son is not None:
        out.extend([son] * max(0, min(int(uses or 0), AZAMI_KULLANIM - len(out))))
    return sorted(out)


def damgala(kullanimlar: Iterable[datetime], yeni: str) -> str:
    """Kullanım geçmişine yeni bir damga ekleyip diske yazılacak JSON'u verir."""
    damgalar = [an.isoformat(timespec="milliseconds") for an in kullanimlar]
    damgalar.append(yeni)
    return json.dumps(damgalar[-AZAMI_KULLANIM:], ensure_ascii=False)


def ilk_damga(created: str) -> str:
    """Yeni kaydın kullanım geçmişi: yazım anı ilk kullanımdır."""
    return json.dumps([created], ensure_ascii=False)
