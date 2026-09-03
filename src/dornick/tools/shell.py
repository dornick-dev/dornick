"""Shell tool.

For a general-purpose agent the shell is the widest lever — but it hands
the harness only an opaque command string. Actions that should be subject
to gating, processing and inspection (file writes, browser, computer use)
must be promoted to separate tools; the shell is for what is left over.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .base import JobFailed, ToolContext, ToolRegistry, ToolResult, object_schema
from .. import environment

MAX_OUTPUT_CHARS = 30_000
DEFAULT_TIMEOUT_S = 120

# Default fuse of a job moved to the background (arka_plan: true). For long
# but FINITE jobs: build, install, test run, download. 2 hours is generous;
# the model changes it with `timeout` if it wants.
JOB_TIMEOUT_S = 7200

# Signatures of server-type commands that never end. Waiting for these in
# the foreground freezes the turn forever — the situation the user calls
# "it got stuck". Even if the model forgets to say `background:true`, the
# shell recognises these ITSELF and moves them to the background; so the
# turn never freezes, there is nothing left to stop, the queue flows.
_SERVER_SIGNS = (
    "flask run", "flask --app", "uvicorn", "gunicorn", "hypercorn", "waitress",
    "runserver", "http.server", "npm start", "npm run dev", "npm run serve",
    "yarn dev", "yarn start", "pnpm dev", "pnpm start", "vite", "next dev",
    "nuxt dev", "nodemon", "node server", "node ./server", "serve -", "php -s",
    "rails server", "rails s", "dotnet run", "streamlit run", "manage.py runserver",
    "webpack serve", "ng serve", "http-server", "live-server", "watch",
)


def _looks_like_server(command: str) -> bool:
    """Is the command a server/watcher that will never end? (heuristic, cautious)

    Two signals: (1) known server tools/subcommands, (2) flags that bind to
    a network interface (`--host`/`--port`/`-p 5000`/`:5000`). Long-but-
    finite commands like `pip install`, `git`, a build do not enter this
    list — their output is needed in the foreground.
    """
    import re

    low = " " + command.lower().strip() + " "
    if any(sign in low for sign in _SERVER_SIGNS):
        return True
    # Flags binding to a network interface are a strong server sign (like
    # the modbus web client `app.py --host 0.0.0.0 --port 5000`).
    if re.search(r"(^|\s)--(host|port|serve|bind)(\s|=)", low):
        return True
    if re.search(r"(^|\s)-p\s+\d{2,5}(\s|$)", low):
        return True
    return False


def _shell_command(command: str) -> list[str]:
    """Builds the platform-appropriate shell invocation."""
    if sys.platform == "win32":
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        return [exe, "-NoProfile", "-NonInteractive", "-Command", command]
    exe = shutil.which("bash") or "/bin/sh"
    return [exe, "-lc", command]


# Killing the process tree lives in environment.kill_tree: fully async,
# every wait bounded. The old synchronous twin here (subprocess.run with
# an untimed taskkill) could lock up the ENTIRE agent loop — the user
# presses Stop, taskkill hangs, every chat and Stop itself freeze (live
# wound, 01.09).


async def _run_shell(
    command: str, cwd: Path, session_id: str, timeout: float, cancel: asyncio.Event
) -> tuple[str, str, int]:
    """Runs the command: (status, output, code). status: ok | stop | timeout.

    The command is RACED against the interrupt event: when the user says
    "stop" (cancel) the running command is killed at once. The synchronous
    path calls with ctx.cancel, the background job with its own ledger
    flag — one mechanism.
    """
    proc = await asyncio.create_subprocess_exec(
        *_shell_command(command),
        cwd=str(cwd),
        # stdin closed: if the child inherits stdin, a program waiting on
        # `input()` (live case: a tool the agent wrote itself) hangs the
        # turn for minutes. With stdin closed input() raises EOFError at
        # once — the model sees the error and fixes it.
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "DORNICK_SESSION": session_id},
        **environment.quiet_flags(),
    )

    comm = asyncio.ensure_future(proc.communicate())
    stop = asyncio.ensure_future(cancel.wait())
    try:
        done, _pending = await asyncio.wait(
            {comm, stop}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
    except asyncio.CancelledError:
        await environment.kill_tree(proc)
        comm.cancel()
        stop.cancel()
        raise

    if stop in done:
        await environment.kill_tree(proc)
        comm.cancel()
        return ("stop", "", -1)

    stop.cancel()
    if comm not in done:
        await environment.kill_tree(proc)
        comm.cancel()
        return ("timeout", "", -1)

    output, _ = comm.result()
    text = _truncate(output.decode("utf-8", errors="replace").strip())
    return ("ok", text, proc.returncode or 0)


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    dropped = len(text) - limit
    return f"{head}\n\n... [{dropped} karakter kırpıldı] ...\n\n{tail}"


def register(registry: ToolRegistry) -> None:
    shell_name = "PowerShell" if sys.platform == "win32" else "bash"

    @registry.tool(
        name="shell",
        description=f"""
Bir {shell_name} komutu çalıştırır ve stdout+stderr döndürür.

Ne zaman kullan: dosya sistemi keşfi, süreç yönetimi, paket yöneticileri,
sistem sorguları — özel bir aracın kapsamadığı her şey.

Ne zaman kullanma: dosya okuma/yazma için read_file ve write_file araçları
daha güvenli ve daha ucuz. Onlar varken kabuktan cat/echo yapma.
git commit / push / GitHub repo için `git` aracını kullan; kabuktan
`git commit` yapma.

Komut kendi kabuğunda çalışır: değişkenler, cd, fonksiyonlar turlar arasında
korunmaz. Dizin değiştirmen gerekiyorsa `cwd` argümanını kullan.

Bilinen tuzaklar (ölçüldü — hataların çoğu bu üçünden):
- Tırnak/kaçış: $ ya da iç içe tırnak içeren komutu yazmaya çalışma;
  betiği write_file ile dosyaya yaz, dosyayı koş.
- Komut adı: emin değilsen önce sürümle doğrula (`py --version`);
  bu makinede Python `py` adıyla çağrılır.
- Yol: boşluklu yolu çift tırnağa al; göreli yol yerine `cwd` ver.

UZUN SÜREN SÜREÇLER — iki ayrı kip, karıştırma:
- Uzun ama BİTEN iş (derleme, kurulum, test koşusu, indirme): `arka_plan: true`.
  Araç hemen "başlatıldı · id" döner, sen beklemeden devam edersin; komut
  bitince ÇIKTISI sana bildirilir. Durumu `task_status` ile görürsün.
- HİÇ bitmeyen süreç (sunucu: `python app.py`, `npm start`, `flask run`):
  `background: true`. Detached başlar, çıktı takibi yok; kullanıcı onu
  Uygulamalar › Çalışıyor'dan görüp durdurabilir; canlı adres belirir.
        """,
        input_schema=object_schema(
            {
                "command": {
                    "type": "string",
                    "description": f"Çalıştırılacak {shell_name} komutu.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Çalışma dizini. Belirtilmezse çalışma alanı kullanılır.",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Saniye cinsinden zaman aşımı (varsayılan {DEFAULT_TIMEOUT_S}).",
                },
                "background": {
                    "type": "boolean",
                    "description": "HİÇ bitmeyen süreç (sunucu gibi) için: detached "
                                   "başlar, komutun bitmesini beklemez, turu bloke etmez.",
                },
                "arka_plan": {
                    "type": "boolean",
                    "description": "Uzun ama BİTEN iş (derleme, kurulum, test, "
                                   "indirme) için: komut arkada koşar, araç hemen "
                                   "döner, bitince ÇIKTISI sana bildirilir.",
                },
            },
            required=["command"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def shell(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = (args.get("command") or "").strip()
        if not command:
            return ToolResult.error("Boş komut. `command` alanını doldur.")

        # dornick must not launch ITSELF. When the model got confused ("let
        # me bring the app up") it ran `dornick --web 8873` and opened a
        # second copy of Dornick; the user saw a clone of their own program
        # in the panel labelled "your app". Instead of refusing silently
        # the REASON and the right way are stated — so the model can start
        # its own app on its own port on the next move.
        from .. import apps as _apps

        if _apps.is_dornick_process(command):
            return ToolResult.error(
                "Dornick zaten çalışıyor; kendini yeniden başlatma. Bu komut "
                "Dornick'in (dornick) ikinci bir kopyasını açardı — kullanıcı "
                "panelde kendi programının klonunu görür. Kullanıcının "
                "uygulamasını KENDİ klasöründe, KENDİ portunda başlat "
                "(örn. `py app.py`)."
            )

        # Default working directory is the workshop: everything the agent
        # produces should land there. The shell cannot be bound like the
        # file tools — a command can write wherever it wants — the
        # permission engine holds that boundary.
        default = ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
        cwd = Path(args.get("cwd") or default).expanduser()
        if not cwd.is_dir() and not cwd.is_absolute():
            # The shell copy of the workshop-prefix trap in the file tools
            # (measured, 29.08 sweep: the pattern of 3 failed calls was
            # "Çalışma dizini yok: atolye\X"): the model adds the folder
            # name from the system prompt to the path itself.
            # files._resolve fixed this silently for files; the shell cwd
            # should get the same fix.
            root = default
            parts = cwd.parts
            if parts and parts[0] == root.name:
                candidate = root / Path(*parts[1:]) if len(parts) > 1 else root
            else:
                candidate = root / cwd
            if candidate.is_dir():
                cwd = candidate
        if not cwd.is_dir():
            return ToolResult.error(f"Çalışma dizini yok: {cwd}")

        # Background (detached): processes like servers that never end.
        # Started without waiting; written to the apps process ledger so it
        # can be seen and stopped from Uygulamalar › Çalışıyor and its live
        # address appears. Output goes to a FILE, not a PIPE: an unread pipe
        # locks the process, while a visible console pops windows on the
        # user's screen (one of the roots of the "cmd keeps opening while
        # dornick runs" complaint) — a file solves both and the log stays
        # readable afterwards.
        #
        # Even when `background` is not given explicitly, if the command
        # looks server-type we move it to the background OURSELVES: the turn
        # must not freeze even if the model forgets the flag. When it is
        # auto we also tell the user so.
        auto = not args.get("background") and _looks_like_server(command)
        if args.get("background") or auto:
            import subprocess
            import time as _time

            from .. import apps, environment

            log_dir = ctx.config.state_dir / "surec-loglari"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"{int(_time.time())}-{os.getpid()}.log"
                log = open(log_path, "ab")
            except OSError:
                log, log_path = subprocess.DEVNULL, None
            try:
                bg = subprocess.Popen(
                    _shell_command(command),
                    cwd=str(cwd),
                    env={**os.environ, "DORNICK_SESSION": ctx.session.id},
                    stdout=log, stderr=subprocess.STDOUT,
                    **environment.quiet_flags(),
                )
            except Exception as exc:
                return ToolResult.error(f"Arka planda başlatılamadı: {type(exc).__name__}: {exc}")
            finally:
                if log is not subprocess.DEVNULL:
                    log.close()  # Popen inherited its own handle
            apps._PROCS[bg.pid] = {
                "proc": bg, "path": command[:80], "name": command.split()[0] if command.split() else "süreç",
                "started": _time.time(),
            }
            lead = (
                "Bu komut hiç bitmeyen bir sunucu gibi göründü, o yüzden turu "
                "dondurmamak için otomatik olarak arka plana alındı. "
                if auto else "Arka planda başlatıldı. "
            )
            return ToolResult(
                f"{lead}(PID {bg.pid}). Uzun süren süreç turu bloke etmiyor; "
                "Uygulamalar › Çalışıyor'dan görülüp durdurulabilir. Bir "
                "sunucuysa canlı adres birkaç saniyede orada belirir. Kullanıcı "
                "tarayıcıdan açmak isterse o adresi ver."
            )

        # Long but FINITE job: to the background ledger. The tool returns at
        # once, when the job finishes its output is reported to the agent
        # with a harness note (the same notification infrastructure as the
        # helpers). A server-type command does not enter here — it never
        # ends, the detached path above is for it.
        if args.get("arka_plan") and ctx.job_bg is not None:
            session_id = ctx.session.id
            job_timeout = float(args.get("timeout") or JOB_TIMEOUT_S)

            async def runner(cancel: asyncio.Event) -> str:
                status, text, code = await _run_shell(
                    command, cwd, session_id, job_timeout, cancel)
                if status == "stop":
                    raise JobFailed("İş durduruldu — komut sonlandırıldı.")
                if status == "timeout":
                    raise JobFailed(
                        f"İş zaman aşımına uğradı ({job_timeout:.0f} sn) "
                        "ve durduruldu."
                    )
                if code != 0:
                    raise JobFailed(job_report(
                        command=command, code=code, text=text or ""))
                return success_report(command=command, text=text or "")

            handle = ctx.job_bg(f"$ {command[:60]}", runner)
            return ToolResult(
                f"Arka plan işi başlatıldı · id={handle.id} — beklemeden işine "
                "devam et; komut bitince çıktısı sana bildirilecek. Durumunu "
                "`task_status` ile görebilirsin."
            )

        timeout = int(args.get("timeout") or DEFAULT_TIMEOUT_S)

        status, text, code = await _run_shell(
            command, cwd, ctx.session.id, timeout, ctx.cancel)

        if status == "stop":
            # The user stopped it.
            return ToolResult.error("Durduruldu — çalışan komut sonlandırıldı.")

        if status == "timeout":
            return ToolResult.error(
                f"Komut {timeout} saniyede bitmedi ve durduruldu. "
                "Uzun ama biten bir işse (derleme, kurulum) `arka_plan: true` "
                "ile arkada koştur ya da `timeout` değerini artır; sunucu gibi "
                "hiç bitmeyecek bir şeyse `background: true` kullan."
            )

        if code != 0:
            return ToolResult(
                content=job_report(command=command, code=code, text=text or ""),
                is_error=True,
                detail={"exit_code": code, "cwd": str(cwd)},
            )

        return ToolResult(
            content=success_report(command=command, text=text or ""),
            detail={"exit_code": 0, "cwd": str(cwd)},
        )


# -- teaching shell errors -------------------------------------------------
#
# The error text should be the next turn's recipe for the fix (OpenCode's
# edit-tool pattern). The three patterns here cover all 6 failed calls of
# the benchmark run. Pattern repetition can also be fed into the lesson
# memory (on the roadmap); first let the error itself teach.

_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("unexpected token", "missing terminator", "parsererror",
      "was unexpected at this time", "terminator in the string",
      # A bash heredoc attempt in PowerShell (py - <<EOF): a real case that
      # was left without a hint in the z1 run.
      "missing file specification after redirection"),
     "PowerShell tırnak/kaçış kırılgandır: karmaşık komutu write_file ile "
     "bir betiğe yaz ve dosyayı koş; $ içeren metinlerde tek tırnak kullan."),
    (("is not recognized as the name of a cmdlet",
      "is not recognized as an internal or external command",
      "komut olarak tanınmıyor", "command not found"),
     "Komut bu makinede bu adla yok. Önce sürüm komutuyla doğrula "
     "(ör. `py --version` / `python --version`) ve bulunan adı kullan."),
    (("cannot find path", "no such file or directory", "yol bulunamıyor",
      "sistem belirtilen yolu bulamıyor"),
     "Yol bulunamadı: boşluklu yolları çift tırnağa al ve `cwd` ile göreli "
     "değil, tam yol kullan; önce list_dir ile yolun varlığını doğrula."),
]

_MODULE_RE = re.compile(r"No module named ['\"]([^'\"]+)['\"]", re.I)
_PACKAGE_RE = re.compile(
    r"paketi yüklü değil[:\s]*\*?\*?`?([A-Za-z0-9_.-]+)",
    re.I,
)
_PIP_RE = re.compile(r"pip install ([A-Za-z0-9_.-]+)", re.I)
_ERROR_LINE = re.compile(
    r"^[A-Za-z_][\w.]*?(?:Error|Exception|Warning): .+"
)
_EXIT_RE = re.compile(r"^Çıkış kodu (\d+)\s*\n+(.*)$", re.S)


def _module_name(output: str) -> str:
    raw = output or ""
    for rx in (_MODULE_RE, _PACKAGE_RE, _PIP_RE):
        m = rx.search(raw)
        if m:
            return m.group(1).strip()
    return ""


def last_error_line(output: str) -> str:
    """The traceback's last Exception line — not the 'File …' trace."""
    for line in reversed((output or "").splitlines()):
        s = line.strip()
        if _ERROR_LINE.match(s):
            return s
    return ""


def shell_hint(output: str) -> str:
    """A one-line way out for a known error pattern (empty if none)."""
    name = _module_name(output)
    if name:
        return (
            f"Python paketi `{name}` yüklü değil. "
            f"`py -m pip install {name}` ile kur, sonra komutu yeniden koş."
        )
    lower = output.lower()
    for traces, recipe in _HINTS:
        if any(trace in lower for trace in traces):
            return recipe
    return ""


def shell_summary(output: str) -> str:
    """A sentence the user will understand, from raw shell output."""
    name = _module_name(output)
    if name:
        return (
            f"Gerekli Python paketi yüklü değil: **{name}**. "
            f"Kurmak için `py -m pip install {name}` yaz, sonra aynı komutu "
            "yeniden çalıştır."
        )
    if hint := shell_hint(output or ""):
        last = last_error_line(output)
        if last:
            return f"{last}. {hint}"
        return hint
    return last_error_line(output)


def job_report(*, command: str, code: int, text: str) -> str:
    """The user report of a failed shell job — not a wall of traceback."""
    summary = shell_summary(text)
    lines = [
        "## Sonuç",
        "",
        summary or "Komut çalışmadı.",
        "",
        f"- Komut: `{command}`",
    ]
    if not summary:
        tail = _short_tail(text)
        if tail:
            lines += ["", "## Çıktı", "", tail]
    if code and code != 1:
        lines.append(f"- Çıkış kodu: {code}")
    return "\n".join(lines)


def success_report(*, command: str, text: str) -> str:
    """The user report of a successful shell job — not a wall of raw stdout.

    In the Viewer what finished should be read first; a long log stays
    under ## Çıktı.
    """
    raw = (text or "").strip()
    empty = not raw or raw == "(çıktı yok, komut başarılı)"
    summary = "Komut başarıyla bitti."
    if not empty:
        for line in reversed(raw.splitlines()):
            s = line.strip()
            if s:
                summary = s[:220]
                break
    lines = [
        "## Sonuç",
        "",
        summary,
        "",
        f"- Komut: `{command}`",
    ]
    if not empty and (raw.count("\n") > 0 or len(raw) > len(summary) + 24):
        body = raw if len(raw) <= 12000 else "…\n" + "\n".join(raw.splitlines()[-100:])
        lines += ["", "## Çıktı", "", body]
    return "\n".join(lines)


def _short_tail(output: str) -> str:
    """Drop the traceback trace; the last few meaningful lines."""
    keep: list[str] = []
    for line in (output or "").splitlines():
        s = line.strip()
        if not s or s.startswith("Traceback") or s.startswith("File "):
            continue
        keep.append(s)
    if not keep:
        return ""
    return "\n".join(keep[-5:])[:400]


def _command_from_title(title: str) -> str:
    name = (title or "").strip()
    return name[2:].strip() if name.startswith("$ ") else name


def human_job_report(text: str, *, title: str = "") -> str:
    """Turn the old raw dump (Çıkış kodu + traceback) into a readable report.

    New jobs already write `job_report` / `success_report`; the Viewer can
    still show an old dump from memory.
    """
    raw = (text or "").strip()
    if not raw:
        return raw
    if raw.startswith("## Sonuç"):
        return raw
    command = _command_from_title(title)
    m = _EXIT_RE.match(raw)
    if m:
        return job_report(command=command, code=int(m.group(1)), text=m.group(2))
    if "Traceback (most recent call last)" in raw:
        return job_report(command=command, code=1, text=raw)
    # Success dump: structure it for background jobs titled with a command.
    if command or (title or "").strip().startswith("$ "):
        return success_report(command=command or title, text=raw)
    return raw


def short_job_summary(text: str, *, title: str = "") -> str:
    """One sentence for the tasks list — not a traceback."""
    report = human_job_report(text, title=title)
    for line in report.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("- "):
            continue
        return s
    return report[:400]
