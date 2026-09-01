"""Hatırlama protokolü testleri.

Odak noktası tek bir vaat: bellek büyüdükçe yavaşlamamalı ve hatırlarken
gezdiği yol görülebilmeli.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from dornick.recall import RecallStore, open_store


@pytest.fixture()
def store(tmp_path: Path) -> RecallStore:
    s = open_store(tmp_path)
    yield s
    s.close()


# -- kalıcılık ---------------------------------------------------------


def test_memory_survives_restart(tmp_path: Path) -> None:
    first = open_store(tmp_path)
    node = first.remember("Fatih SCADA tarafında çalışıyor.", kind="user")
    first.close()

    again = open_store(tmp_path)
    try:
        assert again.peek(node.id).body == "Fatih SCADA tarafında çalışıyor."
    finally:
        again.close()


def test_two_processes_see_the_same_store(tmp_path: Path) -> None:
    """Önceki hal belleği açılışta RAM'e okuyordu: bir süreç yazınca
    diğerinin haberi olmuyordu. Arayüz ve ajan aynı belleği görmeli."""
    writer = open_store(tmp_path)
    reader = open_store(tmp_path)
    try:
        node = writer.remember("yeni bir bilgi", kind="fact")
        assert reader.peek(node.id) is not None
    finally:
        writer.close()
        reader.close()


def test_forget_leaves_a_tombstone(store: RecallStore) -> None:
    node = store.remember("yanlış bir bilgi")
    assert store.forget(node.id) is True
    assert store.peek(node.id) is None
    assert store.forget(node.id) is False       # iki kez silinmez


# -- arama -------------------------------------------------------------


def test_turkish_suffixes_match_the_stem(store: RecallStore) -> None:
    store.remember("Haftalık raporları xlsx olarak hazırlıyorum.", kind="procedure")
    store.remember("Tamamen alakasız bir kayıt.", kind="fact")

    hits = store.recall("rapor").hits
    assert hits and "raporları" in hits[0].body


def test_recall_finds_nothing_when_nothing_matches(store: RecallStore) -> None:
    store.remember("bir şey", kind="fact")
    assert store.recall("hiç konuşulmamış konu").hits == []


def test_kind_counts(store: RecallStore) -> None:
    store.remember("a", kind="fact")
    store.remember("b", kind="user")
    store.remember("c", kind="user")

    assert store.count() == 3
    assert store.count("user") == 2


def test_unknown_kind_is_rejected(store: RecallStore) -> None:
    with pytest.raises(ValueError, match="Bilinmeyen tür"):
        store.remember("x", kind="hayal")


# -- çağrışım ----------------------------------------------------------


def test_activation_spreads_to_linked_memories(store: RecallStore) -> None:
    """Sorguda geçmeyen ama bağlı olan hatıra da uyanmalı — sinaps budur."""
    seed = store.remember("Koru1000 SCADA sistemi", kind="fact")
    linked = store.remember("Kuyu debisi sayaçtan okunur", kind="fact", links=[seed.id])

    found = {n.id for n in store.recall("Koru1000").hits}
    assert seed.id in found
    assert linked.id in found, "bağlı hatıra çağrışımla gelmedi"


def test_trace_records_the_path_it_travelled(store: RecallStore) -> None:
    """Arayüz bu izi canlandırıyor: hangi düğüm hangisinden uyandı."""
    seed = store.remember("postgres yedeği", kind="procedure")
    linked = store.remember("yedekler haftalık alınır", kind="fact", links=[seed.id])

    trace = store.recall("postgres").trace
    first = [s for s in trace if s.hop == 0]
    later = [s for s in trace if s.hop > 0]

    assert [s.node for s in first] == [seed.id]
    assert first[0].via == "query"
    assert any(s.node == linked.id and s.via == seed.id for s in later)


def test_activation_weakens_with_distance(store: RecallStore) -> None:
    a = store.remember("birinci halka", kind="fact")
    b = store.remember("ikinci halka", kind="fact", links=[a.id])
    c = store.remember("üçüncü halka", kind="fact", links=[b.id])

    trace = {s.node: s.activation for s in store.recall("birinci").trace}
    assert trace[a.id] > trace[b.id] > trace[c.id]


def test_hop_limit_is_respected(store: RecallStore) -> None:
    a = store.remember("başlangıç", kind="fact")
    b = store.remember("bir adım", kind="fact", links=[a.id])
    c = store.remember("iki adım", kind="fact", links=[b.id])

    reached = {s.node for s in store.recall("başlangıç", hops=1).trace}
    assert b.id in reached
    assert c.id not in reached


def test_links_are_bidirectional(store: RecallStore) -> None:
    a = store.remember("elma", kind="fact")
    b = store.remember("armut", kind="fact")
    store.link(a.id, b.id, reason="ikisi de meyve")

    assert {n.id for n, _ in store.neighbours(a.id)} == {b.id}
    assert {n.id for n, _ in store.neighbours(b.id)} == {a.id}


# -- kullanım izi ------------------------------------------------------


def test_opening_strengthens_the_trace(store: RecallStore) -> None:
    node = store.remember("sık kullanılacak", kind="fact")
    assert store.peek(node.id).uses == 0

    store.open(node.id)
    store.open(node.id)
    assert store.peek(node.id).uses == 2


def test_peek_does_not_count_as_use(store: RecallStore) -> None:
    node = store.remember("sessizce bakılan", kind="fact")
    store.peek(node.id)
    assert store.peek(node.id).uses == 0


def test_headline_hides_the_body(store: RecallStore) -> None:
    """Model önce başlığı görür; gövdeyi açmaya karar verirse alır."""
    node = store.remember("çok uzun bir gövde " * 40, kind="fact", title="kısa başlık")
    headline = node.headline()

    assert "kısa başlık" in headline
    assert "çok uzun bir gövde" not in headline


# -- ölçek -------------------------------------------------------------


def test_recall_does_not_slow_down_as_memory_grows(store: RecallStore) -> None:
    """Asıl vaat bu. Tarama olsaydı süre hacimle doğru orantılı artardı."""
    store.remember("aranan nadir terim: zeplin", kind="fact")

    def elapsed() -> float:
        start = time.perf_counter()
        for _ in range(30):
            store.recall("zeplin")
        return time.perf_counter() - start

    small = elapsed()
    for i in range(3000):
        store.remember(f"alakasız dolgu kaydı numara {i} hakkında bir metin", kind="fact")
    large = elapsed()

    assert store.count() > 3000
    # Doğrusal tarama 3000 kat yavaşlardı. Ölçüm gürültüsüne pay bırakıyoruz.
    assert large < small * 12 + 0.05, f"küçük {small:.4f}s, büyük {large:.4f}s"


# -- önyükleme gürültüsü -----------------------------------------------


def test_numbers_do_not_drag_in_unrelated_memories() -> None:
    """Bir cihaz eklemek isteyen mesaj IP, port ve register adresi taşıyor.

    Ölçüldü: "5.11.239.227 ... 5004 portunda ... 404195 adresinde depo
    seviye" sorgusu üç BTC fiyat kaydını getiriyordu (BTC 3.715.633 TL) —
    sayılar imza katmanında birbirine benziyor. Kullanıcının gördüğü şey
    "modbus cihazı ekle" derken kripto ölçümlerinin taranmasıydı.
    """
    from dornick.loop import _without_numbers

    clean = _without_numbers(
        "5.11.239.227 bu ip adresinde 5004 portunda bir modbus tcp cihazım "
        "var 404195 adrsinde depo seviye var"
    )

    assert "modbus" in clean and "depo seviye" in clean
    for number in ("5.11.239.227", "5004", "404195"):
        assert number not in clean


def test_words_glued_to_numbers_survive() -> None:
    """Sayıyı atarken kelimeyi de atmak, sorguyu anlamsız bırakır."""
    from dornick.loop import _without_numbers

    assert "port" in _without_numbers("port 502 açık")
    assert "v1" in _without_numbers("api v1 uçları")
