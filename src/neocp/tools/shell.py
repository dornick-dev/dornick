"""Kabuk aracı.

Genel amaçlı bir ajan için kabuk en geniş kaldıraçtır — ama harness'a sadece
opak bir komut dizesi verir. Kapıya, işleme, denetime konu olması gereken
eylemler (dosya yazma, tarayıcı, bilgisayar kullanımı) ayrı araçlara
terfi ettirilmelidir; kabuk artakalan için.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema
from .. import ortam

MAX_OUTPUT_CHARS = 30_000
DEFAULT_TIMEOUT_S = 120

# Arka plana alınan (arka_plan: true) işin varsayılan sigortası. Uzun ama
# BİTEN işler için: derleme, kurulum, test koşusu, indirme. 2 saat cömert;
# model isterse `timeout` ile değiştirir.
JOB_TIMEOUT_S = 7200

# Hiç bitmeyen sunucu-tipi komutların imzaları. Bunları önplanda beklemek turu
# sonsuza dek dondurur — kullanıcının "takıldı kaldı" dediği durum. Model
# `background:true` demeyi atlasa bile shell bunları KENDİSİ tanıyıp arka plana
# alır; böylece tur asla donmaz, durdurulacak bir şey kalmaz, kuyruk akar.
_SERVER_SIGNS = (
    "flask run", "flask --app", "uvicorn", "gunicorn", "hypercorn", "waitress",
    "runserver", "http.server", "npm start", "npm run dev", "npm run serve",
    "yarn dev", "yarn start", "pnpm dev", "pnpm start", "vite", "next dev",
    "nuxt dev", "nodemon", "node server", "node ./server", "serve -", "php -s",
    "rails server", "rails s", "dotnet run", "streamlit run", "manage.py runserver",
    "webpack serve", "ng serve", "http-server", "live-server", "watch",
)


def _looks_like_server(command: str) -> bool:
    """Komut hiç bitmeyecek bir sunucu/izleyici mi? (sezgisel, temkinli)

    İki sinyal: (1) bilinen sunucu araçları/altkomutları, (2) bir ağ arayüzüne
    bağlanma bayrakları (`--host`/`--port`/`-p 5000`/`:5000`). `pip install`,
    `git`, derleme gibi uzun-ama-biten komutlar bu listeye girmez — onların
    çıktısı önplanda gerekli.
    """
    import re

    low = " " + command.lower().strip() + " "
    if any(sign in low for sign in _SERVER_SIGNS):
        return True
    # Ağ arayüzüne bağlanma bayrakları güçlü bir sunucu işareti (modbus web
    # client `app.py --host 0.0.0.0 --port 5000` gibi).
    if re.search(r"(^|\s)--(host|port|serve|bind)(\s|=)", low):
        return True
    if re.search(r"(^|\s)-p\s+\d{2,5}(\s|$)", low):
        return True
    return False


def _shell_command(command: str) -> list[str]:
    """Platforma uygun kabuk çağrısını kurar."""
    if sys.platform == "win32":
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        return [exe, "-NoProfile", "-NonInteractive", "-Command", command]
    exe = shutil.which("bash") or "/bin/sh"
    return [exe, "-lc", command]


async def _run_shell(
    command: str, cwd: Path, session_id: str, timeout: float, cancel: asyncio.Event
) -> tuple[str, str, int]:
    """Komutu koşturur: (durum, çıktı, kod). durum: ok | stop | timeout.

    Komut KESME olayıyla yarıştırılıyor: kullanıcı "durdur" dediğinde
    (cancel) çalışan komut anında öldürülüyor. Senkron yol ctx.cancel ile,
    arka plan işi kendi defter bayrağıyla çağırıyor — mekanizma tek.
    """
    proc = await asyncio.create_subprocess_exec(
        *_shell_command(command),
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "NEOCP_SESSION": session_id},
        **ortam.sessiz_bayraklar(),
    )

    comm = asyncio.ensure_future(proc.communicate())
    stop = asyncio.ensure_future(cancel.wait())
    try:
        done, _pending = await asyncio.wait(
            {comm, stop}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        comm.cancel()
        stop.cancel()
        raise

    if stop in done:
        proc.kill()
        await proc.wait()
        comm.cancel()
        return ("stop", "", -1)

    stop.cancel()
    if comm not in done:
        proc.kill()
        await proc.wait()
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

Ne zaman kullan: dosya sistemi keşfi, süreç yönetimi, git, paket yöneticileri,
sistem sorguları — özel bir aracın kapsamadığı her şey.

Ne zaman kullanma: dosya okuma/yazma için read_file ve write_file araçları
daha güvenli ve daha ucuz. Onlar varken kabuktan cat/echo yapma.

Komut kendi kabuğunda çalışır: değişkenler, cd, fonksiyonlar turlar arasında
korunmaz. Dizin değiştirmen gerekiyorsa `cwd` argümanını kullan.

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

        # neo KENDİNİ başlatmasın. Model kafası karıştığında ("uygulamayı
        # ayağa kaldırayım") `neocp --web 8873` çalıştırıp neo'nun ikinci bir
        # kopyasını açıyordu; kullanıcı panelde kendi programının klonunu
        # "uygulaman" diye görüyordu. Sessiz reddetmek yerine NEDENİ ve
        # doğrusu söyleniyor — model bir sonraki hamlede kendi uygulamasını
        # kendi portunda başlatabilsin.
        from .. import apps as _apps

        if _apps.neo_sureci_mi(command):
            return ToolResult.error(
                "neo zaten çalışıyor; kendini yeniden başlatma. Bu komut "
                "neo'nun (neocp) ikinci bir kopyasını açardı — kullanıcı "
                "panelde kendi programının klonunu görür. Kullanıcının "
                "uygulamasını KENDİ klasöründe, KENDİ portunda başlat "
                "(örn. `py app.py`)."
            )

        # Varsayılan çalışma dizini atölye: ajanın ürettiği her şey oraya
        # düşsün. Kabuk dosya araçları gibi bağlanamıyor — bir komut
        # istediği yere yazabilir — o sınırı izin motoru tutuyor.
        default = ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
        cwd = Path(args.get("cwd") or default).expanduser()
        if not cwd.is_dir():
            return ToolResult.error(f"Çalışma dizini yok: {cwd}")

        # Arka plan (detached): sunucu gibi hiç bitmeyen süreçler. Beklemeden
        # başlatılıyor; apps süreç defterine yazılıyor ki Uygulamalar ›
        # Çalışıyor'dan görülüp durdurulabilsin ve canlı adresi belirsin.
        # Çıktı PIPE'a değil DOSYAYA gidiyor: dinlenmeyen boru süreci
        # kilitler, görünür konsol ise kullanıcının ekranında pencere
        # patlatır ("neo çalışırken durmadan cmd açılıyor" şikâyetinin
        # köklerinden biri buydu) — dosya ikisini de çözer ve log sonradan
        # okunabilir kalır.
        #
        # `background` açıkça verilmese bile komut sunucu-tipi görünüyorsa
        # KENDİLİĞİNDEN arka plana alıyoruz: model bayrağı unutsa da tur
        # donmasın. Auto olduğunda kullanıcıya bunu ayrıca söylüyoruz.
        auto = not args.get("background") and _looks_like_server(command)
        if args.get("background") or auto:
            import subprocess
            import time as _time

            from .. import apps, ortam

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
                    env={**os.environ, "NEOCP_SESSION": ctx.session.id},
                    stdout=log, stderr=subprocess.STDOUT,
                    **ortam.sessiz_bayraklar(),
                )
            except Exception as exc:
                return ToolResult.error(f"Arka planda başlatılamadı: {type(exc).__name__}: {exc}")
            finally:
                if log is not subprocess.DEVNULL:
                    log.close()  # Popen kendi tanıtıcısını miras aldı
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

        # Uzun ama BİTEN iş: arka plan defterine. Araç hemen döner, iş
        # bitince çıktısı harness notuyla ajana bildirilir (yardımcıların
        # bildirim altyapısının aynısı). Sunucu-tipi komut buraya girmez —
        # o hiç bitmez, yukarıdaki detached yol onun için.
        if args.get("arka_plan") and ctx.job_bg is not None:
            session_id = ctx.session.id
            job_timeout = float(args.get("timeout") or JOB_TIMEOUT_S)

            async def runner(cancel: asyncio.Event) -> str:
                durum, text, code = await _run_shell(
                    command, cwd, session_id, job_timeout, cancel)
                if durum == "stop":
                    return "(kesildi — süreç sonlandırıldı)"
                if durum == "timeout":
                    return f"(zaman aşımı: {job_timeout:.0f} sn — süreç sonlandırıldı)"
                if code != 0:
                    return f"Çıkış kodu {code}\n\n{text or '(çıktı yok)'}"
                return text or "(çıktı yok, komut başarılı)"

            handle = ctx.job_bg(f"$ {command[:60]}", runner)
            return ToolResult(
                f"Arka plan işi başlatıldı · id={handle.id} — beklemeden işine "
                "devam et; komut bitince çıktısı sana bildirilecek. Durumunu "
                "`task_status` ile görebilirsin."
            )

        timeout = int(args.get("timeout") or DEFAULT_TIMEOUT_S)

        durum, text, code = await _run_shell(
            command, cwd, ctx.session.id, timeout, ctx.cancel)

        if durum == "stop":
            # Kullanıcı durdurdu.
            return ToolResult.error("Durduruldu — çalışan komut sonlandırıldı.")

        if durum == "timeout":
            return ToolResult.error(
                f"Komut {timeout} saniyede bitmedi ve durduruldu. "
                "Uzun ama biten bir işse (derleme, kurulum) `arka_plan: true` "
                "ile arkada koştur ya da `timeout` değerini artır; sunucu gibi "
                "hiç bitmeyecek bir şeyse `background: true` kullan."
            )

        if code != 0:
            return ToolResult(
                content=f"Çıkış kodu {code}\n\n{text or '(çıktı yok)'}",
                is_error=True,
                detail={"exit_code": code, "cwd": str(cwd)},
            )

        return ToolResult(
            content=text or "(çıktı yok, komut başarılı)",
            detail={"exit_code": 0, "cwd": str(cwd)},
        )
