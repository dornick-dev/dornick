"""Change ledger: a snapshot before every write + the `undo` tool.

Right before write_file/edit_file/copy_in change a file INSIDE the
workshop they stop here: the file's current state is copied under
`.dornick/degisiklikler/<session>/<seq>-<name>`, the record lands in
`ledger.jsonl`. The `undo` tool lists those records and applies them in
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

from .. import legacy_names, legacy_values
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

FOLDER = "changes"
SNAPSHOT_CEILING = 2 * 1024 * 1024   # files larger than this get no snapshot
CLEANUP_DAYS = 14
LIST_CAP = 20

_UNSAFE = re.compile(r"[^\w.\-]+")

# Roots cleaned once per process (the practical form of "at start-up":
# when the first file write arrives, once for that root).
_cleaned: set[Path] = set()


LOG_NAME = "ledger.jsonl"
LEGACY_LOG_NAME = "kayit.jsonl"      # the pre-1.5.5 name, adopted once


def ledger(ctx: ToolContext) -> "Ledger":
    return Ledger(Path(ctx.config.state_dir) / FOLDER, ctx.session.id)


class Ledger:
    """One session's change records. The real source is ledger.jsonl on
    disk — nothing is lost if the process restarts or the tool layer is
    rebuilt. A record written before 1.5.5 (`sira`/`dosya`/`arac`/`zaman`/
    `goruntu`/`yoktu`/`atlandi`) is read as `seq`/`file`/`tool`/`time`/
    `snapshot`/`missing`/`skipped`; the file is not rewritten."""

    def __init__(self, root: Path, session: str) -> None:
        self.root = root
        self.directory = root / (_UNSAFE.sub("_", session or "session") or "session")
        self.log_path = self.directory / LOG_NAME
        legacy_names.adopt(self.directory / LEGACY_LOG_NAME, self.log_path)

    # -- recording -----------------------------------------------------

    def save(self, path: Path, tool: str) -> None:
        """Called RIGHT BEFORE the file changes; stores its current state.

        For a file that does not exist yet a "missing" (did not exist)
        record is written — undo deletes that file.
        """
        self._prepare()
        records = self._read_records()
        seq = (records[-1]["seq"] + 1) if records else 1
        record: dict[str, Any] = {
            "seq": seq,
            "file": str(path),
            "tool": tool,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "snapshot": None,
            "missing": False,
            "skipped": None,
        }
        try:
            if not path.exists():
                record["missing"] = True
            elif path.stat().st_size > SNAPSHOT_CEILING:
                record["skipped"] = "2 MB üstü, görüntü alınmadı"
            else:
                name = f"{seq:04d}-{(_UNSAFE.sub('_', path.name) or 'file')[:80]}"
                shutil.copy2(path, self.directory / name)
                record["snapshot"] = name
        except OSError as exc:
            record["snapshot"] = None
            record["skipped"] = f"görüntü alınamadı: {exc}"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -- undo ----------------------------------------------------------

    def list_entries(self, cap: int = LIST_CAP) -> list[dict[str, Any]]:
        """The latest records, newest first."""
        return list(reversed(self._read_records()[-cap:]))

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
            if k["snapshot"] is None and not k["missing"]:
                return [], (
                    f"{k['seq']}. kayıt geri alınamaz ({k['file']}): "
                    f"{k['skipped'] or 'görüntü yok'}. Hiçbir şey geri alınmadı."
                )

        done: list[str] = []
        for k in reversed(chosen):  # newest to oldest
            ok, message = self._undo_one(k)
            done.append(message)
            if not ok:
                return done, message
        return done, None

    def undo_sequence(self, seq: int) -> tuple[list[str], str | None]:
        """Reverts a single record sequence (per-file Keep/Undo).

        The Undo of one row in the turn strip lands here: other files are
        untouched. If the record is missing or has no snapshot nothing is
        written.
        """
        records = self._read_records()
        if not records:
            return [], "Bu oturumda kayıtlı değişiklik yok."
        k = next((x for x in records if int(x.get("seq") or 0) == int(seq)), None)
        if k is None:
            return [], f"{seq}. kayıt bulunamadı."
        if k["snapshot"] is None and not k["missing"]:
            return [], (
                f"{k['seq']}. kayıt geri alınamaz ({k['file']}): "
                f"{k['skipped'] or 'görüntü yok'}."
            )
        ok, message = self._undo_one(k)
        return ([message], None if ok else message)

    def undo_file(self, file_path: str) -> tuple[list[str], str | None]:
        """Reverts the latest record for this path (diff card Undo)."""
        target = Path(file_path)
        try:
            target_key = str(target.resolve()) if target.exists() else str(target)
        except OSError:
            target_key = str(target)
        target_norm = target_key.replace("\\", "/").lower()
        records = self._read_records()
        for k in reversed(records):
            raw = str(k.get("file") or "")
            if not raw:
                continue
            p = Path(raw)
            try:
                key = str(p.resolve()) if p.exists() else raw
            except OSError:
                key = raw
            if key.replace("\\", "/").lower() == target_norm:
                return self.undo_sequence(int(k["seq"]))
        return [], f"Bu oturumda {file_path!r} için kayıt yok."

    def _undo_one(self, k: dict[str, Any]) -> tuple[bool, str]:
        """Applies one record; (ok, message). Calls save first, for redo."""
        target = Path(k["file"])
        self.save(target, "undo")
        try:
            if k["missing"]:
                target.unlink(missing_ok=True)
                return True, f"{k['seq']}. kayıt: {target} silindi (oluşturma geri alındı)."
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.directory / k["snapshot"], target)
            return True, f"{k['seq']}. kayıt: {target} eski haline döndü."
        except OSError as exc:
            return False, f"{k['seq']}. kayıt geri alınamadı: {exc}"

    # -- internals -----------------------------------------------------

    def _prepare(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.root not in _cleaned:
            _cleaned.add(self.root)
            _clean(self.root, keep=self.directory)

    def _read_records(self) -> list[dict[str, Any]]:
        try:
            text = self.log_path.read_text(encoding="utf-8")
        except OSError:
            return []
        records = []
        for line in text.splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue  # a half-written line must not bring the ledger down
            if isinstance(record, dict):
                records.append(legacy_values.keys(record, legacy_values.LEDGER_KEYS))
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
        d = ledger(ctx)
        action = str(args.get("action") or "")

        if action == "list":
            records = await asyncio.to_thread(d.list_entries)
            if not records:
                return ToolResult(content="Bu oturumda kayıtlı değişiklik yok.")
            lines = [f"Son {len(records)} değişiklik (en yenisi önce):", ""]
            for k in records:
                trace = f"{k['seq']:>4}. {k['file']} — {k['tool']} ({k['time']})"
                if k["missing"]:
                    trace += " [dosya yoktu, yeni oluşturuldu]"
                elif k["skipped"]:
                    trace += f" [{k['skipped']}]"
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
