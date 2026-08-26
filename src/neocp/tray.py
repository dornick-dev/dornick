"""Sistem tepsisi.

Pencereyi kapatmak programı kapatmamalı. Ajanın arka planda durması gereken
işleri var: zamanlanmış görevler, kameraları izleyen alt ajanlar ve —
kullanıcı açtıysa — uyandırma sözünü bekleyen mikrofon. Pencere kapanınca
bunların hepsi ölürse "arka planda çalışıyor" demek anlamsız.

Bu yüzden kapatma düğmesi pencereyi **gizliyor**, yok etmiyor. Sayfa
çalışmaya devam ediyor: WebView2 gizli pencerede de betikleri koşturuyor,
yani mikrofon dinlemeyi sürdürüyor. "neo" duyulduğunda pencere kendiliğinden
geri geliyor.

Tepsi simgesi ayrı bir thread'de dönüyor. pywebview'in kendi döngüsü ana
thread'i istiyor ve ikisi aynı thread'i paylaşamıyor.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

# Simge ölçüsü. Windows tepsisi 16-32 px arası ölçekliyor; 64 hepsinde net.
SIZE = 64

INSTALL_HINT = "Sistem tepsisi için: pip install 'neocp[tray]'"


def available() -> bool:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _icon_image() -> Any:
    """Çekirdeğin küçük hali: ortada parlak bir nokta, çevresinde halka.

    Dosyadan okumak yerine çiziliyor — paketlenmiş bir uygulamada varlık
    yolu en sık kırılan şey ve simge kırılınca tepsi bomboş görünüyor.
    """
    # Tek kaynak: pencere ve sekmeyle AYNI işaret (logo modülü).
    from .logo import draw as draw_logo

    return draw_logo(SIZE)


class Tray:
    """Tepsi simgesi ve menüsü.

    `show`/`hide`/`quit` dışarıdan veriliyor: bu sınıf pencereyi tanımıyor,
    yalnızca çağrıları taşıyor.
    """

    def __init__(
        self,
        *,
        show: Callable[[], None],
        hide: Callable[[], None],
        quit: Callable[[], None],
        title: str = "neo",
    ) -> None:
        self.show = show
        self.hide = hide
        self.quit = quit
        self.title = title
        self._icon: Any = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Simgeyi ayrı bir thread'de açar. Paket yoksa False."""
        if not available():
            return False

        import pystray

        self._icon = pystray.Icon(
            "neo",
            _icon_image(),
            self.title,
            menu=pystray.Menu(
                # İlk madde varsayılan: simgeye çift tıklayınca bu çalışıyor.
                pystray.MenuItem("Göster", self._show, default=True),
                pystray.MenuItem("Gizle", self._hide),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Çık", self._quit),
            ),
        )

        # pywebview ana thread'i istiyor; tepsi ayrı thread'de dönmek zorunda.
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="neo-tray")
        self._thread.start()
        return True

    def note(self, text: str) -> None:
        """Tepsiden bildirim. Desteklenmiyorsa sessizce geçiliyor."""
        if self._icon is None:
            return
        try:
            self._icon.notify(text, self.title)
        except Exception:
            pass

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    # -- menü çağrıları ------------------------------------------------
    #
    # pystray geri çağrılara (icon, item) veriyor; bizim işimize yaramıyor
    # ve hatası menüyü sessizce kırıyor, o yüzden sarmalanıyor.

    def _show(self, *_args: Any) -> None:
        _safely(self.show)

    def _hide(self, *_args: Any) -> None:
        _safely(self.hide)

    def _quit(self, *_args: Any) -> None:
        self.stop()
        _safely(self.quit)


def _safely(fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception:
        # Tepsi menüsündeki bir hata programı düşürmemeli; en kötü ihtimalle
        # o tıklama işe yaramaz.
        pass
