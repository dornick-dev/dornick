"""MCP bağlayıcıları — dış araç sunucularının istemci tarafı.

`recall/mcp.py` bu protokolün sunucu tarafı: neo'nun belleğini dışarı açıyor.
Burası tersi — kullanıcı Claude Code / LM Studio'daki `mcpServers` biçimiyle
sunucu tanımlıyor, neo bağlanıp sunucunun araçlarını kendi defterine ekliyor.
Döngü aracın nereden geldiğini bilmiyor; `ToolSpec.source` alanı zaten bunun
için vardı.

İki taşıma:

    stdio  komut başlatılıyor, satır başına bir JSON-RPC mesajı gidip
           geliyor (recall sunucusuyla aynı biçim).
    http   adres + başlıklar. Cevap düz JSON da gelebilir SSE olarak da —
           streamable HTTP sunucuları ikisini de yapıyor, ikisi de okunuyor.

Yapılandırma `.neocp/mcp.json`, Claude Code'un biçimiyle birebir:

    {"mcpServers": {
        "hesap":  {"command": "npx", "args": ["-y", "bir-mcp"]},
        "uzak":   {"url": "https://ornek.com/mcp",
                   "headers": {"Authorization": "Bearer ${ORNEK_TOKEN}"}}
    }}

Gizli değerler bu dosyaya düz yazılmıyor: `${AD}` biçimindeki değerler
bağlanırken ortamdan genişletiliyor. Ayarlar › Anahtarlar'a girilen her
değer ortama zaten yazılıyor — token oraya, dosyaya yalnızca adı.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FILE = "mcp.json"

PROTOCOL = "2025-06-18"
CLIENT = {"name": "neocp", "version": "1.0.0"}

# urllib'in kendi imzası (`Python-urllib/3.11`) Cloudflare arkasındaki
# sunucularda 1010 "Access denied" yiyor — Notion'da yaşandı. Kendimizi
# adımızla tanıtıyoruz.
USER_AGENT = "neocp/1.0 (MCP istemcisi)"

# Bağlanma ve tek bir araç çağrısı için üst sınırlar. Bağlanma cömert:
# `npx` ilk çalıştırmada paket indirebiliyor.
CONNECT_TIMEOUT_S = 30.0
CALL_TIMEOUT_S = 120.0

DEFAULT_RAW = '{\n  "mcpServers": {}\n}\n'

# Araç adları model API'lerinin kabul ettiği alfabeyle sınırlı.
_NAME_OK = re.compile(r"^[a-zA-Z0-9_-]+$")
_UNSAFE = re.compile(r"[^a-zA-Z0-9_-]")
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConnectorError(ValueError):
    """Yapılandırma ya da bağlantı hatası — kullanıcıya gösterilecek dilde."""


class AuthRequired(ConnectorError):
    """Sunucu 401 döndü: sabit token yok, kullanıcı girişi gerekiyor."""


@dataclass(slots=True)
class Connector:
    """Tek bir MCP sunucusunun tanımı."""

    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    # "defer" (varsayılan): araçlar deftere şemalarıyla GİRMEZ; model tek
    # köprü araç üzerinden listeler/çağırır. "full": eski davranış — her
    # araç tam şemasıyla kaydedilir (küçük sunucular için mantıklı).
    #
    # Ölçüldü: Notion'un 28 şeması ~27.000 token ve her mesajla gidiyordu —
    # istemin yarısından fazlası, hiç kullanılmayan araç tarifleriydi.
    expose: str = "defer"

    @property
    def kind(self) -> str:
        return "http" if self.url else "stdio"


# -- yapılandırma -------------------------------------------------------


def parse(raw: str) -> list[Connector]:
    """`mcpServers` metnini çözer. Hatalar alan adıyla söylenir.

    Hem `{"mcpServers": {...}}` hem çıplak `{ad: tanım}` kabul ediliyor:
    kullanıcı başka bir istemciden kopyalarken dış kabuğu unutabiliyor.
    """
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"Bozuk JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConnectorError("En dışta bir nesne olmalı: {\"mcpServers\": {...}}")

    servers = data.get("mcpServers", data)
    if not isinstance(servers, dict):
        raise ConnectorError("`mcpServers` bir nesne olmalı: {\"ad\": {...}}")

    found: list[Connector] = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            raise ConnectorError(f"`{name}` bir nesne olmalı.")
        if not _NAME_OK.match(str(name)):
            raise ConnectorError(
                f"`{name}`: sunucu adı yalnızca harf, rakam, `-` ve `_` içerebilir."
            )

        command = str(spec.get("command") or "").strip()
        url = str(spec.get("url") or "").strip()
        if bool(command) == bool(url):
            raise ConnectorError(
                f"`{name}`: ya `command` (stdio) ya `url` (http) verilmeli — ikisi birden değil."
            )
        if url and not url.startswith(("http://", "https://")):
            raise ConnectorError(f"`{name}`: `url` http(s) ile başlamalı.")

        args = spec.get("args") or []
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ConnectorError(f"`{name}`: `args` bir metin listesi olmalı.")
        env = spec.get("env") or {}
        headers = spec.get("headers") or {}
        for label, mapping in (("env", env), ("headers", headers)):
            if not isinstance(mapping, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
            ):
                raise ConnectorError(f"`{name}`: `{label}` metinden metine bir nesne olmalı.")

        expose = str(spec.get("expose") or "defer")
        if expose not in ("defer", "full"):
            raise ConnectorError(f"`{name}`: `expose` ya defer ya full olmalı.")

        found.append(
            Connector(
                name=str(name),
                command=command,
                args=list(args),
                env=dict(env),
                url=url,
                headers=dict(headers),
                enabled=bool(spec.get("enabled", True)),
                expose=expose,
            )
        )
    return found


def read_raw(state_dir: Path | str) -> str:
    path = Path(state_dir) / FILE
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_RAW


def save(state_dir: Path | str, raw: str) -> list[Connector]:
    """Metni doğrular ve yazar. Bozuksa dosyaya dokunulmaz."""
    found = parse(raw)
    path = Path(state_dir) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(raw, encoding="utf-8")
    temp.replace(path)
    return found


def load(state_dir: Path | str) -> tuple[list[Connector], list[str]]:
    """Kayıtlı bağlayıcılar. Bozuk dosya boş liste + sorun olarak döner."""
    raw = read_raw(state_dir)
    try:
        return [c for c in parse(raw) if c.enabled], []
    except ConnectorError as exc:
        return [], [str(exc)]


def _expand(value: str) -> str:
    """`${AD}` göndermelerini ortamdan doldurur.

    Eksik değişken sessizce boş geçilmiyor: boş bir Authorization başlığı
    "yetkisiz" hatası olarak geri dönüyor ve sebebi görünmüyor. Burada
    adıyla söyleniyor — değer Ayarlar › Anahtarlar'a yazılınca düzeliyor.
    """

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        got = os.environ.get(name)
        if got is None:
            raise ConnectorError(
                f"`${{{name}}}` ortamda yok. Değeri Ayarlar › Anahtarlar'a "
                f"`{name}` adıyla ekle."
            )
        return got

    return _ENV_REF.sub(fill, value)


# -- OAuth: uzak sunucular için giriş ------------------------------------
#
# Bazı uzak MCP sunucuları sabit token değil OAuth istiyor (MCP 2025-06-18
# yetkilendirme sözleşmesi): istek 401 dönüyor, istemci tarayıcıda giriş
# açıyor, jetonu alıp saklıyor ve sonraki isteklerde Bearer taşıyor. Akış
# Claude Code'unkiyle aynı:
#
#   keşif     korunan kaynak metaverisi (RFC 9728) yetki sunucusunu söylüyor,
#             yetki sunucusu metaverisi (RFC 8414 / OIDC) uçları veriyor
#   kayıt     dinamik istemci kaydı (RFC 7591) — elle client_id derdi yok
#   giriş     tarayıcıda yetki kodu + PKCE (S256), geri dönüş 127.0.0.1'e
#   jeton     takas + saklama; yenileme jetonu varsa sessiz tazeleme
#
# Jetonlar `.neocp/mcp_oauth.json` içinde sunucu adıyla duruyor ve ayar
# görüntüsüne hiçbir zaman çıkmıyor.

TOKENS_FILE = "mcp_oauth.json"
LOGIN_TIMEOUT_S = 180.0
LOGIN_HINT = "Giriş gerekiyor: Ayarlar › Bağlantılar'da 'Giriş yap'."


def _tokens_read(state_dir: Path | str) -> dict[str, Any]:
    path = Path(state_dir) / TOKENS_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _tokens_write(state_dir: Path | str, data: dict[str, Any]) -> None:
    path = Path(state_dir) / TOKENS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    try:  # jeton dosyası yalnızca sahibine — elden geldiğince
        os.chmod(path, 0o600)
    except OSError:
        pass


def forget_login(state_dir: Path | str, name: str) -> bool:
    """Bir sunucunun jetonlarını siler. Çıkış bu."""
    stored = _tokens_read(state_dir)
    if name not in stored:
        return False
    del stored[name]
    _tokens_write(state_dir, stored)
    return True


def _json_request(
    url: str,
    *,
    form: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Küçük JSON istemcisi: `form` form-kodlu POST, `body` JSON POST, yoksa GET.

    Testler bunun yerine sahte bir çağrılabilir veriyor; OAuth adımlarının
    hiçbiri ağa doğrudan dokunmuyor.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    data = None
    sent = {"Accept": "application/json", "User-Agent": USER_AGENT, **(headers or {})}
    if form is not None:
        data = urllib.parse.urlencode(form).encode("ascii")
        sent["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        sent["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=sent)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise ConnectorError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ConnectorError(f"Bağlanılamadı: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"Cevap JSON değil: {url}") from exc


def _oauth_discover(url: str, http: Any = _json_request) -> dict[str, Any]:
    """Yetki sunucusunun uçlarını bulur.

    Önce korunan kaynak metaverisi: MCP sunucusu hangi yetki sunucusunu
    kullandığını orada söylüyor. Yoksa kaynağın kendisi yetki sunucusu
    sayılıyor (eski sunucular böyle). Sonra uçlar: RFC 8414, olmazsa OIDC.
    """
    from urllib.parse import urlsplit

    parts = urlsplit(_expand(url))
    origin = f"{parts.scheme}://{parts.netloc}"

    issuer = origin
    try:
        meta = http(origin + "/.well-known/oauth-protected-resource")
        servers = meta.get("authorization_servers") or []
        if servers:
            issuer = str(servers[0]).rstrip("/")
    except ConnectorError:
        pass

    for probe in ("/.well-known/oauth-authorization-server",
                  "/.well-known/openid-configuration"):
        try:
            meta = http(issuer + probe)
        except ConnectorError:
            continue
        if meta.get("authorization_endpoint") and meta.get("token_endpoint"):
            return meta
    raise ConnectorError(
        "Sunucu OAuth uçlarını duyurmuyor. Sabit token istiyorsa `headers` "
        "alanına \"Authorization\": \"Bearer ${AD}\" yazılır."
    )


def _pkce() -> tuple[str, str]:
    """PKCE (S256): doğrulayıcı ve karşılığı."""
    import base64
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _oauth_register(meta: dict[str, Any], redirect: str, http: Any = _json_request) -> str:
    """Dinamik istemci kaydı. `client_id` döner."""
    spot = meta.get("registration_endpoint")
    if not spot:
        raise ConnectorError(
            "Yetki sunucusu istemci kaydını (RFC 7591) desteklemiyor; bu "
            "sunucu için elle alınmış bir token gerekiyor."
        )
    answer = http(spot, body={
        "client_name": "neocp",
        "redirect_uris": [redirect],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })
    client_id = str(answer.get("client_id") or "")
    if not client_id:
        raise ConnectorError("İstemci kaydı client_id döndürmedi.")
    return client_id


def _catch_code(timeout: float) -> tuple[str, Any]:
    """127.0.0.1'de tek kullanımlık geri dönüş dinleyicisi.

    (geri dönüş adresi, bekleyici) döner; bekleyici tarayıcıdan kod gelene
    ya da süre dolana kadar bloklar.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlsplit

    got: dict[str, str] = {}

    class Catcher(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib arayüzü
            query = parse_qs(urlsplit(self.path).query)
            for key in ("code", "state", "error"):
                if key in query:
                    got[key] = query[key][0]
            got.setdefault("done", "1")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h3>Giriş tamam — bu sekmeyi kapatıp neo'ya dönebilirsin.</h3>"
                .encode("utf-8"))

        def log_message(self, *args: Any) -> None:  # sessiz
            pass

    server = HTTPServer(("127.0.0.1", 0), Catcher)
    port = server.server_address[1]

    def wait() -> dict[str, str]:
        import time

        server.timeout = 1.0
        deadline = time.monotonic() + timeout
        try:
            while "done" not in got and time.monotonic() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        return got

    return f"http://127.0.0.1:{port}/callback", wait


def login(
    connector: Connector,
    state_dir: Path | str,
    *,
    http: Any = _json_request,
    browse: Any = None,
    announce: Any = None,
    timeout: float = LOGIN_TIMEOUT_S,
) -> str:
    """Tarayıcıda OAuth girişi yürütür ve jetonları saklar.

    `announce` verilirse giriş adresi ona da söyleniyor: tarayıcı arka
    planda ya da başka bir oturumda açılmış olabilir — adres arayüzde
    görünürse kullanıcı elle de açabilir.
    """
    import time as clock

    if connector.kind != "http":
        raise ConnectorError("Giriş yalnızca uzak (url) sunucular için.")

    meta = _oauth_discover(connector.url, http)
    redirect, wait = _catch_code(timeout)
    client_id = _oauth_register(meta, redirect, http)
    verifier, challenge = _pkce()

    import secrets
    from urllib.parse import urlencode

    state = secrets.token_urlsafe(16)
    resource = _expand(connector.url)
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        # RFC 8707: jeton bu kaynak için istensin — başka sunucuda geçmesin.
        "resource": resource,
    }
    if meta.get("scopes_supported"):
        query["scope"] = " ".join(str(s) for s in meta["scopes_supported"])

    target = meta["authorization_endpoint"] + "?" + urlencode(query)
    if announce is not None:
        try:
            announce(target)
        except Exception:
            pass
    if browse is None:
        import webbrowser

        browse = webbrowser.open
    browse(target)

    got = wait()
    if got.get("error"):
        raise ConnectorError(f"Giriş reddedildi: {got['error']}")
    if not got.get("code"):
        raise ConnectorError("Giriş zaman aşımına uğradı — tarayıcıdaki adım tamamlanmadı.")
    if got.get("state") != state:
        raise ConnectorError("Giriş cevabı eşleşmedi (state); yeniden dene.")

    answer = http(meta["token_endpoint"], form={
        "grant_type": "authorization_code",
        "code": got["code"],
        "redirect_uri": redirect,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": resource,
    })
    if not answer.get("access_token"):
        raise ConnectorError("Jeton alınamadı: sunucu access_token döndürmedi.")

    stored = _tokens_read(state_dir)
    stored[connector.name] = {
        "access_token": str(answer["access_token"]),
        "refresh_token": str(answer.get("refresh_token") or ""),
        "expires_at": clock.time() + float(answer.get("expires_in") or 3600),
        "token_endpoint": meta["token_endpoint"],
        "client_id": client_id,
        "resource": resource,
    }
    _tokens_write(state_dir, stored)
    return "Giriş tamam."


def _bearer(state_dir: Path | str | None, name: str, http: Any = _json_request) -> str:
    """Geçerli erişim jetonu; süresi geçtiyse sessizce tazeler.

    Tazeleme başarısız olursa eldeki jeton döner — 401'i sunucu söylesin,
    kullanıcı 'Giriş yap' ile yeniler.
    """
    import time as clock

    if state_dir is None:
        return ""
    stored = _tokens_read(state_dir)
    entry = stored.get(name)
    if not isinstance(entry, dict) or not entry.get("access_token"):
        return ""

    if clock.time() < float(entry.get("expires_at") or 0) - 30:
        return str(entry["access_token"])

    refresh = str(entry.get("refresh_token") or "")
    if not refresh:
        return str(entry["access_token"])
    try:
        answer = http(str(entry.get("token_endpoint") or ""), form={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": str(entry.get("client_id") or ""),
            "resource": str(entry.get("resource") or ""),
        })
    except ConnectorError:
        return str(entry["access_token"])

    if answer.get("access_token"):
        entry["access_token"] = str(answer["access_token"])
        if answer.get("refresh_token"):
            entry["refresh_token"] = str(answer["refresh_token"])
        entry["expires_at"] = clock.time() + float(answer.get("expires_in") or 3600)
        stored[name] = entry
        _tokens_write(state_dir, stored)
    return str(entry["access_token"])


# -- oturum -------------------------------------------------------------


class Session:
    """Tek bir MCP sunucusuyla açık oturum.

    Çağrılar bir kilitle sıralanıyor: JSON-RPC eşzamanlı isteklere izin
    veriyor ama stdio üstünde cevapları ayıklamak karmaşıklığa değmiyor —
    araç çağrıları zaten `parallel_safe=False`.
    """

    def __init__(self, connector: Connector, state_dir: Path | str | None = None) -> None:
        self.connector = connector
        # OAuth jetonları burada aranıyor; None ise giriş katmanı kapalı.
        self.state_dir = state_dir
        self.tools: list[dict[str, Any]] = []
        self.error = ""
        self._lock = threading.Lock()
        self._id = 0
        # stdio tarafı
        self._proc: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._stderr_tail: list[str] = []
        # http tarafı
        self._session_id = ""

    @property
    def ok(self) -> bool:
        return bool(self.tools) and not self.error

    # -- açılış --------------------------------------------------------

    def open(self) -> None:
        """Bağlanır, el sıkışır, araç listesini alır. Hata `self.error`a."""
        try:
            if self.connector.kind == "stdio":
                self._spawn()
            hello = self._rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": CLIENT,
                },
                timeout=CONNECT_TIMEOUT_S,
            )
            # Sunucunun söylediği sürümle devam ediliyor; pazarlığı burada
            # büyütmeye gerek yok — araç çağrısı her sürümde aynı.
            _ = hello.get("protocolVersion")
            self._notify("notifications/initialized")
            listed = self._rpc("tools/list", {}, timeout=CONNECT_TIMEOUT_S)
            self.tools = [t for t in listed.get("tools") or [] if isinstance(t, dict)]
            self.error = ""
        except ConnectorError as exc:
            self.error = str(exc)
            self.close()
        except Exception as exc:  # ağ, süreç, çözümleme — hepsi aynı kapı
            self.error = f"{type(exc).__name__}: {exc}"
            self.close()

    def call(self, tool: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Bir aracı çağırır. (metin, hata mı) döner — istisna fırlatmaz."""
        try:
            result = self._rpc(
                "tools/call",
                {"name": tool, "arguments": arguments or {}},
                timeout=CALL_TIMEOUT_S,
            )
        except Exception as exc:
            return f"Bağlantı hatası ({self.connector.name}): {exc}", True

        parts: list[str] = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, dict):
                parts.append(f"[{item.get('type', 'bilinmeyen')} içerik]")
        text = "\n".join(p for p in parts if p).strip() or "(boş cevap)"
        return text, bool(result.get("isError"))

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    # -- taşıma: stdio -------------------------------------------------

    def _spawn(self) -> None:
        import shutil

        command = _expand(self.connector.command)
        args = [_expand(a) for a in self.connector.args]
        # Windows'ta `npx` gibi komutlar `.cmd` sarmalayıcı; `which` onu
        # buluyor, çıplak Popen bulamıyordu.
        resolved = shutil.which(command) or command

        env = dict(os.environ)
        env.update({k: _expand(v) for k, v in self.connector.env.items()})

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._proc = subprocess.Popen(
                [resolved, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
        except OSError as exc:
            raise ConnectorError(f"Komut başlatılamadı: {command} — {exc}") from exc

        threading.Thread(
            target=self._pump_stdout, daemon=True, name=f"mcp-{self.connector.name}"
        ).start()
        # stderr boşaltılmazsa boru dolunca sunucu kilitleniyor; son satırlar
        # da hata mesajı olarak işe yarıyor.
        threading.Thread(
            target=self._pump_stderr, daemon=True, name=f"mcp-{self.connector.name}-err"
        ).start()

    def _pump_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self._lines.put(line)
        self._lines.put("")  # akış kapandı işareti

    def _pump_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            self._stderr_tail.append(line.strip())
            del self._stderr_tail[:-5]

    def _rpc(self, method: str, params: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        with self._lock:
            self._id += 1
            message = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
            if self.connector.kind == "http":
                return self._http_round(message, timeout)
            return self._stdio_round(message, timeout)

    def _notify(self, method: str) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        try:
            with self._lock:
                if self.connector.kind == "http":
                    self._http_post(message, timeout=CONNECT_TIMEOUT_S)
                else:
                    self._stdio_write(message)
        except Exception:
            # Bildirim nezaket: sunucu istemiyorsa akış yine de çalışıyor.
            pass

    def _stdio_write(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise ConnectorError("Süreç çalışmıyor.")
        proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def _stdio_round(self, message: dict[str, Any], timeout: float) -> dict[str, Any]:
        import time

        self._stdio_write(message)
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ConnectorError(f"Cevap gelmedi ({message['method']}, {timeout:.0f} sn).")
            try:
                line = self._lines.get(timeout=left)
            except queue.Empty:
                continue
            if not line.strip():
                if self._proc is None or self._proc.poll() is not None:
                    tail = "; ".join(t for t in self._stderr_tail if t)
                    raise ConnectorError(
                        "Sunucu süreci kapandı." + (f" Son çıktı: {tail}" if tail else "")
                    )
                continue
            try:
                answer = json.loads(line)
            except json.JSONDecodeError:
                continue  # protokol dışı gürültü (bir print kaçmış olabilir)
            if not isinstance(answer, dict) or answer.get("id") != message["id"]:
                continue  # bildirim ya da başka bir isteğin cevabı değil, bizim değil
            return self._unwrap(answer)

    # -- taşıma: http --------------------------------------------------

    def _http_post(self, message: dict[str, Any], timeout: float) -> tuple[str, str]:
        """Mesajı gönderir; (içerik türü, gövde) döner."""
        import urllib.error
        import urllib.request

        url = _expand(self.connector.url)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        }
        headers.update({k: _expand(v) for k, v in self.connector.headers.items()})
        # Elle yazılmış Authorization her zaman kazanır; yoksa ve giriş
        # yapılmışsa OAuth jetonu takılır (süresi geçtiyse sessizce tazelenir).
        if "Authorization" not in headers:
            token = _bearer(self.state_dir, self.connector.name)
            if token:
                headers["Authorization"] = "Bearer " + token
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        request = urllib.request.Request(
            url, data=json.dumps(message).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                sid = response.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                kind = (response.headers.get("Content-Type") or "").split(";")[0].strip()
                return kind, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                # Sunucu OAuth istiyor: bu bir arıza değil, giriş çağrısı.
                raise AuthRequired(LOGIN_HINT) from exc
            body = exc.read().decode("utf-8", "replace")[:300]
            raise ConnectorError(f"HTTP {exc.code}: {body or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ConnectorError(f"Bağlanılamadı: {exc.reason}") from exc

    def _http_round(self, message: dict[str, Any], timeout: float) -> dict[str, Any]:
        kind, body = self._http_post(message, timeout)
        for answer in _decode_http(kind, body):
            if isinstance(answer, dict) and answer.get("id") == message["id"]:
                return self._unwrap(answer)
        raise ConnectorError(f"Sunucu `{message['method']}` için cevap döndürmedi.")

    # -- ortak ---------------------------------------------------------

    def _unwrap(self, answer: dict[str, Any]) -> dict[str, Any]:
        if "error" in answer:
            fault = answer["error"] or {}
            raise ConnectorError(str(fault.get("message") or "Sunucu hata döndürdü."))
        result = answer.get("result")
        return result if isinstance(result, dict) else {}


def _decode_http(kind: str, body: str) -> list[Any]:
    """HTTP gövdesini mesaj listesine çevirir — düz JSON ya da SSE."""
    if kind == "text/event-stream":
        found: list[Any] = []
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    found.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    continue
        return found
    if not body.strip():
        return []
    try:
        return [json.loads(body)]
    except json.JSONDecodeError:
        return []


# -- havuz ve defter köprüsü --------------------------------------------


class Pool:
    """Açık oturumların tamamı. Sunucu nesnesinde tek bir örnek duruyor."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.state_dir: Path | str | None = None
        self._lock = threading.Lock()

    def connect(self, connectors: list[Connector],
                state_dir: Path | str | None = None) -> None:
        """Eski oturumları kapatıp verilenlere bağlanır."""
        if state_dir is not None:
            self.state_dir = state_dir
        with self._lock:
            old, self.sessions = self.sessions, {}
        for session in old.values():
            session.close()
        for connector in connectors:
            session = Session(connector, self.state_dir)
            session.open()
            with self._lock:
                self.sessions[connector.name] = session

    def status(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self.sessions.values())
        logged = _tokens_read(self.state_dir) if self.state_dir is not None else {}
        return [
            {
                "name": s.connector.name,
                "kind": s.connector.kind,
                "where": s.connector.url or s.connector.command,
                "ok": s.ok,
                "error": s.error,
                "auth": bool(logged.get(s.connector.name)),
                "tools": [str(t.get("name") or "") for t in s.tools],
            }
            for s in sessions
        ]

    def close(self) -> None:
        with self._lock:
            sessions, self.sessions = list(self.sessions.values()), {}
        for session in sessions:
            session.close()


def tool_name(server: str, tool: str) -> str:
    """Defterdeki ad: `mcp__sunucu__araç` — Claude Code ile aynı düzen."""
    plain = f"mcp__{_UNSAFE.sub('_', server)}__{_UNSAFE.sub('_', tool)}"
    return plain[:64]


def register(registry: Any, pool: Pool) -> tuple[list[str], list[str]]:
    """Havuzdaki araçları deftere yazar; kalkan sunucuların araçlarını düşer.

    İki yol var ve varsayılan ERTELEME:

    * `expose="defer"` — sunucunun araçları deftere şemalarıyla GİRMEZ.
      Hepsinin yerine tek bir `connector` köprü aracı durur: model önce
      listeler, gerekirse tek aracın şemasını ister, sonra çağırır. Ölçülen
      sebep: Notion'un 28 şeması ~27.000 token ve her mesajla gidiyordu —
      istemin yarısı, o mesajda hiç kullanılmayan araç tarifleriydi.
    * `expose="full"` — eski davranış: her araç `mcp__sunucu__araç` adıyla
      tam şemasıyla kaydedilir. Birkaç araçlı küçük sunucuda tek turda
      doğru çağrı için hâlâ en iyisi.

    Kayıtlar `source="mcp:*"` taşıyor: yerleşiklerle karışmıyor, sunucu
    gidince topluca silinebiliyor.
    """
    from .tools.base import ToolSpec

    wanted: dict[str, ToolSpec] = {}
    deferred = [s for s in pool.sessions.values()
                if s.ok and s.connector.expose != "full"]
    if deferred:
        wanted[BRIDGE_TOOL] = _bridge_spec(pool, deferred, ToolSpec)

    for session in pool.sessions.values():
        if session.connector.expose != "full":
            continue
        for tool in session.tools:
            plain = str(tool.get("name") or "").strip()
            if not plain:
                continue
            name = tool_name(session.connector.name, plain)
            schema = tool.get("inputSchema")
            if not isinstance(schema, dict) or schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            wanted[name] = ToolSpec(
                name=name,
                description=(
                    f"[{session.connector.name} MCP sunucusundan] "
                    + str(tool.get("description") or plain).strip()
                ),
                input_schema=schema,
                handler=_handler(session, plain),
                # Dış sunucunun ne yaptığı buradan görünmüyor; izin kapısı
                # temkinli tarafta durmalı.
                mutates=True,
                parallel_safe=False,
                source=f"mcp:{session.connector.name}",
            )

    dropped: list[str] = []
    for spec in list(registry.all()):
        source = getattr(spec, "source", None) or ""
        if source.startswith("mcp:") and spec.name not in wanted:
            registry.unregister(spec.name)
            dropped.append(spec.name)

    added: list[str] = []
    have = {spec.name for spec in registry.all()}
    for name, spec in wanted.items():
        if name in have:
            registry.replace(spec)
        else:
            registry.register(spec)
            added.append(name)

    return added, dropped


BRIDGE_TOOL = "connector"

# describe cevabındaki tek şemanın üst sınırı: Notion'un en şişkini ~5.600
# token — gerektiğinde bir kez ödenir ama sınırsız da bırakılmaz.
DESCRIBE_CAP = 24_000


def _bridge_spec(pool: Pool, deferred: list[Session], ToolSpec: Any) -> Any:
    lines = []
    for session in deferred:
        names = [str(t.get("name") or "") for t in session.tools]
        head = ", ".join(names[:8]) + ("…" if len(names) > 8 else "")
        lines.append(f"  {session.connector.name}: {len(names)} araç ({head})")
    servers = "\n".join(lines)

    description = f"""
Bağlı MCP sunucularının araçlarına açılan kapı. Sunucular ve araçları:

{servers}

  tools     bir sunucunun araçlarını kısa açıklamalarıyla listeler.
  describe  TEK aracın tam şemasını verir (parametreler). Bir aracı ilk
            kez çağırmadan önce şemasına bak — alan adlarını tahmin etme.
  call      aracı çağırır: `tool` + `args` (şemaya uygun nesne).

Basit araçlarda (tek metin alanı gibi) describe'ı atlayıp doğrudan call
deneyebilirsin; hata mesajı şemayı tarif eder.
"""

    async def run(args: dict[str, Any], ctx: Any) -> Any:
        import asyncio

        from .tools.base import ToolResult

        action = str(args.get("action") or "")
        server = str(args.get("server") or "").strip()
        sessions = {s.connector.name: s for s in pool.sessions.values() if s.ok}
        if not sessions:
            return ToolResult.error("Bağlı MCP sunucusu yok.")
        if server and server not in sessions:
            return ToolResult.error(
                f"Sunucu yok: {server}. Bağlı olanlar: {', '.join(sessions)}")

        if action == "tools":
            picked = [sessions[server]] if server else list(sessions.values())
            lines2: list[str] = []
            for s in picked:
                lines2.append(f"## {s.connector.name}")
                for t in s.tools:
                    brief = str(t.get("description") or "").strip()
                    brief = brief.split("\n")[0][:140]
                    lines2.append(f"- {t.get('name')}: {brief}")
            return ToolResult("\n".join(lines2))

        tool = str(args.get("tool") or "").strip()
        if not tool:
            return ToolResult.error("`tool` gerekli.")
        owner = None
        if server:
            owner = sessions[server]
        else:
            for s in sessions.values():
                if any(t.get("name") == tool for t in s.tools):
                    owner = s
                    break
        if owner is None or not any(t.get("name") == tool for t in owner.tools):
            return ToolResult.error(
                f"Araç bulunamadı: {tool}. `action=tools` ile listeye bak.")

        if action == "describe":
            spec = next(t for t in owner.tools if t.get("name") == tool)
            body = json.dumps(spec.get("inputSchema") or {}, ensure_ascii=False, indent=1)
            if len(body) > DESCRIBE_CAP:
                body = body[:DESCRIBE_CAP] + "… (kırpıldı)"
            return ToolResult(
                f"{tool} — {str(spec.get('description') or '').strip()}\n\n"
                f"Parametre şeması:\n{body}"
            )

        if action == "call":
            call_args = args.get("args")
            if not isinstance(call_args, dict):
                return ToolResult.error("`args` bir nesne olmalı (şemaya uygun).")
            text, failed = await asyncio.to_thread(owner.call, tool, call_args)
            return ToolResult.error(text) if failed else ToolResult(text)

        return ToolResult.error("`action` tools, describe ya da call olmalı.")

    return ToolSpec(
        name=BRIDGE_TOOL,
        description=description,
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["tools", "describe", "call"]},
                "server": {"type": "string",
                           "description": "Sunucu adı; tek sunucu varsa boş bırakılabilir."},
                "tool": {"type": "string", "description": "describe/call için araç adı."},
                "args": {"type": "object",
                         "description": "call için aracın parametreleri (şemaya uygun)."},
            },
            "required": ["action"],
        },
        handler=run,
        mutates=True,
        parallel_safe=False,
        source="mcp:*",
    )


def _handler(session: Session, tool: str) -> Any:
    async def run(args: dict[str, Any], ctx: Any) -> Any:
        import asyncio

        from .tools.base import ToolResult

        text, failed = await asyncio.to_thread(session.call, tool, dict(args or {}))
        return ToolResult.error(text) if failed else ToolResult(text)

    return run
