"""Bilgisayar açıldığında kendiliğinden başlama.

Tepside sürekli çalışan, "hey neo" ile uyanan bir ajanın her açılışta elle
başlatılması gerekiyorsa otonom değil demektir.

Kayıt yeri `HKCU\\...\\Run`: yalnızca bu kullanıcı için, yönetici hakkı
istemeden, tek bir değerle. Sistem geneline (HKLM) yazmıyoruz — bir
kullanıcının tercihi bütün makineyi bağlamamalı.

Kapatmak da aynı yerden: değeri silmek yetiyor. Kullanıcı isterse
`regedit` ile ya da Görev Yöneticisi › Başlangıç sekmesinden de görebiliyor;
gizli bir şey bırakmıyoruz.
"""

from __future__ import annotations

import sys

# Kayıttaki ad. Görev Yöneticisi'nin başlangıç listesinde bu görünüyor.
NAME = "neo"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def available() -> bool:
    """Yalnızca Windows. Başka yerde ayar gösterilmiyor."""
    return sys.platform == "win32"


def command() -> str:
    """Açılışta çalıştırılacak satır.

    Damgalı `neo.exe` (yoksa `pythonw`) seçiliyor: `python` bir konsol
    penceresi açıyor ve her açılışta ekranın ortasında siyah bir kutu
    beliriyor. Görev Yöneticisi de ev sahibi PE'nin simgesini gösterdiği
    için pythonw yerine damgalı kopya gerekir.
    """
    from .winicon import app_executable

    runner = app_executable()
    return f'"{runner}" -m neocp.cli --app'


def enabled() -> bool:
    if not available():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, NAME)
    except OSError:
        return False
    return bool(value)


def current() -> str:
    """Kayıtta duran satır. Ayar sayfası bunu gösteriyor: kullanıcı neyin
    yazıldığını görebilmeli."""
    if not available():
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, NAME)
    except OSError:
        return ""
    return str(value)


def enable() -> str:
    """Açılışa ekler. Yazılan satırı döndürür."""
    if not available():
        raise RuntimeError("Otomatik başlatma yalnızca Windows'ta.")
    import winreg

    line = command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, line)
    return line


def disable() -> None:
    """Açılıştan çıkarır. Yoksa sessizce geçiyor."""
    if not available():
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, NAME)
    except OSError:
        pass


def apply(on: bool) -> str:
    if on:
        return enable()
    disable()
    return ""
