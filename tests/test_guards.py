"""Sabit korumalar — izin kipinden bağımsız aşılamaz retler.

Bu testler güvenlik denetiminde (01.09) bulunan somut sızıntı/eskalasyon
zincirlerine karşılık geliyor: sırların okunup dışarı gitmesi, kip/kapı
dosyalarına yazıp `yolo`'ya kendini çekme, açılış kalıcılığı bırakma.
"""

from __future__ import annotations

from dornick import guards
from dornick.permissions import Decision, PermissionEngine


def _spec(name: str, mutates: bool = False):
    from dornick.tools.base import object_schema, ToolSpec

    async def _h(_a, _c):  # pragma: no cover - çağrılmaz
        return None

    return ToolSpec(name=name, description="", input_schema=object_schema({}),
                    handler=_h, mutates=mutates)


# -- sabit_ret birimi ---------------------------------------------------


def test_keys_json_read_and_write_both_denied() -> None:
    """`.dornick/keys.json` ne okunur ne yazılır — sır, injection'ın malı."""
    assert guards.sabit_ret("read_file", False,
                               {"path": r"C:\x\.dornick\keys.json"})
    assert guards.sabit_ret("write_file", True,
                               {"path": "/home/u/.dornick/keys.json"})
    # copy_in kaynağı farklı alanda olsa da yakalanır (tüm değerler taranır).
    assert guards.sabit_ret("copy_in", True,
                               {"source": ".dornick/keys.json", "dest": "a"})
    # shell içinde adı geçse de.
    assert guards.sabit_ret("shell", True,
                               {"command": "type .dornick\\keys.json"})


def test_config_and_gate_write_denied_read_allowed() -> None:
    """config/gate/manifest YAZMAYA kapalı (kip/kapı/onay), okumaya açık."""
    for hedef in ("config.json", "gate.json", "skills_onayli.json"):
        yol = f".dornick/{hedef}"
        assert guards.sabit_ret("write_file", True, {"path": yol}), hedef
        assert guards.sabit_ret("shell", True,
                                   {"command": f"echo x > .dornick/{hedef}"}), hedef
        # Okuma (mutasyon değil, yazma yüzeyi değil) serbest.
        assert guards.sabit_ret("read_file", False, {"path": yol}) is None, hedef


def test_startup_persistence_denied() -> None:
    """Run anahtarı ve Başlangıç klasörü — kabuk/mutasyon uzanamaz."""
    assert guards.sabit_ret(
        "shell", True,
        {"command": r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v x /d y'})
    assert guards.sabit_ret(
        "write_file", True,
        {"path": r"C:\Users\u\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\x.bat"})


def test_ordinary_paths_are_not_touched() -> None:
    """Sıradan iş engellenmiyor — koruma dar. keys.json/config.json adı
    `.dornick` DIŞINDA bir kullanıcı dosyasıysa serbest."""
    assert guards.sabit_ret("write_file", True, {"path": "atolye/site/index.html"}) is None
    assert guards.sabit_ret("shell", True, {"command": "npm test"}) is None
    # Kullanıcının kendi projesindeki config.json (‑.dornick değil) yazılabilir.
    assert guards.sabit_ret("write_file", True, {"path": "proje/config.json"}) is None
    assert guards.sabit_ret("read_file", False, {"path": "proje/keys.json"}) is None


# -- izin motoruyla bütünleşme: yolo bile aşamaz -----------------------


def test_yolo_cannot_bypass_hard_deny() -> None:
    """En gevşek kip bile sabit korumayı açamaz — kapı yolo'dan ÖNCE."""
    engine = PermissionEngine("yolo", allow=["*"], deny=[])
    decision, rule = engine.evaluate(_spec("read_file"),
                                     {"path": ".dornick/keys.json"})
    assert decision is Decision.DENY
    assert rule.startswith("sabit:koruma:")
    # Gerekçe insan diliyle taşınıyor (executor bunu modele gösterir).
    assert "keys.json" in rule


def test_allow_rule_cannot_bypass_hard_deny() -> None:
    """Açık bir allow kuralı da sabit korumayı geçemez."""
    engine = PermissionEngine("ask", allow=["write_file:*"], deny=[])
    decision, _rule = engine.evaluate(_spec("write_file", mutates=True),
                                      {"path": ".dornick/config.json"})
    assert decision is Decision.DENY


def test_normal_call_still_flows_through_the_gate() -> None:
    """Koruma sıradan çağrıyı etkilemiyor: yolo'da normal yazma ALLOW."""
    engine = PermissionEngine("yolo", allow=[], deny=[])
    decision, _rule = engine.evaluate(_spec("write_file", mutates=True),
                                      {"path": "atolye/rapor.md"})
    assert decision is Decision.ALLOW
