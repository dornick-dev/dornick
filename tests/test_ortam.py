"""Ortam algısı testleri.

Kurulu düzen (kurulum sihirbazı) ile geliştirici deposu ayrımı kullanıcıya
görünen metinleri değiştiriyor: kuruluda pip önerilmez, sihirbaz önerilir.
Konsolsuz alt süreç bayrakları da burada — pythonw altında bayraksız her
konsol çağrısı ekranda cmd penceresi parlatıyordu.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from neocp import listen, ortam, voice, watch


def test_gelistirici_deposu_kurulu_sayilmaz(tmp_path: Path, monkeypatch) -> None:
    """Ne ._pth ne setup.json: geliştirici düzeni."""
    exe = tmp_path / "python" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    try:
        ortam.kurulu_mu.cache_clear()
        assert ortam.kurulu_mu() is False

        # Sihirbazın bıraktığı işaret: kökte setup.json.
        (tmp_path / "setup.json").write_text('{"dil": "tr"}', encoding="utf-8")
        ortam.kurulu_mu.cache_clear()
        assert ortam.kurulu_mu() is True

        # Eski ad da tanınır (mevcut kurulumlar).
        (tmp_path / "setup.json").unlink()
        (tmp_path / "kurulum.json").write_text('{"dil": "tr"}', encoding="utf-8")
        ortam.kurulu_mu.cache_clear()
        assert ortam.kurulu_mu() is True

        # Gömülü Python izi tek başına yeter: ._pth dosyası.
        (tmp_path / "kurulum.json").unlink()
        (exe.parent / "python311._pth").write_text("..\\src\n", encoding="ascii")
        ortam.kurulu_mu.cache_clear()
        assert ortam.kurulu_mu() is True
    finally:
        ortam.kurulu_mu.cache_clear()  # sahte yol önbellekte kalmasın


def test_kuruluda_pip_onerilmez(monkeypatch) -> None:
    """Kurulu düzende mesaj sihirbaza yönlendirir, pip'e değil."""
    monkeypatch.setattr(ortam, "kurulu_mu", lambda: True)
    for mesaj in (listen.hint(), voice.hint(), watch.hint()):
        assert "pip install" not in mesaj
        assert "sihirbaz" in mesaj
    # Bileşen adları sihirbazdakiyle aynı olmalı — kullanıcı onu arayacak.
    assert "Dinleme (mikrofon)" in listen.hint()
    assert "Kamera izleme" in watch.hint()


def test_gelistiricide_pip_onerilir(monkeypatch) -> None:
    monkeypatch.setattr(ortam, "kurulu_mu", lambda: False)
    assert listen.hint() == listen.INSTALL_HINT
    assert voice.hint() == voice.INSTALL_HINT
    assert watch.hint() == watch.INSTALL_HINT
    assert "pip install" in listen.hint()


def test_sessiz_bayraklar_konsol_penceresi_actirmaz() -> None:
    """Windows'ta CREATE_NO_WINDOW; başka platformda hiçbir şey."""
    bayraklar = ortam.sessiz_bayraklar()
    if sys.platform == "win32":
        assert bayraklar == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert bayraklar == {}
