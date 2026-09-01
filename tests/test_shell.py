"""Kabuk aracı: arka plan (sunucu) ve kesme (durdur).

İki gerçek dünya hatası: (1) dornick bir sunucuyu (`python app.py`) normal kipte
çalıştırınca komut hiç bitmediği için tur takılıp kalıyordu — `background`
bunu detached başlatıp hemen dönüyor. (2) Uzun bir komutta "durdur" işe
yaramıyordu — kabuk `communicate()`'i beklerken kesmeyi görmüyordu; artık
`ctx.cancel` ile yarışıyor ve süreci öldürüyor.

Windows'ta PowerShell `Start-Sleep` kullanılıyor (quoting-güvenli, uzun sürer).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from dornick import apps
from dornick.config import Config
from dornick.events import EventLog
from dornick.permissions import PermissionEngine
from dornick.session import PendingToolUse, Session
from dornick.tools import ToolContext, ToolRegistry, execute
from dornick.tools.shell import register

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell Start-Sleep")

LONG = "Start-Sleep -Seconds 30"


def _ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
        cancel=asyncio.Event(),
    )


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register(reg)
    return reg


async def _approve(spec, args) -> bool:
    return True


def _run(calls, reg, ctx):
    return asyncio.run(execute(
        calls, registry=reg,
        permissions=PermissionEngine("yolo", allow=["*"], deny=[]),
        ctx=ctx, approve=_approve,
    ))


def test_background_returns_immediately_and_is_tracked(tmp_path: Path) -> None:
    reg, ctx = _registry(), _ctx(tmp_path)
    before = len(apps._PROCS)
    calls = [PendingToolUse("1", "shell", {"command": LONG, "background": True})]

    blocks = _run(calls, reg, ctx)

    assert blocks[0]["is_error"] is False
    assert "Arka planda" in blocks[0]["content"]
    assert len(apps._PROCS) == before + 1
    # Temizle: başlattığımız süreci bitir.
    for pid in list(apps._PROCS)[before:]:
        try:
            apps._PROCS[pid]["proc"].terminate()
        except Exception:
            pass
        apps._PROCS.pop(pid, None)


def test_stop_kills_a_running_command(tmp_path: Path) -> None:
    reg, ctx = _registry(), _ctx(tmp_path)
    calls = [PendingToolUse("1", "shell", {"command": LONG})]

    async def go():
        async def stopper():
            await asyncio.sleep(0.4)
            ctx.cancel.set()

        task = asyncio.ensure_future(stopper())
        blocks = await execute(
            calls, registry=reg,
            permissions=PermissionEngine("yolo", allow=["*"], deny=[]),
            ctx=ctx, approve=_approve,
        )
        task.cancel()
        return blocks

    blocks = asyncio.run(go())
    assert blocks[0]["is_error"] is True
    assert "Durduruldu" in blocks[0]["content"]
