"""Kabuk aracı.

Genel amaçlı bir ajan için kabuk en geniş kaldıraçtır — ama harness'a sadece
opak bir komut dizesi verir. Kapıya, işleme, denetime konu olması gereken
eylemler (dosya yazma, tarayıcı, bilgisayar kullanımı) ayrı araçlara
terfi ettirilmelidir; kabuk artakalan için.
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


def _agaci_oldur(proc: Any) -> None:
    """Süreci ÇOCUKLARIYLA öldürür (Windows'ta kill torunu vurmaz)."""
    if os.name == "nt":
        import subprocess as _sp
        _sp.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True)
    try:
        proc.kill()
    except ProcessLookupError:
        pass


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
        # stdin kapalı: çocuk stdin'i miras alırsa `input()` bekleyen bir
        # program (canlıda ajanın kendi yazdığı araç) turu dakikalarca
        # asıyor. Kapalı stdin'de input() anında EOFError verir — model
        # hatayı görür ve düzeltir.
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "DORNICK_SESSION": session_id},
        **ortam.sessiz_bayraklar(),
    )

    comm = asyncio.ensure_future(proc.communicate())
    stop = asyncio.ensure_future(cancel.wait())
    try:
        done, _pending = await asyncio.wait(
            {comm, stop}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
    except asyncio.CancelledError:
        _agaci_oldur(proc)
        await proc.wait()
        comm.cancel()
        stop.cancel()
        raise

    if stop in done:
        _agaci_oldur(proc)
        await proc.wait()
        comm.cancel()
        return ("stop", "", -1)

    stop.cancel()
    if comm not in done:
        _agaci_oldur(proc)
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

        # dornick KENDİNİ başlatmasın. Model kafası karıştığında ("uygulamayı
        # ayağa kaldırayım") `dornick --web 8873` çalıştırıp dornick'nun ikinci bir
        # kopyasını açıyordu; kullanıcı panelde kendi programının klonunu
        # "uygulaman" diye görüyordu. Sessiz reddetmek yerine NEDENİ ve
        # doğrusu söyleniyor — model bir sonraki hamlede kendi uygulamasını
        # kendi portunda başlatabilsin.
        from .. import apps as _apps

        if _apps.neo_sureci_mi(command):
            return ToolResult.error(
                "dornick zaten çalışıyor; kendini yeniden başlatma. Bu komut "
                "dornick'nun (dornick) ikinci bir kopyasını açardı — kullanıcı "
                "panelde kendi programının klonunu görür. Kullanıcının "
                "uygulamasını KENDİ klasöründe, KENDİ portunda başlat "
                "(örn. `py app.py`)."
            )

        # Varsayılan çalışma dizini atölye: ajanın ürettiği her şey oraya
        # düşsün. Kabuk dosya araçları gibi bağlanamıyor — bir komut
        # istediği yere yazabilir — o sınırı izin motoru tutuyor.
        default = ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
        cwd = Path(args.get("cwd") or default).expanduser()
        if not cwd.is_dir() and not cwd.is_absolute():
            # Dosya araçlarındaki atölye-önek tuzağının kabuk kopyası
            # (ölçüldü, 29.08 süpürümü: 3 hatalı çağrının kalıbı "Çalışma
            # dizini yok: atolye\X"): model sistem promptundaki klasör
            # adını yola kendisi ekliyor. files._resolve bunu dosyalarda
            # sessizce düzeltiyordu; kabuk cwd'si aynı düzeltmeyi almalı.
            kok = default
            parts = cwd.parts
            if parts and parts[0] == kok.name:
                aday = kok / Path(*parts[1:]) if len(parts) > 1 else kok
            else:
                aday = kok / cwd
            if aday.is_dir():
                cwd = aday
        if not cwd.is_dir():
            return ToolResult.error(f"Çalışma dizini yok: {cwd}")

        # Arka plan (detached): sunucu gibi hiç bitmeyen süreçler. Beklemeden
        # başlatılıyor; apps süreç defterine yazılıyor ki Uygulamalar ›
        # Çalışıyor'dan görülüp durdurulabilsin ve canlı adresi belirsin.
        # Çıktı PIPE'a değil DOSYAYA gidiyor: dinlenmeyen boru süreci
        # kilitler, görünür konsol ise kullanıcının ekranında pencere
        # patlatır ("dornick çalışırken durmadan cmd açılıyor" şikâyetinin
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
                    env={**os.environ, "DORNICK_SESSION": ctx.session.id},
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
                    raise JobFailed("İş durduruldu — komut sonlandırıldı.")
                if durum == "timeout":
                    raise JobFailed(
                        f"İş zaman aşımına uğradı ({job_timeout:.0f} sn) "
                        "ve durduruldu."
                    )
                if code != 0:
                    raise JobFailed(is_raporu(
                        command=command, code=code, text=text or ""))
                return basari_raporu(command=command, text=text or "")

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
                content=is_raporu(command=command, code=code, text=text or ""),
                is_error=True,
                detail={"exit_code": code, "cwd": str(cwd)},
            )

        return ToolResult(
            content=basari_raporu(command=command, text=text or ""),
            detail={"exit_code": 0, "cwd": str(cwd)},
        )


# -- öğretici kabuk hataları ---------------------------------------------
#
# Hata metni sonraki turun düzeltme tarifi olmalı (OpenCode'un edit aracı
# kalıbı). Buradaki üç kalıp kıyas koşusundaki 6 hatalı çağrının tamamını
# kapsıyor. Kalıp tekrarı ders hafızasına da işlenebilir (yol haritasında);
# önce hatanın kendisi öğretsin.

_IPUCLARI: list[tuple[tuple[str, ...], str]] = [
    (("unexpected token", "missing terminator", "parsererror",
      "was unexpected at this time", "terminator in the string",
      # PowerShell'de bash heredoc denemesi (py - <<EOF): z1 koşusunda
      # ipucusuz kalan gerçek vaka.
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

_MODUL_RE = re.compile(r"No module named ['\"]([^'\"]+)['\"]", re.I)
_PAKET_RE = re.compile(
    r"paketi yüklü değil[:\s]*\*?\*?`?([A-Za-z0-9_.-]+)",
    re.I,
)
_PIP_RE = re.compile(r"pip install ([A-Za-z0-9_.-]+)", re.I)
_HATA_SATIRI = re.compile(
    r"^[A-Za-z_][\w.]*?(?:Error|Exception|Warning): .+"
)
_CIKIS_RE = re.compile(r"^Çıkış kodu (\d+)\s*\n+(.*)$", re.S)


def _modul_adi(cikti: str) -> str:
    ham = cikti or ""
    for rx in (_MODUL_RE, _PAKET_RE, _PIP_RE):
        m = rx.search(ham)
        if m:
            return m.group(1).strip()
    return ""


def son_hata_satiri(cikti: str) -> str:
    """Traceback'in son Exception satırı — 'File …' izi değil."""
    for line in reversed((cikti or "").splitlines()):
        s = line.strip()
        if _HATA_SATIRI.match(s):
            return s
    return ""


def kabuk_ipucu(cikti: str) -> str:
    """Bilinen hata kalıbına tek satırlık çıkış yolu (yoksa boş)."""
    ad = _modul_adi(cikti)
    if ad:
        return (
            f"Python paketi `{ad}` yüklü değil. "
            f"`py -m pip install {ad}` ile kur, sonra komutu yeniden koş."
        )
    kucuk = cikti.lower()
    for izler, tarif in _IPUCLARI:
        if any(iz in kucuk for iz in izler):
            return tarif
    return ""


def kabuk_ozet(cikti: str) -> str:
    """Ham kabuk çıktısından kullanıcının anlayacağı cümle."""
    ad = _modul_adi(cikti)
    if ad:
        return (
            f"Gerekli Python paketi yüklü değil: **{ad}**. "
            f"Kurmak için `py -m pip install {ad}` yaz, sonra aynı komutu "
            "yeniden çalıştır."
        )
    if ipucu := kabuk_ipucu(cikti or ""):
        son = son_hata_satiri(cikti)
        if son:
            return f"{son}. {ipucu}"
        return ipucu
    return son_hata_satiri(cikti)


def is_raporu(*, command: str, code: int, text: str) -> str:
    """Başarısız kabuk işinin kullanıcı raporu — traceback duvarı değil."""
    ozet = kabuk_ozet(text)
    satirlar = [
        "## Sonuç",
        "",
        ozet or "Komut çalışmadı.",
        "",
        f"- Komut: `{command}`",
    ]
    if not ozet:
        kuyruk = _kisa_kuyruk(text)
        if kuyruk:
            satirlar += ["", "## Çıktı", "", kuyruk]
    if code and code != 1:
        satirlar.append(f"- Çıkış kodu: {code}")
    return "\n".join(satirlar)


def basari_raporu(*, command: str, text: str) -> str:
    """Başarılı kabuk işinin kullanıcı raporu — ham stdout duvarı değil.

    Viewer'da önce ne bittiği okunsun; uzun log ## Çıktı altında kalsın.
    """
    ham = (text or "").strip()
    bos = not ham or ham == "(çıktı yok, komut başarılı)"
    ozet = "Komut başarıyla bitti."
    if not bos:
        for line in reversed(ham.splitlines()):
            s = line.strip()
            if s:
                ozet = s[:220]
                break
    satirlar = [
        "## Sonuç",
        "",
        ozet,
        "",
        f"- Komut: `{command}`",
    ]
    if not bos and (ham.count("\n") > 0 or len(ham) > len(ozet) + 24):
        govde = ham if len(ham) <= 12000 else "…\n" + "\n".join(ham.splitlines()[-100:])
        satirlar += ["", "## Çıktı", "", govde]
    return "\n".join(satirlar)


def _kisa_kuyruk(cikti: str) -> str:
    """Traceback izini at; son birkaç anlamlı satır."""
    keep: list[str] = []
    for line in (cikti or "").splitlines():
        s = line.strip()
        if not s or s.startswith("Traceback") or s.startswith("File "):
            continue
        keep.append(s)
    if not keep:
        return ""
    return "\n".join(keep[-5:])[:400]


def _komut_from_title(title: str) -> str:
    ad = (title or "").strip()
    return ad[2:].strip() if ad.startswith("$ ") else ad


def insan_is_raporu(metin: str, *, title: str = "") -> str:
    """Eski ham dökümü (Çıkış kodu + traceback) okunur rapora çevir.

    Yeni işler zaten `is_raporu` / `basari_raporu` yazar; Viewer hâlâ
    bellekteki eski dökümü gösterebilir.
    """
    ham = (metin or "").strip()
    if not ham:
        return ham
    if ham.startswith("## Sonuç"):
        return ham
    komut = _komut_from_title(title)
    m = _CIKIS_RE.match(ham)
    if m:
        return is_raporu(command=komut, code=int(m.group(1)), text=m.group(2))
    if "Traceback (most recent call last)" in ham:
        return is_raporu(command=komut, code=1, text=ham)
    # Başarı dökümü: komut başlıklı arka plan işlerinde yapılandır.
    if komut or (title or "").strip().startswith("$ "):
        return basari_raporu(command=komut or title, text=ham)
    return ham


def kisa_is_ozeti(metin: str, *, title: str = "") -> str:
    """Görevler listesi için tek cümle — traceback değil."""
    rapor = insan_is_raporu(metin, title=title)
    for line in rapor.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("- "):
            continue
        return s
    return rapor[:400]
