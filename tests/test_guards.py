"""Hard guards — refusals independent of the permission mode that cannot be lifted.

These tests correspond to the concrete leak/escalation chains found in the
security audit (01.09): secrets being read and sent out, writing to the
mode/gate files and pulling oneself to `yolo`, leaving startup persistence.
"""

from __future__ import annotations

from dornick import guards
from dornick.permissions import Decision, PermissionEngine


def _spec(name: str, mutates: bool = False):
    from dornick.tools.base import object_schema, ToolSpec

    async def _h(_a, _c):  # pragma: no cover - never called
        return None

    return ToolSpec(name=name, description="", input_schema=object_schema({}),
                    handler=_h, mutates=mutates)


# -- hard_deny unit -----------------------------------------------------


def test_keys_json_read_and_write_both_denied() -> None:
    """`.dornick/keys.json` is neither read nor written — a secret, injection's prize."""
    assert guards.hard_deny("read_file", False,
                            {"path": r"C:\x\.dornick\keys.json"})
    assert guards.hard_deny("write_file", True,
                            {"path": "/home/u/.dornick/keys.json"})
    # copy_in's source is caught even though it sits in a different field (all values are scanned).
    assert guards.hard_deny("copy_in", True,
                            {"source": ".dornick/keys.json", "dest": "a"})
    # Even when the name only appears inside a shell command.
    assert guards.hard_deny("shell", True,
                            {"command": "type .dornick\\keys.json"})


def test_config_and_gate_write_denied_read_allowed() -> None:
    """config/gate/manifest are closed to WRITING (mode/gate/approval), open to reading."""
    for target in ("config.json", "gate.json", "skills_onayli.json"):
        path = f".dornick/{target}"
        assert guards.hard_deny("write_file", True, {"path": path}), target
        assert guards.hard_deny("shell", True,
                                {"command": f"echo x > .dornick/{target}"}), target
        # Reading (not a mutation, not the write surface) is free.
        assert guards.hard_deny("read_file", False, {"path": path}) is None, target


def test_startup_persistence_denied() -> None:
    """The Run key and the Startup folder — shell/mutation cannot reach."""
    assert guards.hard_deny(
        "shell", True,
        {"command": r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v x /d y'})
    assert guards.hard_deny(
        "write_file", True,
        {"path": r"C:\Users\u\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\x.bat"})


def test_ordinary_paths_are_not_touched() -> None:
    """Ordinary work is not blocked — the guard is narrow. A keys.json/config.json
    name OUTSIDE `.dornick` is a user file and is free."""
    assert guards.hard_deny("write_file", True, {"path": "atolye/site/index.html"}) is None
    assert guards.hard_deny("shell", True, {"command": "npm test"}) is None
    # A config.json in the user's own project (not .dornick) can be written.
    assert guards.hard_deny("write_file", True, {"path": "proje/config.json"}) is None
    assert guards.hard_deny("read_file", False, {"path": "proje/keys.json"}) is None


# -- integration with the permission engine: even yolo cannot pass ------


def test_yolo_cannot_bypass_hard_deny() -> None:
    """Even the loosest mode cannot open a hard guard — the gate comes BEFORE yolo."""
    engine = PermissionEngine("yolo", allow=["*"], deny=[])
    decision, rule = engine.evaluate(_spec("read_file"),
                                     {"path": ".dornick/keys.json"})
    assert decision is Decision.DENY
    assert rule.startswith("sabit:koruma:")
    # The reason travels in human language (the executor shows it to the model).
    assert "keys.json" in rule


def test_allow_rule_cannot_bypass_hard_deny() -> None:
    """An explicit allow rule cannot get past a hard guard either."""
    engine = PermissionEngine("ask", allow=["write_file:*"], deny=[])
    decision, _rule = engine.evaluate(_spec("write_file", mutates=True),
                                      {"path": ".dornick/config.json"})
    assert decision is Decision.DENY


def test_normal_call_still_flows_through_the_gate() -> None:
    """The guard does not affect an ordinary call: a normal write in yolo is ALLOW."""
    engine = PermissionEngine("yolo", allow=[], deny=[])
    decision, _rule = engine.evaluate(_spec("write_file", mutates=True),
                                      {"path": "atolye/rapor.md"})
    assert decision is Decision.ALLOW
