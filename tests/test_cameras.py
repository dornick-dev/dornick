"""Kamera kaynağı: USB indeksi ve RTSP kimlik bilgisi.

OpenCV yokken de çalışır — URL kurulumu GPU/önizlemeden bağımsız.
"""

from __future__ import annotations

from dornick.watch import Camera


def test_usb_connect_source_is_an_index() -> None:
    cam = Camera(id="a", name="Bilgisayar kamerası", kind="usb", source="0")
    assert cam.connect_source() == 0


def test_rtsp_embeds_credentials_but_public_dict_hides_them() -> None:
    cam = Camera(
        id="b", name="bahçe", kind="rtsp",
        host="192.168.1.10", port=554, path="/stream",
        user="admin", password="s3cret",
        source="rtsp://admin:s3cret@192.168.1.10:554/stream",
    )
    url = str(cam.connect_source())
    assert "s3cret" in url
    assert url.startswith("rtsp://admin:")
    pub = cam.public_dict()
    assert pub["has_password"] is True
    assert "password" not in pub
    assert "s3cret" not in str(pub["source"])


def test_old_source_only_records_still_open() -> None:
    cam = Camera(id="c", name="eski", source="rtsp://cam.local/live")
    assert cam.connect_source() == "rtsp://cam.local/live"


def test_builtin_is_index_zero_without_host() -> None:
    assert Camera(id="a", name="x", source="0", kind="usb").is_builtin()
    assert not Camera(id="b", name="bahçe", kind="rtsp", host="10.0.0.1").is_builtin()


def test_remember_writes_last_note(tmp_path) -> None:
    from dornick import watch

    cam = Camera(id="b", name="bahçe", kind="rtsp", host="10.0.0.1")
    watch.save(tmp_path, [cam])
    watch.remember(tmp_path, cam, "kişi, araba")
    loaded = watch.load(tmp_path)
    assert loaded[0].last_note == "kişi, araba"
    assert loaded[0].last_seen

