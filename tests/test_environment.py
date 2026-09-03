"""Environment-detection tests.

The distinction between the installed layout (installer wizard) and the
developer repo changes user-visible texts: in the installed layout pip is
not suggested, the wizard is. The console-less child-process flags are here
too — under pythonw every console call without flags flashed a cmd window
on screen.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dornick import listen, environment, voice, watch


def test_developer_repo_does_not_count_as_installed(tmp_path: Path, monkeypatch) -> None:
    """Neither ._pth nor setup.json: developer layout."""
    exe = tmp_path / "python" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    try:
        environment.is_installed.cache_clear()
        assert environment.is_installed() is False

        # The mark the wizard leaves: setup.json at the root.
        (tmp_path / "setup.json").write_text('{"dil": "tr"}', encoding="utf-8")
        environment.is_installed.cache_clear()
        assert environment.is_installed() is True

        # The old name is recognised too (existing installs).
        (tmp_path / "setup.json").unlink()
        (tmp_path / "kurulum.json").write_text('{"dil": "tr"}', encoding="utf-8")
        environment.is_installed.cache_clear()
        assert environment.is_installed() is True

        # The embedded-Python trace alone suffices: the ._pth file.
        (tmp_path / "kurulum.json").unlink()
        (exe.parent / "python311._pth").write_text("..\\src\n", encoding="ascii")
        environment.is_installed.cache_clear()
        assert environment.is_installed() is True
    finally:
        environment.is_installed.cache_clear()  # the fake path must not stay in the cache


def test_installed_layout_does_not_suggest_pip(monkeypatch) -> None:
    """In the installed layout the message points to the wizard, not pip."""
    monkeypatch.setattr(environment, "is_installed", lambda: True)
    for message in (listen.hint(), voice.hint(), watch.hint()):
        assert "pip install" not in message
        assert "sihirbaz" in message
    # Component names must match the ones in the wizard — the user will look for them.
    assert "Dinleme (mikrofon)" in listen.hint()
    assert "Kamera izleme" in watch.hint()


def test_developer_layout_suggests_pip(monkeypatch) -> None:
    monkeypatch.setattr(environment, "is_installed", lambda: False)
    assert listen.hint() == listen.INSTALL_HINT
    assert voice.hint() == voice.INSTALL_HINT
    assert watch.hint() == watch.INSTALL_HINT
    assert "pip install" in listen.hint()


def test_quiet_flags_do_not_open_a_console_window() -> None:
    """CREATE_NO_WINDOW on Windows; nothing on other platforms."""
    flags = environment.quiet_flags()
    if sys.platform == "win32":
        assert flags == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert flags == {}


# -- version -------------------------------------------------------------
#
# Which copy was installed was invisible in the field. The single source of
# truth is pyproject.toml: it sits at the root in the developer repo,
# build.ps1 puts it in the installed tree — read from the same place in both.


def test_version_is_read_from_pyproject() -> None:
    """version() must match the version in pyproject.toml exactly."""
    import re

    text = (environment._root() / "pyproject.toml").read_text(encoding="utf-8")
    expected = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)
    environment.version.cache_clear()
    try:
        assert environment.version() == expected
    finally:
        environment.version.cache_clear()


def test_version_is_read_from_a_fake_root(tmp_path: Path, monkeypatch) -> None:
    """Wherever the root moves (installed layout included) the pyproject
    there is read — the file itself speaks, not a path assumption."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "dornick"\nversion = "9.9.9"\n', encoding="utf-8")
    monkeypatch.setattr(environment, "_root", lambda: tmp_path)
    environment.version.cache_clear()
    try:
        assert environment.version() == "9.9.9"
    finally:
        environment.version.cache_clear()


def test_version_does_not_blow_up_on_a_broken_tree(tmp_path: Path, monkeypatch) -> None:
    """Without pyproject (a hand-broken install) a string must come back, not
    an exception — the UI must be able to open without a version too."""
    monkeypatch.setattr(environment, "_root", lambda: tmp_path)
    environment.version.cache_clear()
    try:
        value = environment.version()
        assert isinstance(value, str) and value
    finally:
        environment.version.cache_clear()


def test_version_parsing_swallows_the_v_prefix_and_text() -> None:
    assert environment._parse_version("v0.2.10") == (0, 2, 10)
    assert environment._parse_version("0.2.2") == (0, 2, 2)
    assert environment._parse_version("surum yok") == ()
    # The comparison is numeric: 0.2.10 > 0.2.9 (a string comparison misses this).
    assert environment._parse_version("0.2.10") > environment._parse_version("0.2.9")


# -- update check ----------------------------------------------------------
#
# Triggered MANUALLY only (Settings › Machine). The tests never go to the
# network: a fake opener is passed instead of urlopen.


class _FakeResponse:
    def __init__(self, body: dict) -> None:
        import json

        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass


def test_update_check_reports_a_newer_version(monkeypatch) -> None:
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    answer = environment.check_update(
        _ac=lambda *a, **k: _FakeResponse(
            {"tag_name": "v0.9.0", "html_url": "https://ornek/yayin"}))
    assert answer["ok"] and answer["yeni"] == "0.9.0"
    assert answer["url"] == "https://ornek/yayin"
    assert answer["mevcut"] == "0.2.2"


def test_update_check_finds_the_installer_asset(monkeypatch) -> None:
    """The installer .exe attached to the release comes back as a direct
    download link; with several exes the one named setup/kurulum is preferred."""
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    answer = environment.check_update(
        _ac=lambda *a, **k: _FakeResponse({
            "tag_name": "v0.9.0", "html_url": "https://ornek/yayin",
            "assets": [
                {"name": "araclar.exe",
                 "browser_download_url": "https://ornek/araclar.exe"},
                {"name": "dornick-setup-0.9.0.exe",
                 "browser_download_url": "https://ornek/setup.exe"},
            ]}))
    assert answer["yeni"] == "0.9.0"
    assert answer["indirme"] == "https://ornek/setup.exe"


def test_update_check_leaves_download_empty_without_assets(monkeypatch) -> None:
    """Without an exe in the release the download stays empty — the UI falls back to the release page."""
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    answer = environment.check_update(
        _ac=lambda *a, **k: _FakeResponse(
            {"tag_name": "v0.9.0", "html_url": "https://ornek/yayin"}))
    assert answer["yeni"] == "0.9.0" and answer["indirme"] == ""


def test_update_check_is_silent_on_the_same_version(monkeypatch) -> None:
    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    answer = environment.check_update(
        _ac=lambda *a, **k: _FakeResponse({"tag_name": "v0.2.2"}))
    assert answer["ok"] and answer["yeni"] == "" and answer["hata"] == ""


def test_update_check_gives_a_polite_error_offline(monkeypatch) -> None:
    """Without network a human-language error text must come back, not an exception."""
    import urllib.error

    def offline(*a, **k):
        raise urllib.error.URLError("dns yok")

    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    answer = environment.check_update(_ac=offline)
    assert not answer["ok"] and answer["yeni"] == ""
    assert "internet" in answer["hata"].lower() or "ağ" in answer["hata"].lower()


def test_update_check_says_so_when_there_is_no_release(monkeypatch) -> None:
    """404 (no release ever published / repo not visible) must not be confused with a network error."""
    import io
    import urllib.error

    def missing(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b""))

    monkeypatch.setattr(environment, "version", lambda: "0.2.2")
    answer = environment.check_update(_ac=missing)
    assert not answer["ok"]
    assert "sürüm" in answer["hata"].lower() or "yayın" in answer["hata"].lower()


# -- in-app update download (security) ---------------------------------
#
# Download+run is a dangerous action: the address must be ONLY the official
# GitHub release infrastructure (host filter) and the final (post-redirect)
# address must pass the same filter. A truncated/small download must not run.


class _FakeDownload:
    def __init__(self, body: bytes, final: str) -> None:
        self._body = body
        self._final = final
        self.headers = {"Content-Length": str(len(body))}
        self._read = False

    def geturl(self) -> str:
        return self._final

    def read(self, n: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a) -> None:
        pass


def test_download_only_from_a_trusted_address(tmp_path: Path) -> None:
    """Downloads outside github.com / *.githubusercontent.com are REFUSED."""
    import pytest

    with pytest.raises(ValueError, match="[Gg]üvenil"):
        environment.download_update("https://evil.example/setup.exe", tmp_path,
                               _ac=lambda *a, **k: _FakeDownload(b"x" * (2 * 1024 * 1024), "https://evil.example/setup.exe"))


def test_download_refuses_an_untrusted_redirect(tmp_path: Path) -> None:
    """Even if the first address is github, the download stops if the FINAL address is untrusted."""
    import pytest

    body = b"MZ" + b"0" * (2 * 1024 * 1024)
    opener = lambda *a, **k: _FakeDownload(body, "https://evil.example/gizli.exe")
    with pytest.raises(ValueError, match="[Yy]önlendirme"):
        environment.download_update(
            "https://github.com/dornick-dev/dornick/releases/download/v9/dornick-setup-9.exe",
            tmp_path, name="dornick-setup-9.exe", _ac=opener)


def test_successful_download_writes_the_file(tmp_path: Path) -> None:
    """Trusted address + sufficient size: the file lands on disk and its path is returned."""
    body = b"MZ" + b"0" * (2 * 1024 * 1024)
    final = "https://objects.githubusercontent.com/gh/abc"
    opener = lambda *a, **k: _FakeDownload(body, final)
    progress_calls: list[int] = []
    path = environment.download_update(
        "https://github.com/dornick-dev/dornick/releases/download/v9/dornick-setup-9.exe",
        tmp_path, name="dornick-setup-9.exe", expected_size=len(body),
        progress=lambda a, t: progress_calls.append(a), _ac=opener)
    assert path.is_file() and path.name == "dornick-setup-9.exe"
    assert path.read_bytes() == body
    assert progress_calls  # progress was called


def test_download_refuses_a_tiny_file(tmp_path: Path) -> None:
    """Under 1 MB cannot be an 'installer' — the file to be executed does not land."""
    import pytest

    opener = lambda *a, **k: _FakeDownload(b"kucuk", "https://github.com/x/y/z.exe")
    with pytest.raises(ValueError, match="küçük"):
        environment.download_update(
            "https://github.com/dornick-dev/dornick/releases/download/v9/z.exe",
            tmp_path, name="z.exe", _ac=opener)
