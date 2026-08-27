"""Tepsi ve kapanış davranışı.

X pencereyi GİZLER (uygulama tepside yaşar), tepsiden Çıkış ise ajan
meşgulken önce sorar — süren iş sessizce ölmesin. Buradaki testler görsel
tepsiyi (pystray) değil, karar mantığını sınıyor: pencere yokken de aynı
kararlar aynı sonucu vermeli.
"""

from __future__ import annotations

from neocp import tray


# -- X davranışı: gizle mi kapat mı --------------------------------------


def test_close_hides_when_the_tray_is_alive() -> None:
    """Tepsi yaşıyorsa X = gizle: iş, duyular ve zamanlanmış görevler sürer."""
    assert tray.kapatma_karari(tepsi_acik=True) == "gizle"


def test_close_really_closes_without_a_tray() -> None:
    """Tepsi yoksa gizlemek programı kapanmaz hale getirirdi: X = kapat."""
    assert tray.kapatma_karari(tepsi_acik=False) == "kapat"


# -- Çıkış bekçisi: meşgulken onay ---------------------------------------


def test_quit_asks_nothing_when_idle() -> None:
    """Boştayken Çıkış sorgusuzdur — onay fonksiyonu HİÇ çağrılmaz."""
    asked: list[str] = []

    def confirm(q: str) -> bool:
        asked.append(q)
        return False

    assert tray.cikis_karari(mesgul=False, onayla=confirm) is True
    assert asked == []


def test_quit_while_busy_asks_and_respects_no() -> None:
    """Meşgulken soru sorulur; Hayır dersen çıkılmaz, iş sürer."""
    asked: list[str] = []

    def hayir(q: str) -> bool:
        asked.append(q)
        return False

    assert tray.cikis_karari(mesgul=True, onayla=hayir) is False
    assert asked == [tray.CIKIS_SORUSU]
    assert "yarım kalır" in tray.CIKIS_SORUSU   # kullanıcı neyi göze aldığını okur


def test_quit_while_busy_respects_yes() -> None:
    assert tray.cikis_karari(mesgul=True, onayla=lambda _q: True) is True


def test_quit_never_traps_the_user() -> None:
    """Onay sorulamıyorsa (diyalog yok/patladı) açık Çıkış jesti kazanır:
    "çıkamıyorum" tuzağı, yarım işten daha kötü."""
    assert tray.cikis_karari(mesgul=True, onayla=None) is True

    def patlar(_q: str) -> bool:
        raise RuntimeError("diyalog kurulamadı")

    assert tray.cikis_karari(mesgul=True, onayla=patlar) is True


# -- Tray._quit: bekçi menüye gerçekten bağlı ----------------------------


def test_tray_quit_is_gated_by_the_busy_confirm() -> None:
    """Menüdeki Çıkış, karar fonksiyonundan geçer: meşgul + Hayır → quit
    çağrılmaz; meşgul + Evet → çağrılır."""
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
    assert calls == [], "Hayır dendi: çıkılmamalı"

    box["answer"] = True
    t._quit()
    assert calls == ["quit"]


def test_tray_quit_survives_a_broken_busy_probe() -> None:
    """`busy` sorgusu patlarsa meşgul değil sayılır — çıkış kilitlenmez."""
    calls: list[str] = []

    def bozuk() -> bool:
        raise RuntimeError("köprü öldü")

    t = tray.Tray(
        show=lambda: None, hide=lambda: None,
        quit=lambda: calls.append("quit"),
        busy=bozuk,
        confirm=lambda _q: False,   # sorulsaydı Hayır derdi
    )
    t._quit()
    assert calls == ["quit"]


def test_tray_without_guards_keeps_the_old_behaviour() -> None:
    """busy/confirm verilmeden kurulan tepsi (eski çağıranlar) sorgusuz çıkar."""
    calls: list[str] = []
    t = tray.Tray(show=lambda: None, hide=lambda: None,
                  quit=lambda: calls.append("quit"))
    t._quit()
    assert calls == ["quit"]
