"""Tepsi ve kapanış davranışı.

X pencereyi GİZLER (uygulama tepside yaşar), tepsiden Çıkış ise ajan
meşgulken önce sorar — süren iş sessizce ölmesin. Buradaki testler görsel
tepsiyi (pystray) değil, karar mantığını sınıyor: pencere yokken de aynı
kararlar aynı sonucu vermeli.
"""

from __future__ import annotations

from dornick import tray


# -- X davranışı: gizle mi kapat mı --------------------------------------


def test_close_hides_when_the_tray_is_alive() -> None:
    """Tepsi yaşıyorsa X = gizle: iş, duyular ve zamanlanmış görevler sürer."""
    assert tray.close_decision(tepsi_acik=True) == "gizle"


def test_close_really_closes_without_a_tray() -> None:
    """Tepsi yoksa gizlemek programı kapanmaz hale getirirdi: X = kapat."""
    assert tray.close_decision(tepsi_acik=False) == "kapat"


# -- Çıkış bekçisi: meşgulken onay ---------------------------------------


def test_quit_asks_nothing_when_idle() -> None:
    """Boştayken Çıkış sorgusuzdur — onay fonksiyonu HİÇ çağrılmaz."""
    asked: list[str] = []

    def confirm(q: str) -> bool:
        asked.append(q)
        return False

    assert tray.exit_decision(mesgul=False, onayla=confirm) is True
    assert asked == []


def test_quit_while_busy_asks_and_respects_no() -> None:
    """Meşgulken soru sorulur; Hayır dersen çıkılmaz, iş sürer."""
    asked: list[str] = []

    def hayir(q: str) -> bool:
        asked.append(q)
        return False

    assert tray.exit_decision(mesgul=True, onayla=hayir) is False
    assert asked == [tray.EXIT_QUESTION]
    assert "yarım kalır" in tray.EXIT_QUESTION   # kullanıcı neyi göze aldığını okur


def test_quit_while_busy_respects_yes() -> None:
    assert tray.exit_decision(mesgul=True, onayla=lambda _q: True) is True


def test_quit_never_traps_the_user() -> None:
    """Onay sorulamıyorsa (diyalog yok/patladı) açık Çıkış jesti kazanır:
    "çıkamıyorum" tuzağı, yarım işten daha kötü."""
    assert tray.exit_decision(mesgul=True, onayla=None) is True

    def patlar(_q: str) -> bool:
        raise RuntimeError("diyalog kurulamadı")

    assert tray.exit_decision(mesgul=True, onayla=patlar) is True


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


# -- X ile Çıkış'ın ayrımı ------------------------------------------------
#
# İkisi de pencere katmanının aynı `closing` olayına düşüyor. Ayrımı bir
# bayrak yapıyor; bayrak olmayınca Çıkış sessizce gizlemeye düşüyordu.


def _shutdown() -> tuple[tray.Shutdown, list[str]]:
    iz: list[str] = []
    k = tray.Shutdown(gizle=lambda: iz.append("gizle"),
                     yok_et=lambda: iz.append("yok et"))
    return k, iz


def test_x_hides_and_cancels_the_close() -> None:
    k, iz = _shutdown()
    assert k.kapanabilir_mi() is False, "X kapanışı İPTAL etmeli"
    assert iz == ["gizle"]


def test_quit_from_the_tray_actually_closes() -> None:
    """Canlıda kırılan tam bu zincirdi: kullanıcı Evet diyor, pencere
    yok edilmeye çalışılıyor, `closing` kancası bunu bir X sanıp iptal
    ediyor ve program kapanmıyordu."""
    k, iz = _shutdown()
    k.cik()
    assert iz == ["yok et"], "Çıkış gizlemeye DÜŞMEMELİ"
    assert k.kapanabilir_mi() is True, "kapanış artık iptal edilmemeli"
    assert iz == ["yok et"], "izin verirken bir daha gizlenmemeli"


def test_the_flag_only_lifts_for_a_real_quit() -> None:
    """Bayrak kendiliğinden kalkmıyor: birkaç X üst üste hep gizler."""
    k, iz = _shutdown()
    for _ in range(3):
        assert k.kapanabilir_mi() is False
    assert iz == ["gizle"] * 3
    assert k.cikiliyor is False
    k.cik()
    assert k.cikiliyor is True


# -- Görev bitiş bildirimi / tepsi Görevler -------------------------------


def test_gorev_bildirim_ok_and_fail() -> None:
    assert tray.task_notification_text("Rapor", ok=True) == "Görev tamamlandı: Rapor"
    assert tray.task_notification_text("Rapor", ok=False) == "Görev hata verdi: Rapor"


def test_gorev_bildirim_trims_long_title() -> None:
    uzun = "x" * 100
    metin = tray.task_notification_text(uzun, ok=True)
    assert metin.startswith("Görev tamamlandı: ")
    assert metin.endswith("…")
    assert len(metin) < 120


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


def test_arka_plan_notu_mentions_tasks() -> None:
    assert "görev" in tray.BACKGROUND_NOTE.lower() or "otomasyon" in tray.BACKGROUND_NOTE.lower()


def test_toast_xml_embeds_logo_and_escapes() -> None:
    xml = tray.toast_xml("dornick", 'bit <&> "ok"', "file:///C:/dornick.png")
    assert "appLogoOverride" in xml
    assert "file:///C:/dornick.png" in xml
    assert "&lt;" in xml and "&amp;" in xml and "&quot;" in xml
    assert "<bit" not in xml


def test_installer_asks_keep_or_wipe_data() -> None:
    """Kurulumda eski veri (görevler dahil) koru / sıfırla seçenekleri durur."""
    from pathlib import Path
    iss = Path(__file__).resolve().parents[1] / "installer" / "dornick.iss"
    text = iss.read_text(encoding="utf-8-sig")
    assert "görevler" in text.lower() or "tasks" in text.lower()
    assert "SecVeri" in text and "SecGuncelle" in text
    assert "OnayAnladim" in text
