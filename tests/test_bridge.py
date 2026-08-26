"""Sinonim köprüsü.

Sözcüksel hatırlamanın ölçülmüş duvarı: bitcoin↔BTC gibi çiftlerde sorgu ile
kayıt hiç ortak n-gram taşımıyor. Köprü yalnız SORGU tarafında açılır —
kayıt yazıldığı gibi durur, tablo değişince indeks yeniden kurulmaz.
Mühürlü holdout'ta tek atış ölçüldü: recall@3 0.840 → 0.920.
"""

from __future__ import annotations

from neocp.recall import bridge


def test_a_word_calls_its_synonyms() -> None:
    assert "btc" in bridge.calls_of("bitcoin")
    assert "bitcoin" in bridge.calls_of("BTC")          # büyük harf fark etmez
    assert "tag" in bridge.calls_of("etiket")


def test_suffixed_forms_are_caught_by_prefix() -> None:
    # Türkçe sondan eklemeli: "etiketleri" de köprüyü açmalı.
    assert "tag" in bridge.calls_of("etiketleri")
    assert "backup" in bridge.calls_of("yedeğini") or "backup" in bridge.calls_of("yedekleri")


def test_short_keys_do_not_prefix_match() -> None:
    """"işlem"in "iş"i çağırması gibi kazalar: kısa anahtarda tam eşleşme şart.
    (Tabloda kısa anahtar örneği: ağ.)"""
    assert bridge.calls_of("ağır") == ()      # "ağ" anahtarını AÇMAMALI
    assert "network" in bridge.calls_of("ağ")


def test_expand_appends_without_touching_the_query() -> None:
    grown = bridge.expand("bitcoin ne durumda")
    assert grown.startswith("bitcoin ne durumda")
    assert "btc" in grown.split()

    # Köprüsüz sorgu aynen döner — maliyet sıfır.
    plain = "bugün yoruldum biraz"
    assert bridge.expand(plain) == plain


def test_expand_does_not_repeat_terms_already_present() -> None:
    grown = bridge.expand("btc bitcoin karşılaştır")
    assert grown.split().count("btc") == 1
    assert grown.split().count("bitcoin") == 1


def test_the_bridge_reaches_a_record_with_no_shared_words(tmp_path) -> None:
    """Asıl iddia: sorgu ile kayıt hiç ortak kelime taşımasa da köprü
    kuruluyor — ve önyüklemenin zemin kapısı köprüyü tanıyor."""
    from neocp.loop import select_prime
    from neocp.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("BTC portföyün yüzde onunu geçmesin", kind="lesson",
                  title="pozisyon sınırı")
    mind.remember("Kek tarifinde iki yumurta", kind="fact")

    hits = select_prime(mind, "bitcoin pozisyonum için kural neydi")
    got = {h.item.title for h in hits}
    assert "pozisyon sınırı" in got
    mind.store.close()
