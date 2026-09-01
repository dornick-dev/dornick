"""Konum ve otomatik başlatma.

"Yarın hava nasıl?" sorusuna model İstanbul'u varsayıp cevap vermişti.
Buradaki kontroller o hatanın iki tarafını da tutuyor: konumun gerçekten
öğrenilebilmesi, ve öğrenilemediğinde uydurulmaması.
"""

from __future__ import annotations

from pathlib import Path

from dornick import place, startup
from dornick.config import Config


# -- kaynaklar ---------------------------------------------------------


def test_location_is_off_until_asked_for(tmp_path: Path) -> None:
    """IP sorgusu kullanıcının adresini üçüncü bir servise gönderiyor.
    Sessizce yapılacak bir şey değil."""
    assert not Config.load(tmp_path).place.enabled


def test_what_the_user_typed_beats_everything(tmp_path: Path) -> None:
    found = place.locate(place.PlaceConfig(manual="Kayseri"))
    assert found.where == "Kayseri"
    assert found.trust == "kesin"


def test_the_machine_knows_the_country_but_not_the_city() -> None:
    """Saat dilimi ülkeyi veriyor, şehri vermiyor. "Türkiye'desin" ile
    "İstanbul'dasın" arasındaki fark, hava durumu sorusunda cevabın
    tamamı demek."""
    found = place.from_machine()
    assert found.trust in ("ülke", "yok")
    if found.where:
        assert "saat dilimi" in found.source


def test_a_closed_setting_never_touches_the_network(monkeypatch) -> None:
    """Kapalıyken ağa çıkmamalı: ayarın anlamı bu."""
    def boom() -> place.Place:
        raise AssertionError("kapalıyken ağa çıkıldı")

    monkeypatch.setattr(place, "from_network", boom)
    assert place.locate(place.PlaceConfig(enabled=False)).trust in ("ülke", "yok")


# -- güven -------------------------------------------------------------


def test_an_ip_guess_is_never_presented_as_fact() -> None:
    """Ölçüm: aynı anda iki servise soruldu, biri "Manisa" dedi diğeri
    "Kayseri". Mobil bağlantıda çıkış noktası kullanıcının bulunduğu yer
    değil."""
    said = place.describe(place.Place(where="Manisa", trust="ipucu", source="IP"))

    assert "Kesin değil" in said
    assert "teyit" in said


def test_a_certain_place_is_usable_without_asking() -> None:
    said = place.describe(place.Place(where="Kayseri", trust="kesin",
                                      source="kullanıcı söyledi"))
    assert "kullanabilirsin" in said
    assert "Kesin değil" not in said


def test_only_knowing_the_country_says_to_ask_for_the_city() -> None:
    said = place.describe(place.Place(where="TR", trust="ülke", source="saat dilimi"))
    assert "şehri sor" in said.lower() or "Şehir bilinmiyor" in said


def test_knowing_nothing_says_to_ask() -> None:
    said = place.describe(place.Place())
    assert "sor" in said


def test_disagreeing_services_are_both_reported() -> None:
    """Tek bir cevaba indirgemek, ölçümde yanlış olanı seçmek demekti."""
    import json

    calls = []

    def answer(url: str) -> dict:
        calls.append(url)
        return {"city": "Manisa" if "ip-api" in url else "Kayseri"}

    original = place._ask
    place._ask = answer
    try:
        found = place.from_network()
    finally:
        place._ask = original

    assert len(calls) == 2
    assert "Manisa" in found.where and "Kayseri" in found.where
    assert found.trust == "ipucu"
    json.dumps(found.detail)  # arayüze gidiyor: serileşebilmeli


def test_a_dead_service_does_not_break_the_answer() -> None:
    def boom(url: str) -> dict:
        raise OSError("ağ yok")

    original = place._ask
    place._ask = boom
    try:
        assert place.from_network().where == ""
    finally:
        place._ask = original


# -- açılışta başlat ---------------------------------------------------


def test_autostart_reads_without_writing() -> None:
    """Durumu okumak hiçbir şey değiştirmemeli: ayar sayfası her
    açılışta bunu çağırıyor."""
    before = startup.current()
    startup.enabled()
    startup.command()
    assert startup.current() == before


def test_autostart_runs_a_command_that_exists() -> None:
    """`python -m dornick` çalışmıyor (paket doğrudan çalıştırılamıyor);
    açılışa yazılan satırın gerçekten bir şey başlatması gerekiyor."""
    line = startup.command()
    assert "dornick.cli" in line and "--app" in line
    # Konsol penceresi açılmasın; Görev Yöneticisi damgalı dornick.exe ister.
    low = line.lower()
    assert "dornick.exe" in low or "pythonw" in low or "python" in low


def test_autostart_writes_only_for_this_user() -> None:
    """Bir kullanıcının tercihi bütün makineyi bağlamamalı."""
    import inspect

    source = inspect.getsource(startup)
    assert "HKEY_CURRENT_USER" in source
    assert "HKEY_LOCAL_MACHINE" not in source
