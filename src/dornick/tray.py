"""Sistem tepsisi.

Pencereyi kapatmak programı kapatmamalı. Ajanın arka planda durması gereken
işleri var: zamanlanmış görevler, kameraları izleyen alt ajanlar ve —
kullanıcı açtıysa — uyandırma sözünü bekleyen mikrofon. Pencere kapanınca
bunların hepsi ölürse "arka planda çalışıyor" demek anlamsız.

Bu yüzden kapatma düğmesi pencereyi **gizliyor**, yok etmiyor. Sayfa
çalışmaya devam ediyor: WebView2 gizli pencerede de betikleri koşturuyor,
yani mikrofon dinlemeyi sürdürüyor. "dornick" duyulduğunda pencere kendiliğinden
geri geliyor.

Tepsi simgesi ayrı bir thread'de dönüyor. pywebview'in kendi döngüsü ana
thread'i istiyor ve ikisi aynı thread'i paylaşamıyor.
"""

from __future__ import annotations

import sys
import threading
from typing import Any, Callable

# Simge ölçüsü. Windows tepsisi 16-32 px arası ölçekliyor; 64 hepsinde net.
SIZE = 64

INSTALL_HINT = "Sistem tepsisi için: pip install 'dornick[tray]'"

# X'e basılınca iş sürüyorsa gösterilen balon. Yalnızca İLK seferde —
# her gizlenişte bildirim basmak rahatsız eder, bir kez öğretmek yeter.
ARKA_PLAN_NOTU = ("dornick arka planda — zamanlanmış görevler ve otomasyonlar "
                  "çalışmaya devam eder; tepsiden açabilirsin")

# Zamanlanmış / otomasyon işi bittiğinde Windows tepsi bildirimi.
GOREV_BITTI = "Görev tamamlandı: {title}"
GOREV_HATA = "Görev hata verdi: {title}"


def gorev_bildirim_metni(title: str, *, ok: bool) -> str:
    """Koşu bitiş balonu metni — test edilebilir, UI'dan bağımsız."""
    sablon = GOREV_BITTI if ok else GOREV_HATA
    ad = (title or "görev").strip() or "görev"
    if len(ad) > 80:
        ad = ad[:79] + "…"
    return sablon.format(title=ad)


def _xml_esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def toast_xml(title: str, body: str, icon_uri: str) -> str:
    """WinRT toast gövdesi — logo `appLogoOverride` ile solda durur."""
    return (
        "<toast><visual><binding template='ToastGeneric'>"
        f"<text>{_xml_esc(title)}</text>"
        f"<text>{_xml_esc(body)}</text>"
        f"<image placement='appLogoOverride' hint-crop='circle' src='{_xml_esc(icon_uri)}'/>"
        "</binding></visual></toast>"
    )


def _windows_toast(title: str, body: str) -> bool:
    """WinRT toast. Başarısızsa False — çağıran pystray balonuna düşer."""
    if sys.platform != "win32":
        return False
    try:
        import subprocess
        import tempfile
        from pathlib import Path

        from . import ortam
        from .logo import png_path
        from .winicon import AUMID

        png = png_path()
        if not png.exists():
            return False
        xml = toast_xml(title or "dornick", body, png.resolve().as_uri())
        xml_path = Path(tempfile.gettempdir()) / "dornick-toast.xml"
        xml_path.write_text(xml, encoding="utf-8")
        q = str(xml_path).replace("'", "''")
        app = AUMID.replace("'", "''")
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, "
            "Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, "
            "ContentType = WindowsRuntime] | Out-Null; "
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
            f"$xml.LoadXml([System.IO.File]::ReadAllText('{q}', [System.Text.Encoding]::UTF8)); "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
            f"$n = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app}'); "
            "$n.Show($toast)"
        )
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            timeout=12, **ortam.sessiz_bayraklar(),
        )
        return done.returncode == 0
    except Exception:
        return False

# Tepsiden Çıkış seçildi ama ajan meşgul: yarım kalacak işin onayı.
CIKIS_SORUSU = ("Bir iş sürüyor; çıkarsan yarım kalır (kaldığın yerden "
                "sürdürülebilir).\n\nYine de çık?")


def kapatma_karari(tepsi_acik: bool) -> str:
    """X'e basılınca ne olur: tepsi yaşıyorsa pencere GİZLENİR, uygulama
    tepside sürer (Claude Code / masaüstü geleneği). Tepsi yoksa gizlemek
    programı kapanmaz hale getirirdi — gerçekten kapatılır."""
    return "gizle" if tepsi_acik else "kapat"


def cikis_karari(mesgul: bool, onayla: Callable[[str], bool] | None) -> bool:
    """Tepsiden Çıkış seçildi: çıkılsın mı?

    Ajan meşgulse kullanıcıya sorulur — yarım kalacak işten haberi olsun.
    Boştaysa sorgusuz çıkılır. Onay sorulamıyorsa (diyalog yok/patladı)
    kullanıcının açık jesti kazanır: çıkılır — "çıkamıyorum" durumu,
    yarım işten daha kötü bir tuzak.
    """
    if not mesgul:
        return True
    if onayla is None:
        return True
    try:
        return bool(onayla(CIKIS_SORUSU))
    except Exception:
        return True


class Kapanis:
    """X ile "Çıkış"ı ayıran bayrak.

    İkisi de pencere katmanının AYNI olayına (pywebview `closing`) düşüyor:
    X'e basmak da, `destroy()` çağırmak da. Olay tek başına niyeti
    taşımadığı için, ayrımı burada tutulan bayrak yapıyor.

    Bayrak olmadan tepsideki Çıkış sessizce gizlemeye düşüyordu: kullanıcı
    onay penceresinde Evet diyor, `destroy()` çağrılıyor, `closing` kancası
    "bu bir X'tir" varsayıp kapanışı iptal ediyor. Program yaşamaya devam
    ediyor — üstelik tepsi simgesi çoktan kapandığı için geri de gelinemiyor.
    """

    def __init__(self, gizle: Callable[[], None], yok_et: Callable[[], None]) -> None:
        self._gizle = gizle
        self._yok_et = yok_et
        self._cikiliyor = False

    @property
    def cikiliyor(self) -> bool:
        return self._cikiliyor

    def cik(self) -> None:
        """Tepsiden Çıkış: bayrağı kaldır, sonra pencereyi yok et."""
        self._cikiliyor = True
        self._yok_et()

    def kapanabilir_mi(self) -> bool:
        """`closing` olayının dönüş değeri: True kapan, False iptal et."""
        if self._cikiliyor:
            return True
        self._gizle()
        return False


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
        title: str = "dornick",
        busy: Callable[[], bool] | None = None,
        confirm: Callable[[str], bool] | None = None,
        jobs: Callable[[], None] | None = None,
    ) -> None:
        self.show = show
        self.hide = hide
        self.quit = quit
        self.title = title
        # Çıkış bekçisi: ajan meşgulken Çıkış seçilirse `confirm` ile
        # sorulur — süren iş sessizce ölmesin. İkisi de isteğe bağlı:
        # verilmezse eski davranış (sorgusuz çıkış) aynen durur.
        self.busy = busy
        self.confirm = confirm
        # Tepsiden Görevler: pencereyi açıp HUD Görevler panelini getirir.
        self.jobs = jobs
        self._icon: Any = None
        self._thread: threading.Thread | None = None
        # Bir kez gösterilmiş balonlar. "Arka planda çalışmaya devam
        # ediyor" bilgisi ÖĞRETİCİ: ilk gizlenişte gerekli, her
        # gizlenişte rahatsız edici.
        self._gosterilen: set[str] = set()

    def start(self) -> bool:
        """Simgeyi ayrı bir thread'de açar. Paket yoksa False."""
        if not available():
            return False

        import pystray

        self._icon = pystray.Icon(
            "dornick",
            _icon_image(),
            self.title,
            menu=pystray.Menu(
                # İlk madde varsayılan: simgeye çift tıklayınca bu çalışıyor.
                pystray.MenuItem("Göster", self._show, default=True),
                pystray.MenuItem("Görevler", self._jobs),
                pystray.MenuItem("Gizle", self._hide),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Çıkış", self._quit),
            ),
        )

        # pywebview ana thread'i istiyor; tepsi ayrı thread'de dönmek zorunda.
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="dornick-tray")
        self._thread.start()
        return True

    def note(self, text: str) -> None:
        """Tepsiden bildirim. Desteklenmiyorsa sessizce geçiliyor.

        Windows 10/11 toast pystray balonunu Python yılanıyla gösteriyor;
        WinRT bildirimi logoyu `appLogoOverride` ile basıyor.
        """
        if _windows_toast(self.title, text):
            return
        if self._icon is None:
            return
        try:
            self._icon.notify(text, self.title)
        except Exception:
            pass

    def note_once(self, text: str) -> bool:
        """Aynı balonu ömürde bir kez basar. Bastıysa True.

        X'e ilk basışta "dornick arka planda çalışmaya devam ediyor" demek
        gerekiyor — pencere kaybolunca kullanıcı programın kapandığını
        sanıyor. İkinci kez demek ise öğretmek değil, dırdır.
        """
        if text in self._gosterilen:
            return False
        self._gosterilen.add(text)
        self.note(text)
        return True

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

    def _jobs(self, *_args: Any) -> None:
        # Ayrı `jobs` yoksa en azından pencereyi göster — menü kırılmasın.
        _safely(self.jobs or self.show)

    def _hide(self, *_args: Any) -> None:
        _safely(self.hide)

    def _quit(self, *_args: Any) -> None:
        # Meşgulken onay: yarım kalacak iş varsa kullanıcı bilerek çıksın.
        # `busy` sorgusu patlarsa meşgul DEĞİL sayılır — çıkışı kilitleme.
        mesgul = False
        if self.busy is not None:
            try:
                mesgul = bool(self.busy())
            except Exception:
                mesgul = False
        if not cikis_karari(mesgul, self.confirm):
            return
        self.stop()
        _safely(self.quit)


def _safely(fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception:
        # Tepsi menüsündeki bir hata programı düşürmemeli; en kötü ihtimalle
        # o tıklama işe yaramaz.
        pass
