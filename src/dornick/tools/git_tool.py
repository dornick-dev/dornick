"""Git aracı — commit, push, GitHub'da repo.

Kabuktan `git commit` yok: izin, çubuk tazelemesi ve öğretici hata bu
aracın işi. Okuma (status/diff/log) onaysız; yazma kapıdan geçer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .. import git as store
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

ACTIONS = (
    "status", "diff", "log", "commit", "push", "pull",
    "init", "create_repo", "publish",
)
MUTATING = frozenset({"commit", "push", "pull", "init", "create_repo", "publish"})

DESCRIPTION = """
Git deposu: durum, fark, commit, push/pull, GitHub'da repo açma.

`git commit` / `git push` / GitHub repo için BUNU kullan; kabuğa düşme.

Eylemler:
  status       dal, uzak, kirli dosyalar, +N −M
  diff         bir dosyanın (path) veya hepsinin eski/yeni gövdesi
  log          son commit'ler
  commit       message zorunlu; paths verilirse yalnız onlar, yoksa hepsi
  push / pull  uzak depo
  init         klasörde `git init` (yoksa proje / atölye)
  create_repo  GitHub'da repo: name, private (varsayılan true)
  publish      remote yoksa create_repo + git push -u

GitHub: önce `gh` (girişliyse); yoksa GITHUB_TOKEN / GH_TOKEN.
İkisi de yoksa öğretici hata — uydurma yayın yok.
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="git",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": list(ACTIONS),
                },
                "message": {
                    "type": "string",
                    "description": "Commit mesajı — action=commit için zorunlu.",
                },
                "path": {
                    "type": "string",
                    "description": "Tek dosya farkı — action=diff.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Commit'e girecek dosyalar; boşsa hepsi.",
                },
                "name": {
                    "type": "string",
                    "description": "GitHub repo adı — create_repo / publish.",
                },
                "private": {
                    "type": "boolean",
                    "description": "GitHub repo gizli mi. Varsayılan true.",
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
        safe_actions=("status", "diff", "log"),
    )
    async def git_tool(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "").strip()
        if action not in ACTIONS:
            return ToolResult.error(
                f"Bilinmeyen eylem: {action!r}. Geçerli: {', '.join(ACTIONS)}."
            )
        try:
            # _run senkron subprocess/ağ (git push 30 sn, gh 60 sn) içeriyor;
            # doğrudan çağrılınca ajan döngüsünün tamamını kilitliyordu —
            # bütün sohbetler ve Durdur dahil (canlı yara, 01.09).
            result = await asyncio.to_thread(_run, action, args, ctx)
        except store.GitError as exc:
            return ToolResult.error(str(exc))
        if action in MUTATING:
            ctx.session.log.note("git", action=action)
        return result


def _root(ctx: ToolContext) -> Path:
    # Ajanın aracı atölyede de çalışır (kendi kurduğu projeler orada
    # doğuyor); yalnız ARAYÜZ çubuğu atölyeyi görmez (scratch_ok=False).
    found = store.repo_root(ctx.config, scratch_ok=True)
    if found is None:
        box = ctx.config.open_sandbox()
        return box.project or box.root
    return found


def _run(action: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    root = _root(ctx)
    state = ctx.config.state_dir

    if action == "status":
        if store.find_root(root) is None:
            return ToolResult(
                "Bu klasörde git deposu yok. `action=init` ile açabilirsin "
                f"({root})."
            )
        snap = store.status(root, workspace=ctx.config.workspace)
        return ToolResult(_status_text(snap), detail=snap)

    if action == "diff":
        data = store.diff(root, str(args.get("path") or "") or None)
        path = str(args.get("path") or "")
        if path:
            return ToolResult(_one_diff_text(data), detail=data)
        files = data.get("files") or []
        lines = [f"{len(files)} dosya  +{data.get('plus', 0)} −{data.get('minus', 0)}"]
        for row in files[:40]:
            lines.append(
                f"  {row.get('status', 'M')} {row['path']}"
                f"  +{row.get('plus', 0)} −{row.get('minus', 0)}"
            )
        return ToolResult("\n".join(lines), detail=data)

    if action == "log":
        rows = store.log(root)
        if not rows:
            return ToolResult("Commit yok.")
        lines = [f"{r['hash']}  {r['subject']}  ({r['when']})" for r in rows]
        return ToolResult("\n".join(lines), detail={"log": rows})

    if action == "commit":
        snap = store.commit(root, str(args.get("message") or ""),
                            paths=_paths(args))
        return ToolResult(_status_text(snap, head="Commit alındı."), detail=snap)

    if action == "push":
        snap = store.push(root)
        return ToolResult(_status_text(snap, head="Push tamam."), detail=snap)

    if action == "pull":
        snap = store.pull(root)
        return ToolResult(_status_text(snap, head="Pull tamam."), detail=snap)

    if action == "init":
        snap = store.init(root)
        return ToolResult(_status_text(snap, head=f"Git init: {snap['root']}"),
                          detail=snap)

    private = args.get("private")
    if private is None:
        private = True
    name = str(args.get("name") or "").strip()

    if action == "create_repo":
        created = store.create_repo(
            name or root.name, private=bool(private),
            source=root,
            state_dir=state,
        )
        return ToolResult(
            f"GitHub repo: {created.get('html_url') or created.get('remote') or name}"
            f"  ({created.get('via')})",
            detail=created,
        )

    # publish
    snap = store.publish(
        root, name=name, private=bool(private), state_dir=state,
    )
    return ToolResult(_status_text(snap, head="Yayınlandı."), detail=snap)


def _paths(args: dict[str, Any]) -> list[str] | None:
    raw = args.get("paths")
    if not isinstance(raw, list) or not raw:
        return None
    out = [str(p).strip() for p in raw if str(p).strip()]
    return out or None


def _status_text(snap: dict[str, Any], head: str = "") -> str:
    lines = []
    if head:
        lines.append(head)
    remote = snap.get("remote") or "(uzak yok)"
    lines.append(
        f"{snap.get('name')}  {snap.get('branch')}  {remote}"
    )
    ab = []
    if snap.get("ahead"):
        ab.append(f"↑{snap['ahead']}")
    if snap.get("behind"):
        ab.append(f"↓{snap['behind']}")
    if ab:
        lines[-1] += "  " + " ".join(ab)
    files = snap.get("files") or []
    if not files:
        lines.append("Temiz.")
        return "\n".join(lines)
    lines.append(f"{len(files)} dosya  +{snap.get('plus', 0)} −{snap.get('minus', 0)}")
    for row in files[:40]:
        lines.append(
            f"  {row.get('status', 'M')} {row['path']}"
            f"  +{row.get('plus', 0)} −{row.get('minus', 0)}"
        )
    return "\n".join(lines)


def _one_diff_text(data: dict[str, Any]) -> str:
    if data.get("binary"):
        return f"{data.get('path')}: ikili dosya — fark çizilmiyor."
    old = str(data.get("old") or "")
    new = str(data.get("new") or "")
    if old == new:
        return f"{data.get('path')}: içerik aynı."
    return (
        f"{data.get('path')}  +{data.get('plus', 0)} −{data.get('minus', 0)}\n"
        f"--- eski ({len(old.splitlines())} satır)\n"
        f"+++ yeni ({len(new.splitlines())} satır)"
    )
