"""Sesli konuşma.

İşletim sisteminin kendi sentezleyicisi (Windows'ta SAPI) robot gibi
konuşuyor — bir asistanla değil bir santral kaydıyla konuşuyormuş hissi
veriyor. Burada Microsoft'un sinirsel sesleri kullanılıyor: Türkçe için
`tr-TR-EmelNeural` ve `tr-TR-AhmetNeural`, ikisi de gerçek insan tonunda.

Bedeli internet: ses bulutta üretiliyor. Ağ yoksa konuşma sessizce kapanıyor,
metin yerinde duruyor — sesin olmaması işi durdurmamalı.

Sesletilecek metin ekrandaki metinle aynı değil. Kod bloğunu sesli okumak
anlamsız ("üç ters tırnak powershell dolar u r l eşittir…"), tablo da öyle.
`speakable()` bunları atıyor ve geriye konuşulabilir olan kalıyor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Ses üreten paket isteğe bağlı: kurulu değilse konuşma kapalı kalıyor,
# program çalışmaya devam ediyor.
INSTALL_HINT = "Sesli konuşma için: pip install 'dornick[voice]'"


def hint() -> str:
    """Eksik-paket mesajı: kurulu düzende pip değil onarım önerilir.

    edge-tts kurulum paketine dahil; kuruluda yokluğu eksik/bozuk bir
    kurulum demek — sihirbazı yeniden çalıştırmak onarır.
    """
    from . import environment

    if environment.kurulu_mu():
        return ("Ses paketi bu kurulumda eksik görünüyor. Kurulum "
                "sihirbazını yeniden çalıştırmak eksiği onarır.")
    return INSTALL_HINT

DEFAULT_VOICE = "tr-TR-EmelNeural"

# Bir seferde sesletilecek azami karakter. Uzun metin hem gecikme hem de
# kesilemeyen bir monolog demek; cümle cümle gönderiliyor zaten.
MAX_CHARS = 1200

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`]*`")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_MARK = re.compile(r"[*_#>~]+")
_PATH = re.compile(r"\S*[\\/]\S*[\\/]\S*")
_BLANK = re.compile(r"\n{2,}")
_SPACES = re.compile(r"[ \t]{2,}")


@dataclass(slots=True)
class VoiceConfig:
    """Sesli konuşma ayarları.

    enabled: kapalı geliyor. Kendiliğinden konuşmaya başlayan bir program
        rahatsız edici; açmak kullanıcının kararı.
    rate/pitch: edge-tts biçimi ("+0%", "-10%", "+5Hz"). Hız kişiye göre
        çok değişiyor — kimi 1.0'da yavaş buluyor.
    """

    enabled: bool = False
    name: str = DEFAULT_VOICE
    rate: str = "+0%"
    pitch: str = "+0Hz"
    # Sesin karakteri: 0 saf insan, 1 tamamen makine. Sentezleyici insan
    # sesi üretiyor ve düz okuyor; bu değer tarayıcıda sesin üstüne bir
    # katman ekliyor (ikizleme, tını, hafif titreşim). Ortada bir yerde
    # duruyor: ne santral kaydı ne de birebir insan taklidi.
    character: float = 0.35


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def speakable(text: str, limit: int = MAX_CHARS) -> str:
    """Ekrandaki metinden sesletilecek olanı çıkarır.

    Kod bloğunu sesli okumak anlamsız; tablo, adres ve dosya yolu da öyle.
    Bunlar atılıyor ve yerlerine bir şey konmuyor: "kod bloğu" diye
    seslendirmek de her cevapta tekrarlanan bir gürültü olurdu.
    """
    out = _FENCE.sub(" ", text or "")
    out = _TABLE_ROW.sub(" ", out)
    out = _INLINE_CODE.sub(" ", out)
    # Bağlantıda okunacak şey metni, adresi değil.
    out = _LINK.sub(r"\1", out)
    out = _URL.sub(" ", out)
    out = _PATH.sub(" ", out)
    out = _MARK.sub("", out)
    out = _SPACES.sub(" ", out)
    out = _BLANK.sub("\n", out)
    out = "\n".join(line.strip() for line in out.splitlines() if line.strip())
    return out[:limit].strip()


# Cümlenin tonu. Türkçe seslerde SSML duygu stili yok (hepsi "General"),
# ama hız ve perde cümle cümle ayarlanabiliyor. Bu gerçek bir tonlama —
# oyunculuk değil, ama düz okumayı da bitiriyor.
#
# Değerler küçük tutuldu: abartılınca insan gibi değil, tuhaf duruyor.
TONES: tuple[tuple[str, int, int], ...] = (
    # (ne zaman, hız %, perde Hz)
    ("soru", 2, 4),        # soru sonunda ses yükselir
    ("unlem", 8, 6),       # heyecan: biraz hızlı, biraz tiz
    ("uyari", -3, -4),     # sorun/hata: yavaşlar ve alçalır, ciddileşir
    ("tereddut", -5, 1),   # emin değil: yavaş ama perde biraz yukarıda
    ("bulus", 6, 5),       # buldum/oldu: canlanır
    ("duraklama", -6, -2), # üç nokta: yavaşlar, alçalır
    ("uzun", -4, -1),      # uzun cümle: anlatım temposu
    ("kisa", 4, 2),        # kısa cümle: canlı
)

# Uzun sayılan cümle uzunluğu.
LONG = 90

# İçerik ipuçları. Noktalama tek başına yetmiyor: "Bir sorun var." ile
# "Tamam, oldu." aynı noktayla bitiyor ama aynı tonda söylenmemeli.
#
# Liste kasten kısa. Uzun bir kelime listesi yanlış cümleyi yakalayıp
# tuhaf bir tonlama üretiyor; buradakiler yanlış yakalasa bile zararsız.
CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("uyari", ("sorun", "hata", "başarısız", "çalışmıyor", "dikkat",
               "uyarı", "olmadı", "bulamadım", "yapamadım")),
    ("tereddut", ("sanırım", "galiba", "belki", "emin değilim",
                  "olabilir", "muhtemelen", "bakmam lazım")),
    ("bulus", ("buldum", "tamam", "oldu", "hazır", "bitti", "çalışıyor",
               "başardık", "harika")),
)


def tone_of(text: str) -> tuple[str, str]:
    """Cümleye göre hız ve perde. edge-tts biçiminde döner.

    Düz okumanın sebebi tek bir ayarın bütün cevaba uygulanmasıydı: soru da
    ünlem de aynı tonda çıkıyordu.
    """
    words = (text or "").strip()
    if not words:
        return "+0%", "+0Hz"

    # Soru ve ünlem önce: onlar cümlenin tamamını belirliyor. Sonra içerik,
    # en son uzunluk — "Bir sorun var." ile "Tamam, oldu." aynı noktayla
    # bitiyor ve düz okunduğunda ikisi de aynı çıkıyordu.
    lower = words.lower()
    if words.endswith("…") or words.endswith("..."):
        key = "duraklama"
    elif words.endswith("?"):
        key = "soru"
    elif words.endswith("!"):
        key = "unlem"
    elif found := next((k for k, cues in CUES if any(c in lower for c in cues)), ""):
        key = found
    elif len(words) > LONG:
        key = "uzun"
    elif len(words) < 30:
        key = "kisa"
    else:
        return "+0%", "+0Hz"

    _, rate, pitch = next(t for t in TONES if t[0] == key)
    return f"{rate:+d}%", f"{pitch:+d}Hz"


def _blend(base: str, shift: str, unit: str) -> str:
    """Kullanıcının ayarı ile cümlenin tonunu toplar.

    Ayardaki hız kişisel bir tercih; tonlama onun üstüne biniyor, yerine
    geçmiyor.
    """
    try:
        first = int(str(base).rstrip(unit).replace("+", "") or 0)
        second = int(str(shift).rstrip(unit).replace("+", "") or 0)
    except ValueError:
        return base
    return f"{first + second:+d}{unit}"


async def synthesize(text: str, config: VoiceConfig) -> bytes:
    """Metni mp3'e çevirir. Söylenecek bir şey yoksa boş döner."""
    if not (words := speakable(text)):
        return b""

    try:
        import edge_tts
    except ImportError as exc:  # pragma: no cover - kurulum yolu
        raise RuntimeError(hint()) from exc

    rate, pitch = tone_of(words)
    speech = edge_tts.Communicate(
        words,
        config.name or DEFAULT_VOICE,
        rate=_blend(config.rate or "+0%", rate, "%"),
        pitch=_blend(config.pitch or "+0Hz", pitch, "Hz"),
    )
    return b"".join([chunk["data"] async for chunk in speech.stream() if chunk["type"] == "audio"])


async def voices(prefix: str = "") -> list[dict[str, Any]]:
    """Kullanılabilir sesler. `prefix` verilirse dile göre süzer ("tr")."""
    try:
        import edge_tts
    except ImportError:
        return []

    try:
        listing = await edge_tts.list_voices()
    except Exception:  # ağ yoksa ses listesi de yok
        return []

    return [
        {
            "id": voice["ShortName"],
            "locale": voice["Locale"],
            "gender": voice.get("Gender", ""),
            # Sesin karakteri seçimde en çok işe yarayan bilgi.
            "tone": ", ".join(voice.get("VoiceTag", {}).get("VoicePersonalities", [])),
        }
        for voice in listing
        if not prefix or voice["Locale"].lower().startswith(prefix.lower())
    ]
