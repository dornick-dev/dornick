r"""Sabit korumalar — izin kipinden BAĞIMSIZ, aşılamaz retler.

İzin motorunun `allow`/`yolo` dalları kullanıcının kendi gevşetmesidir;
ama birkaç hedef vardır ki hiçbir kipte, hiçbir kuralla açılmamalı çünkü
açılması güvenlik modelinin kendisini çökertir:

  * `.dornick/keys.json` — API anahtarları ve posta parolası. Okunması bile
    tehlikeli: bir araç sonucuna düşen sır, injection'la bir sonraki `fetch`
    URL'sine (sorgu dizesi = kanal) konup dışarı sızabilir. Bu dosyaya
    dokunan HİÇBİR aracın meşru gerekçesi yok — uygulama anahtarları kendi
    içinde okuyor, araçla değil.
  * `.dornick/config.json`, `.dornick/gate.json` — izin kipini, allow/deny
    kurallarını, dış kapı anahtarını tutuyor. Buraya YAZMAK, modelin kendi
    kapısını `yolo`'ya çekmesi demek. Okumak serbest (model hangi kuralın
    altında olduğunu görebilmeli); yazmak/kabuk sabit ret.
  * Windows açılış kalıcılığı (`...CurrentVersion\Run`) ve Başlangıç
    klasörü — makinede kalıcı kod. Kabuk/mutasyon buraya uzanamaz.

Bu bir HAPİS DEĞİL, kancalar.py'deki gibi bir "kasıt kapısı": adı gizleyen
bir kabuk komutu (base64, değişkene atama) teorik olarak aşar. Kapattığı
şey gerçek başarısızlık kipi — prompt injection'ın ya da fazla uyumlu bir
modelin DOĞRUDAN, tek adımda sırrı okuyup göndermesi / kipi yükseltmesi.
Kasıtlı bir düşmana karşı asıl çit işletim sistemi seviyesindedir.
"""

from __future__ import annotations

import re
from typing import Any

# Okunması da yazılması da sabit ret olan dosyalar (yol içinde .dornick ile).
_SIR = re.compile(r"\.dornick[\\/]keys\.json", re.IGNORECASE)

# Yalnız YAZMA/kabuk sabit ret; okuma serbest. skills_onayli.json da burada:
# yetenek onay manifesti — araç yazabilseydi injection dosyayı da karmasını
# da yazıp açılış-exec korumasını aşardı.
_AYAR = re.compile(
    r"\.dornick[\\/](?:config|gate|skills_onayli)\.json", re.IGNORECASE)

# Kalıcılık yüzeyleri: kabuk/mutasyon uzanamaz.
_KALICILIK = re.compile(
    r"currentversion[\\/]run\b"                 # HKCU/HKLM ...Run
    r"|start menu[\\/]programs[\\/]startup",    # Başlangıç klasörü
    re.IGNORECASE,
)

# Bu araçlar diske yazabilir ya da komut çalıştırabilir — "yazma yüzeyi".
# Mutasyon bayrağı taşımayan ama yazma/çalıştırma yapan araçlar da burada.
_YAZMA_YUZEYI = frozenset({
    "shell", "write_file", "edit_file", "copy_in", "hand", "git",
})


def _degerler(girdi: Any) -> list[str]:
    """Girdinin içindeki tüm string değerleri (iç içe sözlük/liste dahil).

    Özne çıkarımı (SUBJECT_KEYS) yetmiyor: `copy_in` kaynağı `source`
    alanında, `http` düğümü `url`'de — hepsi taranmalı, yoksa keys.json'a
    `source` ile uzanan bir çağrı kapıdan sızar."""
    out: list[str] = []
    yigin = [girdi]
    while yigin:
        p = yigin.pop()
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            yigin.extend(p.values())
        elif isinstance(p, (list, tuple)):
            yigin.extend(p)
    return out


def sabit_ret(arac: str, mutasyon: bool, girdi: Any) -> str | None:
    """Bu çağrı sabit korumalardan birini ihlal ediyor mu?

    Dönüş: ihlal varsa insan diliyle gerekçe (izin motoru bunu DENY olarak
    kullanır ve kipe hiç bakmaz), yoksa None.
    """
    degerler = _degerler(girdi)
    if not degerler:
        return None
    yazabilir = mutasyon or arac in _YAZMA_YUZEYI

    for d in degerler:
        if _SIR.search(d):
            return (
                "Bu çağrı `.dornick/keys.json` dosyasına uzanıyor ve sabit "
                "olarak engellendi — bu dosya API anahtarlarını ve posta "
                "parolasını tutuyor, ne okunur ne kopyalanır. Sırlara bir "
                "aracın işi için gerek yok; bir kimlik gerekiyorsa kullanıcıya "
                "sor, dosyayı okuma."
            )
    if not yazabilir:
        return None  # geri kalanı yalnız yazma/kabuk için
    for d in degerler:
        if _AYAR.search(d):
            return (
                "Bu çağrı `.dornick` ayar/kapı dosyasına YAZMAYA çalışıyor ve "
                "sabit olarak engellendi — izin kipi, kurallar ve dış kapı "
                "buradan yönetilir; bir araçla değiştirilmesi güvenlik kapısını "
                "kendi kendine açmak olurdu. Kip/kural değişikliği kullanıcının "
                "işidir (Ayarlar)."
            )
        if _KALICILIK.search(d):
            return (
                "Bu çağrı Windows açılış kalıcılığına (Run anahtarı / Başlangıç "
                "klasörü) yazmaya çalışıyor ve sabit olarak engellendi — "
                "makinede kalıcı, kullanıcının görmediği kod bırakmak bu "
                "araçların işi değil. Gerçekten gerekliyse kullanıcıya söyle."
            )
    return None
