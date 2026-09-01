"""Sinonim köprüsü — sorgu tarafında anlam genişletme.

Sözcüksel hatırlamanın ölçülmüş duvarı: sorgu ile kayıt hiç ortak
kelime/n-gram taşımıyorsa (bitcoin↔BTC, etiket↔tag) FTS de imza da köprü
kuramıyor. Embedding bilinçli olarak yok (kurulumsuz, GPU'suz ilke); bunun
yerine küçük, elle bakımı yapılabilir bir eşleme: sorgudaki kelimenin
eşanlamlıları sorguya ek terim olarak katılıyor. Kayıt tarafına dokunulmuyor
— yazılan şey yazıldığı gibi kalır, köprü yalnızca ararken açılır.

Tablo GENEL kategorilerden derlendi (kripto kısaltmaları, endüstri terimleri,
BT'nin İngilizce↔Türkçe gündelik sözlüğü, yaygın Türkçe eşanlamlılar) —
eval sorgularına bakılarak değil; eval'e göre tablo yazmak ölçümü anlamsız
kılar (ARASTIRMA.md hile kuralı). Dürüstlük notu: yazarı başarısızlık
SINIFLARINI biliyordu (kısaltma/çeviri çiftleri); çiftler yine de kategori
geneli seçildi ve sınıfın örtmediği kaçışlar (iş↔mühendis gibi gerçek
eşanlamlı olmayanlar) bilerek dışarıda bırakıldı.

Genişletme ölçülüdür: kelime başına en çok birkaç ek terim, yalnız içerik
kelimeleri, ekli biçimler önekle yakalanır ("etiketleri" → etiket).
"""

from __future__ import annotations

import re

# Eş anlam grupları. Grup içindeki her kelime, gruptaki diğerlerini çağırır.
# Kısa tutmak bilinçli: agresif bir tablo ("fiyat/bedel/ücret/para" gibi
# gevşek zincirler) alakasız kayıtları uyandırıp tuzak sızıntısını artırıyor.
GROUPS: tuple[tuple[str, ...], ...] = (
    # kripto / finans kısaltmaları
    ("btc", "bitcoin"),
    ("eth", "ethereum"),
    ("usdt", "tether"),
    ("borsa", "exchange"),
    ("cüzdan", "wallet"),
    ("portföy", "portfolio"),
    ("alım", "alış"),
    ("satım", "satış"),
    # endüstri / SCADA
    ("vana", "valf"),
    ("debi", "akış"),
    ("arıza", "fault"),
    ("uyarı", "alarm"),
    ("sensör", "algılayıcı"),
    ("yazmaç", "register"),
    ("pano", "panel"),
    ("motor", "pompa"),  # sahada sık geçişli; ölçümde zarar verirse çıkar
    ("sondaj", "kuyu"),
    ("basınç", "bar"),
    # BT — İngilizce↔Türkçe gündelik sözlük
    ("etiket", "tag"),
    ("yedek", "backup"),
    ("şifre", "parola", "password"),
    ("sunucu", "server"),
    ("veritabanı", "database"),
    ("eposta", "mail", "posta"),
    ("güncelleme", "update"),
    ("dizin", "klasör", "folder"),
    ("ağ", "network"),
    ("bağlantı", "link"),
    ("hata", "bug"),
    ("sürüm", "versiyon"),
    ("depolama", "disk"),
    ("bellek", "hafıza"),
    ("araç", "tool"),
    # gündelik Türkçe
    ("araba", "otomobil"),
    ("ev", "konut"),
    ("doktor", "hekim"),
    ("ilaç", "hap"),
    ("yanıt", "cevap"),
    ("soru", "sual"),
    ("sorun", "problem"),
    ("kent", "şehir"),
    ("görsel", "resim", "fotoğraf"),
    ("hedef", "amaç"),
    ("ders", "öğreti"),
    ("koşu", "koşmak"),
    ("yürüyüş", "yürümek"),
    ("takvim", "ajanda"),
    ("toplantı", "görüşme"),
    ("tatil", "izin"),
    ("maaş", "ücret"),
    ("kira", "kiralık"),
)

_CLEAN = re.compile(r"[^\wçğıöşü]+", re.UNICODE)

# kelime → çağırdığı ek terimler. Önek eşleşmesi için anahtarlar ayrıca
# uzunluklarıyla tutuluyor ("etiketleri" → "etiket").
_CALLS: dict[str, tuple[str, ...]] = {}
for _group in GROUPS:
    for _word in _group:
        _CALLS.setdefault(_word, tuple(w for w in _group if w != _word))

# Önek araması yalnız ≥5 harfli anahtarlarda: "işlem"in "iş"i çağırması gibi
# kazaları kısa anahtarlarda tam eşleşme şartı kesiyor.
_LONG_KEYS = tuple(sorted((k for k in _CALLS if len(k) >= 5),
                          key=len, reverse=True))


def calls_of(word: str) -> tuple[str, ...]:
    """Bir kelimenin çağırdığı eş anlamlılar (ekli biçimler dahil)."""
    plain = _CLEAN.sub("", (word or "").casefold())
    if not plain:
        return ()
    if plain in _CALLS:
        return _CALLS[plain]
    for key in _LONG_KEYS:
        if plain.startswith(key):
            return _CALLS[key]
    return ()


def expand(query: str) -> str:
    """Sorguya eş anlamlı ek terimleri katar; yoksa sorguyu aynen döndürür.

    Ekler SONA gelir: FTS tarafında fazladan OR terimi, imza tarafında
    birkaç ek özellik. Kayıt tarafı değişmediği için genişletme her an
    geri alınabilir — indeks yeniden kurulmaz.
    """
    text = query or ""
    extra: list[str] = []
    seen = set(_CLEAN.sub(" ", text.casefold()).split())
    for word in text.split():
        for called in calls_of(word):
            if called not in seen:
                seen.add(called)
                extra.append(called)
    return f"{text} {' '.join(extra)}" if extra else text
