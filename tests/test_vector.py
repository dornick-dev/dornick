"""Çağrışım imzası testleri.

Buradaki katmanın işi iki uçlu: yakın metni bulmak *ve* uzak metni
bulmamak. İkincisi daha kolay kaçırılıyor — eşiği gevşek bırakınca her
sorgu bir şey "hatırlıyor" ve yayılan aktivasyon alakasız bölgeye sıçrıyor.
"""

from __future__ import annotations

import time

from neocp.recall.vector import BITS, FLOOR, Index, from_blob, signature, similarity, to_blob


def test_same_text_gives_the_same_signature() -> None:
    """Hash tohumu sabit olmalı: aksi halde diske yazılan imza bir sonraki
    çalıştırmada anlamsızlaşır."""
    assert signature("postgres yedeği") == signature("postgres yedeği")


def test_similar_texts_land_close() -> None:
    near = similarity(
        signature("postgres veritabanı yedeğini her gece alıyoruz"),
        signature("postgres veritabanı yedeği gece alınıyor"),
    )
    far = similarity(
        signature("postgres veritabanı yedeğini her gece alıyoruz"),
        signature("kahve makinesi mutfakta bozuldu"),
    )
    assert near > far


def test_unrelated_texts_stay_under_the_noise_floor() -> None:
    """İki rastgele imza bitlerinin yarısı civarında tutar. Ham oranı
    benzerlik diye vermek alakasız her kaydı 0.5 puanla listeye sokardı;
    ölçek kaydırıldıktan sonra geriye yalnızca saçılma kalıyor ve o da
    eşiğin altında olmalı."""
    assert similarity(signature("kahve makinesi"), signature("borsa analizi")) < FLOOR


def test_short_texts_do_not_all_look_alike() -> None:
    """Kısa metinde boyutların çoğu berabere kalıyor. Beraberliği sabit bir
    tarafa yazmak bütün kısa metinleri komşu yapmıştı."""
    assert similarity(signature("bir şey"), signature("hiç konuşulmamış konu")) < FLOOR


def test_turkish_suffix_survives_the_signature() -> None:
    """Harf n-gramları bu yüzden var: 'rapor' ile 'raporlarımızı' örtüşmeli."""
    assert similarity(signature("haftalık rapor"), signature("haftalık raporlarımızı")) > 0.3


def test_empty_text_has_no_signature() -> None:
    assert signature("") == 0
    assert similarity(0, signature("bir şey")) == 0.0


def test_blob_round_trip() -> None:
    value = signature("diske yazılıp geri okunuyor")
    assert from_blob(to_blob(value)) == value
    assert len(to_blob(value)) == BITS // 8
    assert from_blob(None) == 0


# -- indeks ------------------------------------------------------------


def test_index_ranks_the_closest_first() -> None:
    index = Index(
        [
            ("db", signature("postgres veritabanı yedeği alınıyor")),
            ("coffee", signature("kahve makinesi mutfakta")),
        ]
    )
    assert index.search(signature("veritabanı dökümü"), 2)[0][0] == "db"


def test_index_returns_nothing_for_an_unrelated_query() -> None:
    index = Index([("db", signature("postgres veritabanı yedeği alınıyor"))])
    assert index.search(signature("gitar akort etmek"), 5) == []


def test_dropped_entries_stop_matching() -> None:
    index = Index([("db", signature("postgres veritabanı yedeği alınıyor"))])
    index.drop("db")
    assert index.search(signature("postgres yedeği"), 5) == []
    assert len(index) == 0


def test_added_entries_are_visible_after_a_search() -> None:
    """Tarama düz bir liste üzerinden gidiyor; ekleme o listeyi tazelemezse
    yeni kayıt sessizce görünmez kalır."""
    index = Index([("coffee", signature("kahve makinesi"))])
    index.search(signature("herhangi bir sorgu"), 5)  # düz listeyi kurdurur
    index.add("db", signature("postgres veritabanı yedeği alınıyor"))
    assert index.search(signature("veritabanı dökümü"), 5)[0][0] == "db"


def test_signatureless_entries_are_ignored() -> None:
    assert len(Index([("boş", 0)])) == 0


def test_fifty_thousand_signatures_stay_under_a_tenth_of_a_second() -> None:
    """Kullanıcının koyduğu şart: 'uzun süre geçince dakikalarca içinde
    kaybolursa bir anlamı kalmaz.' Tarama tam ve doğrusal; ölçü buranın
    doğrusal katsayısını tutuyor."""
    index = Index((f"n{i}", signature(f"kayıt {i} hakkında birkaç kelime")) for i in range(50_000))
    query = signature("kayıt 400 hakkında")

    start = time.perf_counter()
    index.search(query, 8)
    assert time.perf_counter() - start < 0.1
