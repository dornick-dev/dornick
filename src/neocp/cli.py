"""Terminal arayüzü.

Geçici bir kabuk: harness'ı sürmeye ve gözlemeye yeter. Zengin TUI ve
zihin görselleştirmesi ayrı katman olarak gelecek — döngü arayüzü bilmiyor,
sadece AgentIO'yu tanıyor.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import webbrowser
from contextlib import suppress
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .backends import build_client
from . import prompt
from .config import Config
from .context import ContextPolicy
from .loop import Agent, AgentIO
from .mind import open_mind
from .permissions import PermissionEngine
from .session import Session
from .tools import build_registry
from .tools.base import ToolSpec

console = Console()

BANNER = "neocp — çıkmak için /exit, komutlar için /help"
HELP = """
/exit            çık
/tools           kayıtlı araçları listele
/mode <ad>       izin modu: auto | ask | plan | yolo
/usage           son turun token ve önbellek raporu
/system          etkin sistem promptunu göster
/soul            diskten yüklenen kimliği göster
/mind [sorgu]    zihni incele: hedefler, bellek, geçmiş oturumlar
/note <metin>    ajana konuşma ortası operatör yönergesi gönder
/thinking        düşünme akışını göster/gizle
"""


def build_io(state: dict[str, Any], permissions: PermissionEngine) -> AgentIO:
    def on_text(chunk: str) -> None:
        console.print(chunk, end="", markup=False, highlight=False)

    def on_thinking(chunk: str) -> None:
        if state.get("show_thinking"):
            console.print(Text(chunk, style="dim italic"), end="", markup=False)

    def on_tool_start(name: str, args: dict[str, Any]) -> None:
        summary = _summarize(args)
        console.print(f"\n[cyan]→ {name}[/cyan] [dim]{summary}[/dim]")

    def on_tool_end(name: str, ok: bool, ms: int) -> None:
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {mark} [dim]{name} · {ms} ms[/dim]")

    def on_notice(text: str) -> None:
        console.print(f"\n[yellow]{text}[/yellow]")

    def on_usage(report: dict[str, int]) -> None:
        state["usage"] = report

    async def approve(spec: ToolSpec, args: dict[str, Any]) -> bool:
        console.print(
            Panel(
                _summarize(args, limit=600) or "(argümansız)",
                title=f"izin isteniyor · {spec.name}",
                border_style="yellow",
            )
        )
        answer = (await asyncio.to_thread(input, "  [e]vet / [h]ayır / [d]aima: ")).strip().lower()
        if answer.startswith("d"):
            rule = permissions.remember_allow(spec, args)
            console.print(f"  [dim]kural eklendi: {rule}[/dim]")
            return True
        return answer.startswith("e")

    return AgentIO(
        on_text=on_text,
        on_thinking=on_thinking,
        on_tool_start=on_tool_start,
        on_tool_end=on_tool_end,
        on_notice=on_notice,
        on_usage=on_usage,
        approve=approve,
    )


# Bayt sırası işareti. İkinci biçim, UTF-8 BOM'un cp125x ile çözülmüş hali —
# Windows'ta boru ile beslenen girdide böyle gelir. Temizlenmezse "/exit"
# bir komut değil, prompt olarak modele gider ve boşuna istek atılır.
_BOMS = ("﻿", "ï»¿", "​")


def _clean(line: str) -> str:
    for bom in _BOMS:
        line = line.removeprefix(bom)
    return line.strip()


def _summarize(args: dict[str, Any], limit: int = 120) -> str:
    for key in ("command", "path", "url", "query"):
        if isinstance(value := args.get(key), str):
            flat = " ".join(value.split())
            return flat if len(flat) <= limit else flat[:limit] + "…"
    flat = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return flat if len(flat) <= limit else flat[:limit] + "…"


async def repl(config: Config, resume: bool, web: int | None = None) -> int:
    config.ensure_dirs()

    session = (Session.latest(config.sessions_dir) if resume else None) or Session.create(
        config.sessions_dir
    )
    mind = open_mind(config.mind_dir, config.sessions_dir, session.id)
    # Dar pencereli modelde alt ajan aracı hiç kaydedilmiyor: şeması
    # tek başına 130 token ve 4096'lık bir pencerede o yer konuşmanın.
    registry = build_registry(mind, subagents=not prompt.is_lean(config))
    permissions = PermissionEngine.from_config(config.permissions)
    client = build_client(config.model)
    state: dict[str, Any] = {"show_thinking": False, "usage": {}, "mind": mind}

    agent = Agent(
        config=config,
        session=session,
        registry=registry,
        client=client,
        io=build_io(state, permissions),
        permissions=permissions,
        policy=ContextPolicy(config.context),
        mind=mind,
    )

    server = _start_web(mind, session, web) if web else None

    lines = [
        BANNER,
        f"[dim]oturum {session.id} · model {config.model.name} · "
        f"mod {permissions.mode} · {len(registry)} araç[/dim]",
    ]
    if server:
        lines.append(f"[dim]zihin arayüzü: [/dim][cyan]{server.url}[/cyan]")
    console.print(Panel("\n".join(lines), border_style="blue"))

    try:
        while True:
            try:
                line = _clean(await asyncio.to_thread(input, "\n› "))
            except (EOFError, KeyboardInterrupt):
                break

            if not line:
                continue

            if line.startswith("/"):
                if _command(line, config, registry, permissions, agent, state) is False:
                    break
                continue

            await _run_guarded(agent, line)

    finally:
        if server:
            server.stop()
        session.close()
        await client.close()

    console.print("\n[dim]oturum kapatıldı.[/dim]")
    return 0


def _start_web(mind: Any, session: Session, port: int) -> Any:
    """Zihin arayüzünü ayrı bir thread'de başlatır.

    Arayüz açılamazsa ajan yine de çalışmalı; bu bir gözlem yüzeyi,
    çalışma önkoşulu değil.
    """
    from .web import MindServer

    try:
        server = MindServer(mind, session.log, port=port)
        url = server.start()
    except OSError as exc:
        console.print(f"[yellow]zihin arayüzü açılamadı ({exc}); ajan devam ediyor.[/yellow]")
        return None

    with suppress(Exception):
        webbrowser.open(url)
    return server


async def _run_guarded(agent: Agent, line: str) -> None:
    """Turu koşturur; SIGINT turu keser, süreci öldürmez."""
    previous = signal.getsignal(signal.SIGINT)

    def on_sigint(*_: object) -> None:
        agent.interrupt()

    signal.signal(signal.SIGINT, on_sigint)
    try:
        stats = await agent.run(line)
    finally:
        signal.signal(signal.SIGINT, previous)

    console.print()
    if stats.tool_calls:
        console.print(
            f"[dim]{stats.turns} tur · {stats.tool_calls} araç çağrısı"
            f"{' · kesildi' if stats.interrupted else ''}[/dim]"
        )


def _command(
    line: str,
    config: Config,
    registry: Any,
    permissions: PermissionEngine,
    agent: Agent,
    state: dict[str, Any],
) -> bool | None:
    cmd, _, rest = line[1:].partition(" ")
    rest = rest.strip()

    if cmd in ("exit", "quit", "q"):
        return False

    if cmd == "help":
        console.print(HELP.strip())

    elif cmd == "tools":
        for spec in registry.all():
            flag = "[red]mutasyon[/red]" if spec.mutates else "[green]okur[/green]"
            console.print(f"  {spec.name:<14} {flag}  [dim]{spec.description.splitlines()[0]}[/dim]")

    elif cmd == "mode":
        if rest in ("auto", "ask", "plan", "yolo"):
            permissions.mode = rest
            console.print(f"[dim]izin modu: {rest}[/dim]")
        else:
            console.print(f"[yellow]geçerli modlar: auto, ask, plan, yolo (şu an: {permissions.mode})[/yellow]")

    elif cmd == "thinking":
        state["show_thinking"] = not state["show_thinking"]
        console.print(f"[dim]düşünme gösterimi: {state['show_thinking']}[/dim]")

    elif cmd == "usage":
        report = state.get("usage") or {}
        if not report:
            console.print("[dim]henüz tur yok.[/dim]")
        else:
            for key, value in report.items():
                console.print(f"  {key:<14} {value:>9,}")
            if report.get("cache_read", 0) == 0 and report.get("prompt_total", 0) > 4096:
                console.print("[yellow]  önbellek okuması sıfır — sessiz bir bozucu olabilir.[/yellow]")

    elif cmd == "system":
        console.print(Panel(agent.system_prompt, title="sistem promptu", border_style="dim"))

    elif cmd == "soul":
        if agent.soul is None:
            console.print("[dim]zihin bağlı değil.[/dim]")
        else:
            console.print(Panel(agent.soul.render(), title="ruh", border_style="magenta"))

    elif cmd == "mind":
        mind = state["mind"]
        goals = mind.goal_digest() or "aktif hedef yok"
        memories = mind.memories()
        console.print(Panel(goals, title="hedefler", border_style="dim"))
        if rest:
            for hit in mind.recall(rest, limit=6):
                console.print(f"  [{hit.item.id}] ({hit.item.kind}) {hit.item.title}")
            for hit in mind.episodes(rest, limit=4):
                console.print(f"  [dim][{hit.item.session_id}] {hit.item.turns} tur[/dim]")
        else:
            console.print(f"[dim]{len(memories)} bellek kaydı. /mind <sorgu> ile ara.[/dim]")

    elif cmd == "note":
        if rest:
            agent.session.add_system_note(rest)
            console.print("[dim]operatör yönergesi eklendi.[/dim]")

    else:
        console.print(f"[yellow]bilinmeyen komut: /{cmd}[/yellow]")

    return None


def _has_model(config: Config) -> bool:
    """Calistirmadan once model erisilebilir mi?

    Anahtar yoksa ve yerel sunucu adresi tanimli degilse istemci ancak ilk
    mesajda patlardi. Kullaniciyi bos bir pencereyle bas basa birakmak yerine
    burada durdurup ne yapmasi gerektigini soyluyoruz.
    """
    if config.model.provider == "anthropic":
        return bool(os.getenv(config.model.api_key_env or "ANTHROPIC_API_KEY"))
    return bool(config.model.base_url)


def _force_utf8() -> None:
    """Windows'ta stdout varsayılan olarak konsol kod sayfasını kullanır.

    Arayüzün tamamı Türkçe; cp857/cp1254 altında ş, ğ, ı bozulur ya da
    UnicodeEncodeError ile düşer.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(prog="neocp")
    parser.add_argument(
        "command", nargs="?", choices=["setup", "recall-mcp"], default=None,
        help=(
            "setup: modeli sec ve yapilandirmayi yaz · "
            "recall-mcp: hatirlama protokolunu MCP sunucusu olarak ac"
        ),
    )
    parser.add_argument("-C", "--workspace", default=None, help="çalışma alanı dizini")
    parser.add_argument("--resume", action="store_true", help="son oturumu sürdür")
    parser.add_argument("--mode", default=None, help="izin modu: auto|ask|plan|yolo")
    parser.add_argument(
        "--web",
        nargs="?",
        const=8765,
        type=int,
        default=None,
        metavar="PORT",
        help="zihin arayüzünü başlat ve tarayıcıda aç (varsayılan port 8765)",
    )
    parser.add_argument(
        "--app",
        action="store_true",
        help="masaüstü penceresinde aç (terminal yerine)",
    )
    args = parser.parse_args(argv)

    config = Config.load(args.workspace)
    if args.mode:
        config.permissions.mode = args.mode

    if args.command == "recall-mcp":
        # stdio protokolü: stdout'a protokol dışında tek bir bayt bile
        # yazılamaz, o yüzden konsol kurulmadan doğrudan devrediliyor.
        from .recall.mcp import main as run_mcp

        return run_mcp([str(config.mind_dir / "recall.db")])

    if args.command == "setup":
        from .setup import run as run_setup

        _force_utf8()
        return run_setup(config, console)

    # Ayar sayfasından kaydedilen anahtarlar dosyada (.neocp/keys.json)
    # duruyor; _has_model ise ortama bakıyor. Dosyadaki anahtar burada
    # ortama yüklenmezse kayıtlı bir kurulum bile "yapılandırılmamış"
    # sayılıp açılmıyordu.
    from . import settings as saved_settings

    saved_settings.export_keys(config.state_dir)

    if args.app:
        # Masaüstünde model kapısı yok: model yapılandırılmamışsa pencere
        # yine açılır ve ayar sayfası yol gösterir (bkz. desktop._boot).
        # Kurulum sihirbazından çıkan kullanıcının terminali yok — konsola
        # basılan bir uyarı onun için görünmez bir hatadır.
        from .desktop import run as run_desktop

        _force_utf8()
        return run_desktop(config, port=args.web or 8765, resume=args.resume)

    if not _has_model(config):
        _force_utf8()
        console.print(
            "\n[yellow]Model yapılandırılmamış.[/yellow] "
            "Önce [cyan]neocp setup[/cyan] çalıştır.\n"
        )
        return 1

    try:
        return asyncio.run(repl(config, resume=args.resume, web=args.web))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
