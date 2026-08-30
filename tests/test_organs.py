"""Ajanın bedeni: duyuları ve kendine taktığı modüller.

Buradaki tek kural, listedeki her şeyin gerçekten var olması. Sahnede
soluk da olsa duran bir kamera "bu bende var" demek; olmayan bir aygıtı
çizmek ekranda çalışıyormuş gibi duran bir yalan olur.
"""

from __future__ import annotations

from pathlib import Path

from neocp import organs, skills
from neocp.config import Config


def test_the_senses_are_always_listed(tmp_path: Path) -> None:
    """Kapalı olsalar da görünüyorlar: neye sahip olduğu, neyin kapalı
    olduğu kadar önemli. Boş bir sahne "hiçbir şeyim yok" demek."""
    body = organs.inventory(Config.load(tmp_path))
    ids = {organ["id"] for organ in body}

    assert {"mic", "lens", "voice"} <= ids


def test_the_hand_is_part_of_the_body(tmp_path: Path) -> None:
    """Ekran ve el bir organ: makine desteklemese de 'yok' olarak görünmeli,
    'hiç yok' değil. Ajan ne yapabileceğini bedeninde görüyor."""
    hand = next(o for o in organs.inventory(Config.load(tmp_path)) if o["id"] == "hand")
    assert "screen" in hand["tools"] and "hand" in hand["tools"]


def test_a_closed_camera_says_so(tmp_path: Path, monkeypatch) -> None:
    # Kamerasız bir geliştirme makinesinde de geçmeli: yoklama sabitleniyor,
    # test aygıtı değil "var ama kapalı" halinin sözünü sınıyor.
    monkeypatch.setattr(organs, "has_camera", lambda lens=None: True)
    config = Config.load(tmp_path)
    lens = next(o for o in organs.inventory(config) if o["id"] == "lens")

    assert not lens["live"]
    assert lens["state"] == "kapalı"


def test_an_open_camera_is_live(tmp_path: Path) -> None:
    """Ayar değil, gerçek durum. Ayarda açık görünen bir kamera
    açılmamış olabiliyor ve ekranda çalışıyormuş gibi duruyordu."""

    class Open:
        live = True

    lens = next(
        o for o in organs.inventory(Config.load(tmp_path), lens=Open()) if o["id"] == "lens"
    )
    assert lens["live"] and lens["state"] == "açık"


def test_the_camera_is_used_by_the_look_tool(tmp_path: Path) -> None:
    """Arayüz hangi aracın hangi organa dokunduğunu buradan öğreniyor;
    orada tahmin edilirse yeni bir araç sessizce eşleşmeden kalıyor."""
    lens = next(o for o in organs.inventory(Config.load(tmp_path)) if o["id"] == "lens")
    assert "look" in lens["tools"]
    assert "kamera" in lens["tools"]
    assert lens["name"] == "Bilgisayar kamerası"


def test_named_cameras_are_organs_the_model_can_call(tmp_path: Path) -> None:
    from neocp import watch

    config = Config.load(tmp_path)
    config.ensure_dirs()
    watch.save(config.state_dir, [
        watch.Camera(id="cam_1", name="bahçe", kind="rtsp", host="10.0.0.8",
                     last_note="kişi"),
    ])
    body = organs.inventory(config)
    cam = next(o for o in body if o["id"] == "cam:cam_1")
    assert cam["name"] == "bahçe"
    assert "kamera" in cam["tools"]
    assert "kişi" in cam["detail"]


def test_a_deaf_ear_is_not_listening(tmp_path: Path) -> None:
    """Ajan konuşurken kulak kapalı. Sahnede o an "dinliyor" yazması,
    kendi sesini duyuyormuş gibi görünmek olurdu."""

    class Deafened:
        deaf = True

    mic = next(
        o for o in organs.inventory(Config.load(tmp_path), ear=Deafened()) if o["id"] == "mic"
    )
    assert mic["state"] == "sağır"
    assert not mic["live"]


def test_self_written_modules_become_organs(tmp_path: Path) -> None:
    """Ajanın kendine yazdığı yetenek — harita, PLC, USB, ne yazdıysa —
    bedeninin bir parçası. Elle tutulan bir liste değil: atölyedeki
    dosyalardan okunuyor."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    root = config.open_sandbox().root
    skills.scaffold(root, "plc", "Omron PLC adreslerinden değer okur")

    body = organs.inventory(config)
    plc = next((o for o in body if o["id"] == "skill:plc"), None)

    assert plc is not None
    assert plc["kind"] == organs.MODULE
    assert "plc" in plc["tools"]
    assert "Omron" in plc["detail"]


def test_a_broken_module_does_not_empty_the_body(tmp_path: Path) -> None:
    """Yarım bırakılmış bir yetenek dosyası bütün organ listesini
    düşürmemeli: mikrofonun görünmemesi, bozuk bir dosyadan çok daha
    kötü bir hata."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    root = config.open_sandbox().root
    folder = skills.folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "yarim.py").write_text("def run(", encoding="utf-8")

    ids = {organ["id"] for organ in organs.inventory(config)}
    assert {"mic", "lens", "voice"} <= ids


def test_the_workshop_is_the_only_place_modules_live(tmp_path: Path) -> None:
    """Atölyenin dışına yazılmış bir Python dosyası yetenek sayılmıyor.

    Ajanın kendine yazdığı her şey kendi klasöründe kalmalı; oradan
    çıkan bir dosya hem sahnede görünmüyor hem de hiç yüklenmiyor.
    """
    config = Config.load(tmp_path)
    config.ensure_dirs()
    outside = tmp_path / "kacak.py"
    outside.write_text(
        'NAME = "kacak"\nDESCRIPTION = "x"\nSCHEMA = {}\ndef run(a, c): return ""\n',
        encoding="utf-8",
    )

    ids = {organ["id"] for organ in organs.inventory(config)}
    assert "skill:kacak" not in ids
