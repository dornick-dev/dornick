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

from dornick import listen, environment, voice, watch


def test_gelistirici_deposu_kurulu_sayilmaz(tmp_path: Path, monkeypatch) -> None:
    """Ne ._pth ne setup.json: geliştirici düzeni."""
    exe = tmp_path / "python" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    try:
        environment.kurulu_mu.cache_clear()
        assert environment.kurulu_mu() is False

        # Sihirbazın bıraktığı işaret: kökte setup.json.
        (tmp_path / "setup.json").write_text('{"dil": "tr"}', encoding="utf-8")
        environment.kurulu_mu.cache_clear()
        assert environment.kurulu_mu() is True

        # Eski ad da tanınır (mevcut kurulumlar).
        (tmp_path / "setup.json").unlink()
        (tmp_path / "kurulum.json").write_text('{"dil": "tr"}', encoding="utf-8")
        environment.kurulu_mu.cache_clear()
        assert environment.kurulu_mu() is True

        # Gömülü Python izi tek başına yeter: ._pth dosyası.
        (tmp_path / "kurulum.json").unlink()
        (exe.parent / "python311._pth").write_text("..\\src\n", encoding="ascii")
        environment.kurulu_mu.cache_clear()
        assert environment.kurulu_mu() is True
    finally:
        environment.kurulu_mu.cache_clear()  # sahte yol önbellekte kalmasın


def test_kuruluda_pip_onerilmez(monkeypatch) -> None:
    """Kurulu düzende mesaj sihirbaza yönlendirir, pip'e değil."""
    monkeypatch.setattr(environment, "kurulu_mu", lambda: True)
    for mesaj in (listen.hint(), voice.hint(), watch.hint()):
        assert "pip install" not in mesaj
        assert "sihirbaz" in mesaj
    # Bileşen adları sihirbazdakiyle aynı olmalı — kullanıcı onu arayacak.
    assert "Dinleme (mikrofon)" in listen.hint()
    assert "Kamera izleme" in watch.hint()


def test_gelistiricide_pip_onerilir(monkeypatch) -> None:
    monkeypatch.setattr(environment, "kurulu_mu", lambda: False)
    assert listen.hint() == listen.INSTALL_HINT
    assert voice.hint() == voice.INSTALL_HINT
    assert watch.hint() == watch.INSTALL_HINT
    assert "pip install" in listen.hint()


def test_sessiz_bayraklar_konsol_penceresi_actirmaz() -> None:
    """Windows'ta CREATE_NO_WINDOW; başka platformda hiçbir şey."""
    bayraklar = environment.quiet_flags()
    if sys.platform == "win32":
        assert bayraklar == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert bayraklar == {}


# -- sürüm ---------------------------------------------------------------
#
# Sahada hangi kopyanın kurulu olduğu görünmüyordu. Tek gerçek kaynak
# pyproject.toml: geliştirici deposunda kökte durur, kurulu ağaca
# build.ps1 koyar — ikisinde de aynı yerden okunur.


def test_surum_pyprojecttan_okunur() -> None:
    """surum() pyproject.toml'daki version ile birebir aynı olmalı."""
    import re

    metin = (environment._root() / "pyproject.toml").read_text(encoding="utf-8")
    beklenen = re.search(r'^version\s*=\s*"([^"]+)"', metin, re.M).group(1)
    environment.version.cache_clear()
    try:
        assert environment.version() == beklenen
    finally:
        environment.version.cache_clear()


def test_surum_sahte_kokten_okunur(tmp_path: Path, monkeypatch) -> None:
    """Kök nereye taşınırsa taşınsın (kurulu düzen dahil) oradaki
    pyproject okunur — yol varsayımı değil, dosyanın kendisi konuşur."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "dornick"\nversion = "9.9.9"\n', encoding="utf-8")
    monkeypatch.setattr(environment, "_root", lambda: tmp_path)
    environment.version.cache_clear()
    try:
        assert environment.version() == "9.9.9"
    finally:
        environment.version.cache_clear()


def test_surum_bozuk_agacta_patlamaz(tmp_path: Path, monkeypatch) -> None:
    """pyproject yoksa (elle bozulmuş kurulum) istisna değil, bir dizgi
    dönmeli — arayüz sürümsüz de açılabilmeli."""
    monkeypatch.setattr(environment, "_root", lambda: tmp_path)
    environment.version.cache_clear()
    try:
        deger = environment.version()
        assert isinstance(deger, str) and deger
    finally:
        environment.version.cache_clear()


def test_surum_parcalama_v_onekini_ve_metni_yutar() -> None:
    assert environment._parse_version("v0.2.10") == (0, 2, 10)
    assert environment._parse_version("0.2.2") == (0, 2, 2)
    assert environment._parse_version("surum yok") == ()
    # Karşılaştırma sayısal: 0.2.10 > 0.2.9 (dizgi kıyası bunu ıskalar).
    assert environment._parse_version("0.2.10") > environment._parse_version("0.2.9")


# -- güncelleme denetimi -------------------------------------------------
#
# YALNIZ elle tetiklenir (Ayarlar › Makine). Testler ağa hiç çıkmaz:
# urlopen yerine sahte açıcı veriliyor.


class _SahteCevap:
    def __init__(self, govde: dict) -> None:
        import json

        self._govde = json.dumps(govde).encode("utf-8")

    def read(self) -> bytes:
        return self._govde

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass


def test_guncelleme_yeni_surum_varsa_soyler(monkeypatch) -> None:
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    cevap = environment.check_update(
        _ac=lambda *a, **k: _SahteCevap(
            {"tag_name": "v0.9.0", "html_url": "https://ornek/yayin"}))
    assert cevap["ok"] and cevap["yeni"] == "0.9.0"
    assert cevap["url"] == "https://ornek/yayin"
    assert cevap["mevcut"] == "0.2.2"


def test_guncelleme_kurulum_varligini_bulur(monkeypatch) -> None:
    """Yayına eklenmiş kurulum .exe'si doğrudan indirme bağlantısı olarak
    dönüyor; birden çok exe varsa adında setup/kurulum geçen yeğleniyor."""
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    cevap = environment.check_update(
        _ac=lambda *a, **k: _SahteCevap({
            "tag_name": "v0.9.0", "html_url": "https://ornek/yayin",
            "assets": [
                {"name": "araclar.exe",
                 "browser_download_url": "https://ornek/araclar.exe"},
                {"name": "dornick-setup-0.9.0.exe",
                 "browser_download_url": "https://ornek/setup.exe"},
            ]}))
    assert cevap["yeni"] == "0.9.0"
    assert cevap["indirme"] == "https://ornek/setup.exe"


def test_guncelleme_varliksiz_yayinda_indirme_bos(monkeypatch) -> None:
    """Yayında exe yoksa indirme boş kalır — arayüz yayın sayfasına düşer."""
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    cevap = environment.check_update(
        _ac=lambda *a, **k: _SahteCevap(
            {"tag_name": "v0.9.0", "html_url": "https://ornek/yayin"}))
    assert cevap["yeni"] == "0.9.0" and cevap["indirme"] == ""


def test_guncelleme_ayni_surumde_sessiz(monkeypatch) -> None:
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    cevap = environment.check_update(
        _ac=lambda *a, **k: _SahteCevap({"tag_name": "v0.2.2"}))
    assert cevap["ok"] and cevap["yeni"] == "" and cevap["hata"] == ""


def test_guncelleme_agsizken_kibar_hata(monkeypatch) -> None:
    """Ağ yoksa istisna değil, insan diliyle bir hata metni dönmeli."""
    import urllib.error

    def agsiz(*a, **k):
        raise urllib.error.URLError("dns yok")

    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    cevap = environment.check_update(_ac=agsiz)
    assert not cevap["ok"] and cevap["yeni"] == ""
    assert "internet" in cevap["hata"].lower() or "ağ" in cevap["hata"].lower()


def test_guncelleme_yayin_yoksa_dogru_soyler(monkeypatch) -> None:
    """404 (yayın hiç yapılmamış/depo görünmüyor) ağ hatasıyla karışmasın."""
    import io
    import urllib.error

    def yok(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b""))

    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    cevap = environment.check_update(_ac=yok)
    assert not cevap["ok"]
    assert "sürüm" in cevap["hata"].lower() or "yayın" in cevap["hata"].lower()


# -- uygulama içi güncelleme indirmesi (güvenlik) ----------------------
#
# İndirme+çalıştırma tehlikeli bir eylem: adres YALNIZ resmî GitHub yayın
# altyapısından olmalı (host süzgeci) ve nihai (yönlendirme sonrası) adres
# de aynı süzgeçten geçmeli. Kesik/küçük indirme çalıştırılmamalı.


class _SahteIndirme:
    def __init__(self, govde: bytes, nihai: str) -> None:
        self._govde = govde
        self._nihai = nihai
        self.headers = {"Content-Length": str(len(govde))}
        self._okundu = False

    def geturl(self) -> str:
        return self._nihai

    def read(self, n: int = -1) -> bytes:
        if self._okundu:
            return b""
        self._okundu = True
        return self._govde

    def __enter__(self):
        return self

    def __exit__(self, *a) -> None:
        pass


def test_indirme_yalniz_guvenilir_adresten(tmp_path: Path) -> None:
    """github.com / *.githubusercontent.com dışına indirme REDDEDİLİR."""
    import pytest

    with pytest.raises(ValueError, match="[Gg]üvenil"):
        environment.download_update("https://evil.example/setup.exe", tmp_path,
                               _ac=lambda *a, **k: _SahteIndirme(b"x" * (2 * 1024 * 1024), "https://evil.example/setup.exe"))


def test_indirme_yonlendirme_guvenilmezse_reddeder(tmp_path: Path) -> None:
    """İlk adres github olsa da NİHAİ adres güvenilmezse indirme durur."""
    import pytest

    govde = b"MZ" + b"0" * (2 * 1024 * 1024)
    ac = lambda *a, **k: _SahteIndirme(govde, "https://evil.example/gizli.exe")
    with pytest.raises(ValueError, match="[Yy]önlendirme"):
        environment.download_update(
            "https://github.com/dornick-dev/dornick/releases/download/v9/dornick-setup-9.exe",
            tmp_path, ad="dornick-setup-9.exe", _ac=ac)


def test_indirme_basarili_dosya_yazar(tmp_path: Path) -> None:
    """Güvenilir adres + yeterli boyut: dosya diske iner ve yolu döner."""
    govde = b"MZ" + b"0" * (2 * 1024 * 1024)
    nihai = "https://objects.githubusercontent.com/gh/abc"
    ac = lambda *a, **k: _SahteIndirme(govde, nihai)
    yuzdeler: list[int] = []
    yol = environment.download_update(
        "https://github.com/dornick-dev/dornick/releases/download/v9/dornick-setup-9.exe",
        tmp_path, ad="dornick-setup-9.exe", beklenen_boyut=len(govde),
        progress=lambda a, t: yuzdeler.append(a), _ac=ac)
    assert yol.is_file() and yol.name == "dornick-setup-9.exe"
    assert yol.read_bytes() == govde
    assert yuzdeler  # ilerleme çağrıldı


def test_indirme_cok_kucukse_reddeder(tmp_path: Path) -> None:
    """1 MB altı bir 'kurulum' olamaz — çalıştırılacak dosya inmez."""
    import pytest

    ac = lambda *a, **k: _SahteIndirme(b"kucuk", "https://github.com/x/y/z.exe")
    with pytest.raises(ValueError, match="küçük"):
        environment.download_update(
            "https://github.com/dornick-dev/dornick/releases/download/v9/z.exe",
            tmp_path, ad="z.exe", _ac=ac)
