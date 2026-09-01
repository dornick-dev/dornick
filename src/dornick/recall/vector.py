"""Çağrışımsal imza katmanı — hatırlamanın "sezgi" tarafı.

FTS5 kelimeyi bilir, anlamı bilmez. "postgres yedeği" araması "veritabanı
dökümü" yazan kaydı asla bulamaz; harf farkı yeter, kayıt görünmez olur.
Buradaki katman o boşluğu dolduruyor.

Fikir LLM'lerin token gömmesinden geliyor ama ağırlığı yok, eğitimi yok ve
dışarıdan model indirmiyor: her metin sabit bir **hiper-vektöre** yansıtılıyor
(rastgele izdüşüm / SimHash). Yakın metinler yakın vektör üretir; uzaklık
Hamming mesafesi.

Bunun asıl kazancı hız. Vektör 256 bit — tek bir Python tamsayısı. İki kayıt
karşılaştırması `(a ^ b).bit_count()`, yani tek makine komutu düzeyinde bir iş.
Float kosinüs benzerliği 256 çarpma demekti; bu tek XOR. Elli bin kayıt saf
Python'da milisaniyeler içinde taranıyor — kullanıcının koyduğu şart tam olarak
buydu: "uzun süre geçince dakikalarca içinde kaybolursa bir anlamı kalmaz".

Özellik çıkarımı iki kanallı:

    kelime      "rapor"        — tam eşleşme, güçlü sinyal
    harf 4'lüsü "rapo" "apor"  — Türkçe sondan eklemeli; "raporları" ile
                                 "rapor" bu kanalda örtüşür

İkisi birlikte hem yazım hatasına hem çekim ekine dayanıklı bir iz üretiyor.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Iterator

# İmza genişliği. 256 bit tek tamsayıya sığıyor ve ayırt etmeye fazlasıyla
# yetiyor; büyütmek karşılaştırmayı çok basamaklı aritmetiğe iter.
BITS = 256

# Bu uzunluktan kısa kelimeler parçalanmaz — parçası zaten kendisi.
GRAM = 4

# Rastgele eşleşen iki imza bitlerinin yarısında tutar. Bunun altı bilgi
# değil gürültü; sıfıra kırpılıyor ki tohumlamaya sızmasın.
CHANCE = 0.5

# Gurultu esigi. Iki alakasiz imza bitlerinin tam yarisinda degil, yarisi
# civarinda tutar; 256 bitte sapma benzerlik olceginde ~0.06. Esik bu
# saciligin ustunde olmali, yoksa her sorgu bir sey "hatirlar".
FLOOR = 0.15

_WORD = re.compile(r"\w+", re.UNICODE)

# Sorguyu daraltmayan işlev kelimeleri (edat, zamir, soru eki, bağlaç). FTS
# literal kanalında (store._match_expression) eleniyor: "bir fıkra anlat" gibi
# bir soru, içinde "bir" geçen genel bir anıya ("...bir kod asistanı değil;
# genel bir ajan") FTS üstünden yapışıyor ve boş dönmesi gereken sorgu bir
# şey hatırlıyordu. İçerik değil gürültü.
#
# İmza tarafında ELENMİYOR — orada silmek kısa metinleri ("bir şey" → tek
# "şey" özniteliği) kararsızlaştırıp birbirine benzetiyor (bkz. test_vector
# short-texts). İmzadaki sık-kelime sorunu ayrı ele alınmalı (IDF ağırlığı).
STOPWORDS = frozenset(
    """
    ve veya ile için gibi kadar daha çok az bir bu şu o ne nasıl neden
    da de ki mi mı mu mü ben sen biz siz onlar var yok olan olarak
    the a an and or of to in on for with is are was were be been it this that
    """.split()
)

# Bayt -> o baytın 8 bitinin işaret dizisi. Özellik başına 256 kez bit kaydırmak
# yerine 32 tablo okuması yapıyoruz; indeksleme birkaç kat hızlanıyor.
_SIGNS: tuple[tuple[int, ...], ...] = tuple(
    tuple(1 if (byte >> (7 - i)) & 1 else -1 for i in range(8)) for byte in range(256)
)


def features(text: str) -> Iterator[str]:
    """Metni imzalanacak özelliklere ayırır.

    Kelimenin kendisi ve harf n-gramları birlikte veriliyor: ilki kesinlik,
    ikincisi hoşgörü sağlıyor.
    """
    for match in _WORD.finditer((text or "").lower()):
        word = match.group(0)
        yield word
        if len(word) > GRAM:
            for i in range(len(word) - GRAM + 1):
                yield word[i : i + GRAM]


def signature(text: str) -> int:
    """Metnin 256 bitlik çağrışım imzası.

    Her özellik kendi hash'inden türeyen sabit bir ±1 vektörüne açılıyor,
    hepsi toplanıyor, sonuç işaretine göre bitleniyor. Aynı metin her
    çalışmada aynı imzayı verir — hash tohumu sabit.
    """
    weights = [0] * BITS
    seen = False

    for feature in features(text):
        seen = True
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=BITS // 8).digest()
        offset = 0
        for byte in digest:
            signs = _SIGNS[byte]
            for i in range(8):
                weights[offset + i] += signs[i]
            offset += 8

    if not seen:
        return 0

    # Beraberlik (toplam 0) kisa metinlerde sik: iki-uc ozellikli bir kayitta
    # boyutlarin cogu berabere kalir. Berabereyi sabit bir tarafa yazmak
    # butun kisa metinleri birbirine benzetiyordu — "bir sey" ile "hic
    # konusulmamis konu" komsu cikiyordu. Bunun yerine metnin kendi
    # ozetinden bir bit aliniyor: ayni metin ayni biti verir, farkli metin
    # bagimsiz bir bit verir.
    tie = int.from_bytes(
        hashlib.blake2b(text.encode("utf-8"), digest_size=BITS // 8).digest(), "big"
    )

    value = 0
    for position, weight in enumerate(weights):
        if weight:
            bit = 1 if weight > 0 else 0
        else:
            bit = (tie >> (BITS - 1 - position)) & 1
        value = (value << 1) | bit
    return value


def similarity(a: int, b: int) -> float:
    """İki imzanın yakınlığı, 0..1.

    Şansın (yarısı tutan iki rastgele imza) altı sıfıra kırpılıyor; aksi
    halde alakasız her kayıt 0.5 puanla listeye girerdi.
    """
    if not a or not b:
        return 0.0
    agreement = 1.0 - (a ^ b).bit_count() / BITS
    return max(0.0, (agreement - CHANCE) / (1.0 - CHANCE))


def to_blob(value: int) -> bytes:
    return value.to_bytes(BITS // 8, "big")


def from_blob(blob: bytes | None) -> int:
    return int.from_bytes(blob, "big") if blob else 0


class Index:
    """İmzaların RAM'deki hali.

    Tamamı bellekte tutuluyor çünkü tutmamak için bir sebep yok: elli bin
    kayıt ~1.6 MB imza demek. Asıl gövde diskte kalır, burada yalnızca
    "neye benziyor" bilgisi durur.

    Arama saf tarama — ama taranan şey tamsayı XOR'u olduğu için yaklaşık
    komşu yapılarının (HNSW, IVF) karmaşıklığına bu ölçekte gerek yok.
    """

    __slots__ = ("_sigs", "_flat")

    def __init__(self, entries: Iterable[tuple[str, int]] = ()) -> None:
        self._sigs: dict[str, int] = {k: v for k, v in entries if v}
        # Taramanin uzerinden gectigi duz liste. Sozluk uzerinde donmek her
        # adimda bir hash tablosu adimi ekliyordu; tarama zaten tek XOR'a
        # inmisken bu ek yuk toplamin kayda deger bir kismi oluyor.
        self._flat: list[tuple[int, str]] | None = None

    def __len__(self) -> int:
        return len(self._sigs)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._sigs

    def add(self, node_id: str, value: int) -> None:
        if value:
            self._sigs[node_id] = value
            self._flat = None

    def drop(self, node_id: str) -> None:
        if self._sigs.pop(node_id, None) is not None:
            self._flat = None

    def search(self, query: int, limit: int, *, floor: float = FLOOR) -> list[tuple[str, float]]:
        """En yakin `limit` imzayi dondurur.

        Tarama tam ve DOGRUSAL: yaklasik komsu yapilarinin (LSH bantlari,
        HNSW) aksine hicbir eslesmeyi kacirmiyor. Bu olcekte gerekmiyor
        da — kayit basina is tek bir XOR ve popcount oldugu icin elli bin
        kayit ~3-5 ms (olculdu, 29.08); bir model cagrisinin binde biri.

        `floor` gurultu esigi: altinda kalan her sey "hatirlamadim" demektir.
        Zayif eslesmeyi listeye almak, yayilan aktivasyonun alakasiz bir
        bolgeye sicramasina yol aciyor.
        """
        if not query or not self._sigs:
            return []

        if self._flat is None:
            self._flat = [(value, node_id) for node_id, value in self._sigs.items()]

        # Esik dongunun disinda bir kez, mesafe cinsinden hesaplaniyor:
        # her adayda benzerlik orani hesaplamak taramayi yavaslatirdi.
        #   sim >= floor  <=>  hamming <= BITS * CHANCE * (1 - floor)
        cutoff = int(BITS * CHANCE * (1.0 - floor))

        near = [
            (distance, node_id)
            for distance, node_id in (
                ((query ^ value).bit_count(), node_id) for value, node_id in self._flat
            )
            if distance <= cutoff
        ]
        near.sort()
        span = BITS * (1.0 - CHANCE)
        return [
            (node_id, round((BITS * CHANCE - distance) / span, 4))
            for distance, node_id in near[:limit]
        ]
