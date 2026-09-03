"""System tray.

Closing the window must not close the program. The agent has work that has
to keep going in the background: scheduled tasks, sub-agents watching the
cameras and — if the user turned it on — the microphone waiting for the
wake word. If all of those die when the window closes, "runs in the
background" means nothing.

That is why the close button **hides** the window rather than destroying
it. The page keeps running: WebView2 keeps executing scripts in a hidden
window, so the microphone keeps listening. When "dornick" is heard the
window comes back by itself.

The tray icon spins on a separate thread. pywebview's own loop wants the
main thread and the two cannot share it.
"""

from __future__ import annotations

import sys
import threading
from typing import Any, Callable

# Icon size. The Windows tray scales between 16-32 px; 64 is crisp on all.
SIZE = 64

INSTALL_HINT = "Sistem tepsisi için: pip install 'dornick[tray]'"

# Balloon shown when X is pressed while work is running. Only the FIRST
# time — a notification on every hide annoys, teaching once is enough.
BACKGROUND_NOTE = ("Dornick arka planda — zamanlanmış görevler ve otomasyonlar "
                  "çalışmaya devam eder; tepsiden açabilirsin")

# Windows tray notification when a scheduled / automation job finishes.
TASK_DONE_NOTE = "Görev tamamlandı: {title}"
TASK_FAILED_NOTE = "Görev hata verdi: {title}"


def task_notification_text(title: str, *, ok: bool) -> str:
    """Text of the run-finished balloon — testable, independent of the UI."""
    template = TASK_DONE_NOTE if ok else TASK_FAILED_NOTE
    name = (title or "görev").strip() or "görev"
    if len(name) > 80:
        name = name[:79] + "…"
    return template.format(title=name)


def _xml_esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def toast_xml(title: str, body: str, icon_uri: str) -> str:
    """WinRT toast body — the logo sits on the left via `appLogoOverride`."""
    return (
        "<toast><visual><binding template='ToastGeneric'>"
        f"<text>{_xml_esc(title)}</text>"
        f"<text>{_xml_esc(body)}</text>"
        f"<image placement='appLogoOverride' hint-crop='circle' src='{_xml_esc(icon_uri)}'/>"
        "</binding></visual></toast>"
    )


def _windows_toast(title: str, body: str) -> bool:
    """WinRT toast. False on failure — the caller falls back to the pystray balloon."""
    if sys.platform != "win32":
        return False
    try:
        import subprocess
        import tempfile
        from pathlib import Path

        from . import environment
        from .logo import png_path
        from .winicon import AUMID

        png = png_path()
        if not png.exists():
            return False
        xml = toast_xml(title or "Dornick", body, png.resolve().as_uri())
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
            timeout=12, **environment.quiet_flags(),
        )
        return done.returncode == 0
    except Exception:
        return False

# Exit chosen from the tray but the agent is busy: confirmation for the work
# that will be left unfinished.
EXIT_QUESTION = ("Bir iş sürüyor; çıkarsan yarım kalır (kaldığın yerden "
                "sürdürülebilir).\n\nYine de çık?")


def close_decision(tray_alive: bool) -> str:
    """What happens on X: if the tray is alive the window is HIDDEN and the
    app lives on in the tray (Claude Code / desktop tradition). Without a
    tray, hiding would make the program impossible to close — it really
    closes."""
    return "gizle" if tray_alive else "kapat"


def exit_decision(busy: bool, confirm: Callable[[str], bool] | None) -> bool:
    """Exit chosen from the tray: should we quit?

    If the agent is busy the user is asked — so they know about the work
    that will be left unfinished. If idle, quit without asking. If the
    confirmation cannot be asked (no dialog / it blew up) the user's
    explicit gesture wins: quit — the "I can't quit" situation is a worse
    trap than unfinished work.
    """
    if not busy:
        return True
    if confirm is None:
        return True
    try:
        return bool(confirm(EXIT_QUESTION))
    except Exception:
        return True


class Shutdown:
    """The flag that separates X from "Exit".

    Both land on the SAME event of the window layer (pywebview `closing`):
    pressing X as well as calling `destroy()`. Since the event alone does
    not carry the intent, the flag held here makes the distinction.

    Without the flag, Exit from the tray silently fell through to hiding:
    the user says Yes in the confirmation dialog, `destroy()` is called, the
    `closing` hook assumes "this is an X" and cancels the close. The program
    keeps living — and since the tray icon has already gone there is no way
    back either.
    """

    def __init__(self, hide: Callable[[], None], destroy: Callable[[], None]) -> None:
        self._hide = hide
        self._destroy = destroy
        self._quitting = False

    @property
    def quitting(self) -> bool:
        return self._quitting

    def quit(self) -> None:
        """Exit from the tray: raise the flag, then destroy the window."""
        self._quitting = True
        self._destroy()

    def may_close(self) -> bool:
        """Return value of the `closing` event: True close, False cancel."""
        if self._quitting:
            return True
        self._hide()
        return False


def available() -> bool:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _icon_image() -> Any:
    """The small form of the core: a bright dot in the middle, a ring around it.

    Drawn rather than read from a file — in a packaged application the
    asset path is the thing that breaks most often, and with a broken icon
    the tray looks empty.
    """
    # Single source: the SAME mark as the window and the tab (logo module).
    from .logo import draw as draw_logo

    return draw_logo(SIZE)


class Tray:
    """Tray icon and menu.

    `show`/`hide`/`quit` are supplied from outside: this class does not know
    the window, it only carries the calls.
    """

    def __init__(
        self,
        *,
        show: Callable[[], None],
        hide: Callable[[], None],
        quit: Callable[[], None],
        title: str = "Dornick",
        busy: Callable[[], bool] | None = None,
        confirm: Callable[[str], bool] | None = None,
        jobs: Callable[[], None] | None = None,
        guard: Callable[[], None] | None = None,
    ) -> None:
        self.show = show
        self.hide = hide
        self.quit = quit
        self.title = title
        # Exit guard: if Exit is chosen while the agent is busy, `confirm`
        # asks — the running work must not die silently. Both optional: if
        # not given the old behaviour (quit without asking) stays as is.
        self.busy = busy
        self.confirm = confirm
        # Tasks from the tray: opens the window and brings the HUD Tasks panel.
        self.jobs = jobs
        # Exit guard hook: installed after the user has confirmed Exit (see
        # install_exit_guard). Optional — tests and old callers don't pass
        # it and never meet a process-killing side effect.
        self.guard = guard
        self._icon: Any = None
        self._thread: threading.Thread | None = None
        # Balloons shown once. The "keeps running in the background" note
        # is INSTRUCTIVE: needed on the first hide, annoying on every hide.
        self._shown: set[str] = set()

    def start(self) -> bool:
        """Opens the icon on a separate thread. False if the package is missing."""
        if not available():
            return False

        import pystray

        self._icon = pystray.Icon(
            "dornick",
            _icon_image(),
            self.title,
            menu=pystray.Menu(
                # The first item is the default: double-clicking the icon runs it.
                pystray.MenuItem("Göster", self._show, default=True),
                pystray.MenuItem("Görevler", self._jobs),
                pystray.MenuItem("Gizle", self._hide),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Çıkış", self._quit),
            ),
        )

        # pywebview wants the main thread; the tray has to spin on its own thread.
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="dornick-tray")
        self._thread.start()
        return True

    def note(self, text: str) -> None:
        """Notification from the tray. Silently skipped if unsupported.

        The Windows 10/11 toast shows the pystray balloon with the Python
        snake; the WinRT notification prints the logo via `appLogoOverride`.
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
        """Shows the same balloon once in a lifetime. True if it was shown.

        On the first press of X we have to say "dornick keeps running in the
        background" — when the window vanishes the user thinks the program
        closed. Saying it a second time is not teaching, it is nagging.
        """
        if text in self._shown:
            return False
        self._shown.add(text)
        self.note(text)
        return True

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    # -- menu callbacks -------------------------------------------------
    #
    # pystray passes (icon, item) to the callbacks; we have no use for them
    # and an error in one silently breaks the menu, so they are wrapped.

    def _show(self, *_args: Any) -> None:
        _safely(self.show)

    def _jobs(self, *_args: Any) -> None:
        # Without a separate `jobs` at least show the window — don't break the menu.
        _safely(self.jobs or self.show)

    def _hide(self, *_args: Any) -> None:
        _safely(self.hide)

    def _quit(self, *_args: Any) -> None:
        # Confirmation while busy: if work would be left unfinished the user
        # quits knowingly. If the `busy` probe blows up it counts as NOT busy
        # — don't lock the exit.
        is_busy = False
        if self.busy is not None:
            try:
                is_busy = bool(self.busy())
            except Exception:
                is_busy = False
        if not exit_decision(is_busy, self.confirm):
            return
        # Guard: the user CONFIRMED Exit — this gesture must end with the
        # process under every condition (live wound, 01.09: "I said exit
        # from the tray, said ok, and it can't even do that" — they were
        # forced to the task manager). The hook is supplied by the app; in
        # tests/old callers it is absent.
        if self.guard is not None:
            _safely(self.guard)
        self.stop()
        _safely(self.quit)


def install_exit_guard(grace_s: float = 12.0) -> None:
    """Guard that guarantees a confirmed Exit ends with the process.

    If the window layer (pywebview/GUI thread) is locked, `destroy()` can
    silently hang. The graceful shutdown is granted `grace_s`; when the time
    is up the process is taken down for good. The thread is a daemon: if the
    graceful path wins the process ends anyway, the guard does not hold it.
    ONLY the real application installs it — installed in a shared process
    such as pytest it would kill the run midway.
    """
    def _bring_down() -> None:
        import os
        import time
        time.sleep(grace_s)
        os._exit(0)

    threading.Thread(target=_bring_down, name="dornick-exit-guard",
                     daemon=True).start()


def _safely(fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception:
        # An error in the tray menu must not bring the program down; at
        # worst that click does nothing.
        pass
