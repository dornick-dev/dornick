"""Tray and shutdown behaviour.

X HIDES the window (the app lives in the tray), while Exit from the tray
asks first when the agent is busy — the running job must not die silently.
The tests here exercise the decision logic, not the visual tray (pystray):
the same decisions must give the same result even without a window.
"""

from __future__ import annotations

from dornick import tray


# -- X behaviour: hide or close ------------------------------------------


def test_close_hides_when_the_tray_is_alive() -> None:
    """If the tray is alive, X = hide: work, senses and scheduled tasks go on."""
    assert tray.close_decision(tray_alive=True) == "gizle"


def test_close_really_closes_without_a_tray() -> None:
    """Without a tray, hiding would make the program impossible to close: X = close."""
    assert tray.close_decision(tray_alive=False) == "kapat"


# -- Exit guard: confirmation while busy ---------------------------------


def test_quit_asks_nothing_when_idle() -> None:
    """When idle, Exit asks nothing — the confirm function is NEVER called."""
    asked: list[str] = []

    def confirm(q: str) -> bool:
        asked.append(q)
        return False

    assert tray.exit_decision(busy=False, confirm=confirm) is True
    assert asked == []


def test_quit_while_busy_asks_and_respects_no() -> None:
    """While busy the question is asked; say No and it doesn't quit, the work goes on."""
    asked: list[str] = []

    def say_no(q: str) -> bool:
        asked.append(q)
        return False

    assert tray.exit_decision(busy=True, confirm=say_no) is False
    assert asked == [tray.EXIT_QUESTION]
    assert "yarım kalır" in tray.EXIT_QUESTION   # the user reads what they are risking


def test_quit_while_busy_respects_yes() -> None:
    assert tray.exit_decision(busy=True, confirm=lambda _q: True) is True


def test_quit_never_traps_the_user() -> None:
    """If confirmation can't be asked (no dialog / it blew up) the explicit
    Exit gesture wins: the "I can't quit" trap is worse than unfinished work."""
    assert tray.exit_decision(busy=True, confirm=None) is True

    def blows_up(_q: str) -> bool:
        raise RuntimeError("dialog could not be built")

    assert tray.exit_decision(busy=True, confirm=blows_up) is True


# -- Tray._quit: the guard is really wired to the menu -------------------


def test_tray_quit_is_gated_by_the_busy_confirm() -> None:
    """Exit in the menu goes through the decision function: busy + No → quit
    is not called; busy + Yes → it is called."""
    calls: list[str] = []
    box = {"busy": True, "answer": False}

    t = tray.Tray(
        show=lambda: calls.append("show"),
        hide=lambda: calls.append("hide"),
        quit=lambda: calls.append("quit"),
        busy=lambda: box["busy"],
        confirm=lambda _q: box["answer"],
    )

    t._quit()
    assert calls == [], "No was said: must not quit"

    box["answer"] = True
    t._quit()
    assert calls == ["quit"]


def test_tray_quit_survives_a_broken_busy_probe() -> None:
    """If the `busy` probe blows up it counts as not busy — the exit is not locked."""
    calls: list[str] = []

    def broken() -> bool:
        raise RuntimeError("the bridge died")

    t = tray.Tray(
        show=lambda: None, hide=lambda: None,
        quit=lambda: calls.append("quit"),
        busy=broken,
        confirm=lambda _q: False,   # would have said No if asked
    )
    t._quit()
    assert calls == ["quit"]


def test_tray_without_guards_keeps_the_old_behaviour() -> None:
    """A tray built without busy/confirm (old callers) quits without asking."""
    calls: list[str] = []
    t = tray.Tray(show=lambda: None, hide=lambda: None,
                  quit=lambda: calls.append("quit"))
    t._quit()
    assert calls == ["quit"]


# -- Telling X apart from Exit -------------------------------------------
#
# Both land on the same `closing` event of the window layer. A flag makes
# the distinction; without the flag Exit silently fell through to hiding.


def _shutdown() -> tuple[tray.Shutdown, list[str]]:
    trace: list[str] = []
    k = tray.Shutdown(hide=lambda: trace.append("gizle"),
                      destroy=lambda: trace.append("yok et"))
    return k, trace


def test_x_hides_and_cancels_the_close() -> None:
    k, trace = _shutdown()
    assert k.may_close() is False, "X must CANCEL the close"
    assert trace == ["gizle"]


def test_quit_from_the_tray_actually_closes() -> None:
    """Exactly this chain broke live: the user says Yes, the window is about
    to be destroyed, the `closing` hook takes it for an X and cancels, and
    the program never closed."""
    k, trace = _shutdown()
    k.quit()
    assert trace == ["yok et"], "Exit must NOT fall through to hiding"
    assert k.may_close() is True, "the close must no longer be cancelled"
    assert trace == ["yok et"], "must not hide again while allowing"


def test_the_flag_only_lifts_for_a_real_quit() -> None:
    """The flag does not lift by itself: several X presses in a row always hide."""
    k, trace = _shutdown()
    for _ in range(3):
        assert k.may_close() is False
    assert trace == ["gizle"] * 3
    assert k.quitting is False
    k.quit()
    assert k.quitting is True


# -- Task-finished notification / tray Tasks -----------------------------


def test_task_notification_ok_and_fail() -> None:
    assert tray.task_notification_text("Rapor", ok=True) == "Görev tamamlandı: Rapor"
    assert tray.task_notification_text("Rapor", ok=False) == "Görev hata verdi: Rapor"


def test_task_notification_trims_long_title() -> None:
    long_title = "x" * 100
    text = tray.task_notification_text(long_title, ok=True)
    assert text.startswith("Görev tamamlandı: ")
    assert text.endswith("…")
    assert len(text) < 120


def test_tray_jobs_menu_calls_jobs_or_falls_back_to_show() -> None:
    calls: list[str] = []
    t = tray.Tray(
        show=lambda: calls.append("show"),
        hide=lambda: None,
        quit=lambda: None,
        jobs=lambda: calls.append("jobs"),
    )
    t._jobs()
    assert calls == ["jobs"]

    calls.clear()
    t2 = tray.Tray(show=lambda: calls.append("show"),
                   hide=lambda: None, quit=lambda: None)
    t2._jobs()
    assert calls == ["show"]


def test_background_note_mentions_tasks() -> None:
    assert "görev" in tray.BACKGROUND_NOTE.lower() or "otomasyon" in tray.BACKGROUND_NOTE.lower()


def test_toast_xml_embeds_logo_and_escapes() -> None:
    xml = tray.toast_xml("dornick", 'bit <&> "ok"', "file:///C:/dornick.png")
    assert "appLogoOverride" in xml
    assert "file:///C:/dornick.png" in xml
    assert "&lt;" in xml and "&amp;" in xml and "&quot;" in xml
    assert "<bit" not in xml


def test_installer_asks_keep_or_wipe_data() -> None:
    """The installer keeps the keep / wipe options for old data (tasks included)."""
    from pathlib import Path
    iss = Path(__file__).resolve().parents[1] / "installer" / "dornick.iss"
    text = iss.read_text(encoding="utf-8-sig")
    assert "görevler" in text.lower() or "tasks" in text.lower()
    assert "SecVeri" in text and "SecGuncelle" in text
    assert "OnayAnladim" in text
