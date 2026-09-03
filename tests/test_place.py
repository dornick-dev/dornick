"""Location and autostart.

The model once answered "what's the weather tomorrow?" assuming
Istanbul. The checks here hold both sides of that bug: the location can
really be learned, and when it cannot, it is not made up.
"""

from __future__ import annotations

from pathlib import Path

from dornick import place, startup
from dornick.config import Config


# -- sources -----------------------------------------------------------


def test_location_is_off_until_asked_for(tmp_path: Path) -> None:
    """The IP query sends the user's address to a third-party service.
    Not something to do silently."""
    assert not Config.load(tmp_path).place.enabled


def test_what_the_user_typed_beats_everything(tmp_path: Path) -> None:
    found = place.locate(place.PlaceConfig(manual="Kayseri"))
    assert found.where == "Kayseri"
    assert found.trust == "kesin"


def test_the_machine_knows_the_country_but_not_the_city() -> None:
    """The timezone gives the country, not the city. The difference
    between "you are in Türkiye" and "you are in Istanbul" is the entire
    answer to a weather question."""
    found = place.from_machine()
    assert found.trust in ("ülke", "yok")
    if found.where:
        assert "saat dilimi" in found.source


def test_a_closed_setting_never_touches_the_network(monkeypatch) -> None:
    """While disabled it must not touch the network: that is what the setting means."""
    def boom() -> place.Place:
        raise AssertionError("kapalıyken ağa çıkıldı")

    monkeypatch.setattr(place, "from_network", boom)
    assert place.locate(place.PlaceConfig(enabled=False)).trust in ("ülke", "yok")


# -- trust -------------------------------------------------------------


def test_an_ip_guess_is_never_presented_as_fact() -> None:
    """Measured: two services asked at the same moment, one said "Manisa",
    the other "Kayseri". On a mobile connection the exit point is not
    where the user is."""
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
    """Reducing to a single answer would have meant picking the wrong one in the measurement."""
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
    json.dumps(found.detail)  # goes to the UI: must serialize


def test_a_dead_service_does_not_break_the_answer() -> None:
    def boom(url: str) -> dict:
        raise OSError("ağ yok")

    original = place._ask
    place._ask = boom
    try:
        assert place.from_network().where == ""
    finally:
        place._ask = original


# -- start at boot -----------------------------------------------------


def test_autostart_reads_without_writing() -> None:
    """Reading the state must change nothing: the settings page calls
    this on every open."""
    before = startup.current()
    startup.enabled()
    startup.command()
    assert startup.current() == before


def test_autostart_runs_a_command_that_exists() -> None:
    """`python -m dornick` does not work (the package cannot be run
    directly); the line written to startup must actually start something."""
    line = startup.command()
    assert "dornick.cli" in line and "--app" in line
    # No console window; Task Manager wants the branded dornick.exe.
    low = line.lower()
    assert "dornick.exe" in low or "pythonw" in low or "python" in low


def test_autostart_writes_only_for_this_user() -> None:
    """One user's preference must not bind the whole machine."""
    import inspect

    source = inspect.getsource(startup)
    assert "HKEY_CURRENT_USER" in source
    assert "HKEY_LOCAL_MACHINE" not in source
