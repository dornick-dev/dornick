"""Association signature tests.

The layer here has a two-sided job: finding close text *and* not finding
distant text. The second is easier to miss — with a loose floor every query
"remembers" something and spreading activation jumps into an unrelated
region.
"""

from __future__ import annotations

import time

from dornick.recall.vector import BITS, FLOOR, Index, from_blob, signature, similarity, to_blob


def test_same_text_gives_the_same_signature() -> None:
    """The hash seed must be fixed: otherwise a signature written to disk
    becomes meaningless on the next run."""
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
    """Two random signatures agree on around half their bits. Reporting the
    raw ratio as similarity would put every unrelated record on the list
    with 0.5 points; after the scale is shifted only the scatter remains,
    and that must be below the floor."""
    assert similarity(signature("kahve makinesi"), signature("borsa analizi")) < FLOOR


def test_short_texts_do_not_all_look_alike() -> None:
    """In a short text most dimensions stay tied. Writing ties to a fixed
    side had made all short texts neighbours."""
    assert similarity(signature("bir şey"), signature("hiç konuşulmamış konu")) < FLOOR


def test_turkish_suffix_survives_the_signature() -> None:
    """This is why the character n-grams exist: 'rapor' and 'raporlarımızı'
    must overlap."""
    assert similarity(signature("haftalık rapor"), signature("haftalık raporlarımızı")) > 0.3


def test_empty_text_has_no_signature() -> None:
    assert signature("") == 0
    assert similarity(0, signature("bir şey")) == 0.0


def test_blob_round_trip() -> None:
    value = signature("diske yazılıp geri okunuyor")
    assert from_blob(to_blob(value)) == value
    assert len(to_blob(value)) == BITS // 8
    assert from_blob(None) == 0


# -- index -------------------------------------------------------------


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
    """The scan runs over a flat list; if adding does not refresh that list
    the new record silently stays invisible."""
    index = Index([("coffee", signature("kahve makinesi"))])
    index.search(signature("herhangi bir sorgu"), 5)  # forces the flat list to be built
    index.add("db", signature("postgres veritabanı yedeği alınıyor"))
    assert index.search(signature("veritabanı dökümü"), 5)[0][0] == "db"


def test_signatureless_entries_are_ignored() -> None:
    assert len(Index([("empty", 0)])) == 0


def test_fifty_thousand_signatures_stay_under_a_tenth_of_a_second() -> None:
    """The user's condition: 'if it gets lost for minutes once a long time
    has passed, there is no point.' The scan is exact and linear; the
    measurement pins down its linear coefficient."""
    index = Index((f"n{i}", signature(f"kayıt {i} hakkında birkaç kelime")) for i in range(50_000))
    query = signature("kayıt 400 hakkında")

    start = time.perf_counter()
    index.search(query, 8)
    assert time.perf_counter() - start < 0.1
