"""Change ledger: a snapshot before every write + the `undo` tool.

Right before write_file/edit_file/copy_in change a file INSIDE the
workshop they stop here: the file's current state is copied under
`.dornick/degisiklikler/<session>/<seq>-<name>`, the record lands in
`kayit.jsonl`. The `undo` tool lists those records and applies them in
reverse.

Two deliberate decisions:

  * Undo records itself too. So a wrong `restore` can be moved forward
    again with one more `restore` (redo) — not a one-way ladder.
  * Failing to take a snapshot does NOT stop the write. For files above
    2 MB the copy is skipped and a note is put in the record; undo honestly
    says it cannot revert that record. Stopping the car because the seat
    belt would not buckle was locking the model up.

Accumulation: the session folders are filtered once per process, on first
use — folders of sessions older than 14 days are silently deleted. This
folder never enters the transfer package (state_dir is outside the
workshop; transfer._ATLA also recognises .Dornick).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

KLASOR = "degisiklikler"
GORUNTU_TAVANI = 2 * 1024 * 1024   # files larger than this get no snapshot
CLEANUP_DAYS = 14
LIST_CAP = 20

_UNSAFE = re.compile(r"[^\w.\-]+")

# Roots cleaned once per process (the practical form of "at start-up":
# when the first file write arrives, once for that root).
_temizlenen: set[Path] = set()


def defter(ctx: ToolContext) -> "Defter":
    return Defter(Path(ctx.config.state_dir) / KLASOR, ctx.session.id)


class Defter:
    """One session's change records. The real source is kayit.jsonl on
    disk — nothing is lost if the process restarts or the tool layer is
    rebuilt."""

    def __init__(self, root: Path, session: str) -> None:
        self.root = root
        self.dizin = root / (_UNSAFE.sub("_", session or "oturum") or "oturum")
        self.log_path = self.dizin / "kayit.jsonl"

    # -- recording -----------------------------------------------------

    def save(self, path: Path, tool: str) -> None:
        """Called RIGHT BEFORE the file changes; stores its current state.

        For a file that does not exist yet a "yoktu" (did not exist) record
        is written — undo deletes that file.
        """
        self._prepare()
        records = self._read_records()
        seq = (records[-1]["sira"] + 1) if records else 1
        record: dict[str, Any] = {
            "sira": seq,
            "dosya": str(path),
            "arac": tool,
            "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "goruntu": None,
            "yoktu": False,
            "atlandi": None,
        }
        try:
            if not path.exists():
                record["yoktu"] = True
            elif path.stat().st_size > GORUNTU_TAVANI:
                record["atlandi"] = "2 MB üstü, görüntü alınmadı"
            else:
                name = f"{seq:04d}-{(_UNSAFE.sub('_', path.name) or 'dosya')[:80]}"
                shutil.copy2(path, self.dizin / name)
                record["goruntu"] = name
        except OSError as exc:
            record["goruntu"] = None
            record["atlandi"] = f"görüntü alınamadı: {exc}"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -- undo ----------------------------------------------------------

    def list_entries(self, tavan: int = LIST_CAP) -> list[dict[str, Any]]:
        """The latest records, newest first."""
        return list(reversed(self._read_records()[-tavan:]))

    def undo(self, n: int) -> tuple[list[str], str | None]:
        """Applies the last n changes in reverse; returns (done, error).

        ALL of them are checked first: if there is a record without a
        snapshot (skipped), nothing is done — a half undo is worse than no
        undo.
        """
        records = self._read_records()
        if not records:
            return [], "Bu oturumda kayıtlı değişiklik yok."
        if n > len(records):
            return [], (
                f"Bu oturumda {len(records)} değişiklik var, {n} geri alınamaz. "
                "Önce `undo` ile action=list yap."
            )

        chosen = records[-n:]
        for k in chosen:
            if k["goruntu"] is None and not k["yoktu"]:
                return [], (
                    f"{k['sira']}. kayıt geri alınamaz ({k['dosya']}): "
                    f"{k['atlandi'] or 'görüntü yok'}. Hiçbir şey geri alınmadı."
                )

        done: list[str] = []
        for k in reversed(chosen):  # newest to oldest
            ok, message = self._undo_one(k)
            done.append(message)
            if not ok:
                return done, message
        return done, None

    def undo_sequence(self, sira: int) -> tuple[list[str], str | None]:
        """Reverts a single record sequence (per-file Keep/Undo).

        The Undo of one row in the turn strip lands here: other files are
        untouched. If the record is missing or has no snapshot nothing is
        written.
        """
        records = self._read_records()
        if not records:
            return [], "Bu oturumda kayıtlı değişiklik yok."
        k = next((x for x in records if int(x.get("sira") or 0) == int(sira)), None)
        if k is None:
            return [], f"{sira}. kayıt bulunamadı."
        if k["goruntu"] is None and not k["yoktu"]:
            return [], (
                f"{k['sira']}. kayıt geri alınamaz ({k['dosya']}): "
                f"{k['atlandi'] or 'görüntü yok'}."
            )
        ok, message = self._undo_one(k)
        return ([message], None if ok else message)

    def undo_file(self, dosya: str) -> tuple[list[str], str | None]:
        """Reverts the latest record for this path (diff card Undo)."""
        target = Path(dosya)
        try:
            target_key = str(target.resolve()) if target.exists() else str(target)
        except OSError:
            target_key = str(target)
        target_norm = target_key.replace("\\", "/").lower()
        records = self._read_records()
        for k in reversed(records):
            raw = str(k.get("dosya") or "")
            if not raw:
                continue
            p = Path(raw)
            try:
                key = str(p.resolve()) if p.exists() else raw
            except OSError:
                key = raw
            if key.replace("\\", "/").lower() == target_norm:
                return self.undo_sequence(int(k["sira"]))
        return [], f"Bu oturumda {dosya!r} için kayıt yok."

    def _undo_one(self, k: dict[str, Any]) -> tuple[bool, str]:
        """Applies one record; (ok, message). Calls save first, for redo."""
        target = Path(k["dosya"])
        self.save(target, "undo")
        try:
            if k["yoktu"]:
                target.unlink(missing_ok=True)
                return True, f"{k['sira']}. kayıt: {target} silindi (oluşturma geri alındı)."
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.dizin / k["goruntu"], target)
            return True, f"{k['sira']}. kayıt: {target} eski haline döndü."
        except OSError as exc:
            return False, f"{k['sira']}. kayıt geri alınamadı: {exc}"

    # -- internals -----------------------------------------------------

    def _prepare(self) -> None:
        self.dizin.mkdir(parents=True, exist_ok=True)
        if self.root not in _temizlenen:
            _temizlenen.add(self.root)
            _clean(self.root, keep=self.dizin)

    def _read_records(self) -> list[dict[str, Any]]:
        try:
            text = self.log_path.read_text(encoding="utf-8")
        except OSError:
            return []
        records = []
        for line in text.splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                continue  # a half-written line must not bring the ledger down
        return records


def _clean(root: Path, keep: Path) -> None:
    """Silently deletes session folders older than 14 days."""
    threshold = time.time() - CLEANUP_DAYS * 86400
    try:
        children = list(root.iterdir())
    except OSError:
        return
    for child in children:
        try:
            if child.is_dir() and child != keep and child.stat().st_mtime < threshold:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue


# -- tool --------------------------------------------------------------


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="undo",
        description="""
Atölyedeki dosya değişikliklerini yönetir. write_file/edit_file/copy_in her
değişiklikten önce dosyanın o anki halini otomatik saklar; bu araç o
kayıtları listeler ve geri alır.

  list     bu oturumun son değişiklikleri (sıra, dosya, araç, zaman)
  restore  son n değişikliği tersine uygular (varsayılan 1); yeni oluşturulmuş
           bir dosyanın geri alınması dosyayı siler

Geri alma da kendini kaydeder: yanlış geri aldıysan bir kez daha `restore`
ile ileri dönebilirsin (redo).
        """,
        input_schema=object_schema(
            {
                "action": {"type": "string", "enum": ["list", "restore"]},
                "n": {
                    "type": "integer",
                    "description": "restore: geri alınacak değişiklik sayısı (varsayılan 1).",
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def undo(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        d = defter(ctx)
        action = str(args.get("action") or "")

        if action == "list":
            records = await asyncio.to_thread(d.list_entries)
            if not records:
                return ToolResult(content="Bu oturumda kayıtlı değişiklik yok.")
            lines = [f"Son {len(records)} değişiklik (en yenisi önce):", ""]
            for k in records:
                trace = f"{k['sira']:>4}. {k['dosya']} — {k['arac']} ({k['zaman']})"
                if k["yoktu"]:
                    trace += " [dosya yoktu, yeni oluşturuldu]"
                elif k["atlandi"]:
                    trace += f" [{k['atlandi']}]"
                lines.append(trace)
            return ToolResult(content="\n".join(lines), detail={"count": len(records)})

        if action == "restore":
            n = max(1, int(args.get("n") or 1))
            done, error = await asyncio.to_thread(d.undo, n)
            if error:
                body = "\n".join(done + [error])
                return ToolResult.error(body)
            return ToolResult(
                content="\n".join(done),
                detail={"restored": len(done)},
            )

        return ToolResult.error(
            f"Bilinmeyen action: {action!r}. 'list' ya da 'restore' kullan."
        )
