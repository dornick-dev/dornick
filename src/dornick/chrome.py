"""dornick chrome — tarayıcıyı DevTools protokolüyle sürmek.

Claude'un Chrome eklentisinin yerlisi: dornick, Chrome ya da Edge'i hata
ayıklama kapısıyla (`--remote-debugging-port`) başlatıyor ve DevTools
protokolü (CDP) üzerinden konuşuyor — sekmeleri görüyor, sayfa açıyor,
metni okuyor, ekran görüntüsü alıyor.

Tarayıcı **Dornick'in kendi profiliyle** açılıyor (`.dornick/chrome/`):
kullanıcının gündelik Chrome'una bağlanmak mümkün değil çünkü o kapı
kapalı açılıyor. Ayrı profil aynı zamanda bir sınır — kullanıcı hangi
sitelere giriş verdiyse dornick yalnızca onları görüyor ve o oturumlar
profil klasöründe kalıcı: bir kez giriş yapılan siteye ertesi gün de
girilebiliyor.

CDP'nin iki yüzü var:
    http  sekme listesi, sekme açma/kapama — düz JSON uçları
    ws    sayfanın içi (JavaScript çalıştırma, ekran görüntüsü)

stdlib'de WebSocket istemcisi yok; buradaki `Wire` gereken kadarını
yapıyor: tek bağlantı, maskeli metin çerçeveleri, parçalı mesaj ve
ping/pong. Bir kütüphane bağımlılığına değmeyecek kadar küçük bir iş.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ortam

DEFAULT_PORT = 9222

# Tarayıcının kapıyı açması ilk kurulumda yavaş olabiliyor.
BOOT_WAIT_S = 20.0

# Tek bir CDP cevabı için bekleme. Ekran görüntüsü büyük bir sayfada
# birkaç saniye sürebiliyor.
CALL_TIMEOUT_S = 30.0


class BrowseError(RuntimeError):
    """Tarayıcı hatası — mesaj modele gidiyor, öğretici olmalı."""


def executable() -> str | None:
    """Kurulu Chrome/Edge. PATH'te yoksa bilinen konumlara bakılıyor."""
    import shutil

    for name in ("chrome", "msedge", "chromium", "google-chrome", "brave"):
        if found := shutil.which(name):
            return found

    trunk = os.environ.get("ProgramFiles", r"C:\Program Files")
    branch = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    for spot in (
        rf"{trunk}\Google\Chrome\Application\chrome.exe",
        rf"{branch}\Google\Chrome\Application\chrome.exe",
        rf"{local}\Google\Chrome\Application\chrome.exe",
        rf"{trunk}\Microsoft\Edge\Application\msedge.exe",
        rf"{branch}\Microsoft\Edge\Application\msedge.exe",
    ):
        if spot and Path(spot).is_file():
            return spot
    return None


def available() -> bool:
    return executable() is not None


# Süreç-geneli tek tarayıcı. Ana ajan ve alt ajanlar ayrı araç defterleri
# taşıyor; her biri kendi Browser'ını kursaydı aynı anda aynı kapıyı açmaya
# çalışıp yarışırlardı. Tek örnek: hepsi aynı Chrome'u sürüyor, aynı
# sekmeleri görüyor.
_shared: dict[tuple[str, int], "Browser"] = {}
_shared_lock: Any = None


def shared(state_dir: Path | str, port: int = DEFAULT_PORT) -> "Browser":
    import threading

    global _shared_lock
    if _shared_lock is None:
        _shared_lock = threading.Lock()
    key = (str(state_dir), int(port))
    with _shared_lock:
        box = _shared.get(key)
        if box is None:
            box = Browser(state_dir, port)
            _shared[key] = box
        return box


# -- WebSocket teli -----------------------------------------------------


class Wire:
    """RFC 6455'in CDP için gereken kadarı — istemci tarafı.

    İstemci çerçeveleri maskeli gitmek zorunda; sunucununkiler çıplak
    geliyor. Uzunluk 7 bite sığmazsa 16 ya da 64 bitlik ek alan var —
    ekran görüntüsü 64 bitlik yolu gerçekten kullanıyor.
    """

    def __init__(self, url: str, timeout: float = CALL_TIMEOUT_S) -> None:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or 80
        path = parts.path or "/"

        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        self.sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        answer = b""
        while b"\r\n\r\n" not in answer:
            piece = self.sock.recv(4096)
            if not piece:
                raise BrowseError("El sıkışma yarıda kesildi.")
            answer += piece
        if b" 101 " not in answer.split(b"\r\n", 1)[0]:
            raise BrowseError("Tarayıcı WebSocket'e geçmeyi kabul etmedi.")

    def send(self, text: str) -> None:
        payload = text.encode("utf-8")
        head = bytearray([0x81])  # FIN + metin
        size = len(payload)
        if size < 126:
            head.append(0x80 | size)
        elif size < 1 << 16:
            head.append(0x80 | 126)
            head += struct.pack(">H", size)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", size)
        mask = os.urandom(4)
        head += mask
        veiled = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(head) + veiled)

    def recv(self) -> str:
        """Bir mesaj — parçalıysa birleştirilmiş hali."""
        gathered = b""
        while True:
            first, second = self._exactly(2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            size = second & 0x7F
            if size == 126:
                (size,) = struct.unpack(">H", self._exactly(2))
            elif size == 127:
                (size,) = struct.unpack(">Q", self._exactly(8))
            # Sunucu maskelemez; maskeliyse yine de okunur.
            mask = self._exactly(4) if second & 0x80 else b""
            body = self._exactly(size) if size else b""
            if mask:
                body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))

            if opcode == 0x9:  # ping → pong, aynı gövdeyle
                pong = bytearray([0x8A, 0x80 | len(body)])
                veil = os.urandom(4)
                pong += veil + bytes(b ^ veil[i % 4] for i, b in enumerate(body))
                self.sock.sendall(bytes(pong))
                continue
            if opcode == 0x8:
                raise BrowseError("Tarayıcı bağlantıyı kapattı.")
            if opcode == 0xA:  # pong — istemedik ama zararsız
                continue

            gathered += body
            if fin:
                return gathered.decode("utf-8", "replace")

    def _exactly(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            piece = self.sock.recv(count - len(data))
            if not piece:
                raise BrowseError("Bağlantı koptu.")
            data += piece
        return data

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# -- olay tamponu -------------------------------------------------------
#
# Kanıtlanmış yara: dornick bir web uygulaması yapıyor, sayfayı açıyor, metni
# okuyor ve "çalışıyor" diyor. Oysa sayfada JavaScript patlamış olabilir —
# konsolda kırmızı bir yığın izi, ağda 500 dönen bir istek. Bunlar
# `document.body.innerText`te GÖRÜNMEZ; sayfa yarım çizilmiş ama sessizdir.
# Kullanıcı tarayıcıyı açınca öğreniyor.
#
# `read` bunu tek başına çözemez, çünkü konsol mesajı bir OLAYDIR: geçmişte
# bir an olur ve kaybolur. Sonradan sorulamaz, ancak dinlenebilir. O yüzden
# sayfa açılırken sekmeye kalıcı bir dinleyici bağlanıyor ve olaylar burada
# birikiyor.
#
# Dürüstlük kuralı: dinleyici sayfa yüklendikten SONRA bağlandıysa daha
# önceki mesajlar kaçmıştır. Bunu uydurmuyoruz — `eksik` bayrağıyla
# söylüyoruz, çünkü "konsol temiz" demek ile "ben bakmaya geç kaldım"
# demek arasındaki fark, kullanıcının hatayı bulup bulmamasıdır.

# Sekme başına tutulan en fazla kayıt. Döngüde hata basan bir sayfa
# saniyede yüzlerce satır üretir; en tazeler zaten en yararlısı.
TAMPON = 300

# Modele varsayılan olarak gösterilen kayıt sayısı.
VARSAYILAN_N = 20

# CDP seviyelerinin ortak adları. "warning" ve "warn" aynı şey.
_SEVIYE = {
    "log": "log", "info": "info", "debug": "debug", "verbose": "debug",
    "warning": "uyari", "warn": "uyari", "error": "hata", "assert": "hata",
    "trace": "log", "dir": "log", "table": "log",
}


@dataclass(slots=True)
class KonsolSatiri:
    """Tek bir konsol mesajı ya da yakalanmamış istisna."""

    seviye: str            # log | info | debug | uyari | hata
    metin: str
    yer: str = ""          # dosya:satır
    kaynak: str = "konsol"  # konsol | istisna | tarayici

    def bicim(self) -> str:
        etiket = {"hata": "HATA", "uyari": "UYARI"}.get(self.seviye, self.seviye)
        kuyruk = f"  ({self.yer})" if self.yer else ""
        return f"[{etiket}] {self.metin}{kuyruk}"


@dataclass(slots=True)
class Istek:
    """Tek bir ağ isteği: yol, yöntem, durum, süre."""

    url: str
    yontem: str = "GET"
    durum: int = 0
    tur: str = ""
    sure_ms: float = 0.0
    hata: str = ""
    _t0: float = 0.0

    @property
    def basarisiz(self) -> bool:
        return bool(self.hata) or self.durum >= 400

    def bicim(self) -> str:
        from urllib.parse import urlsplit

        parca = urlsplit(self.url)
        kisa = (parca.path or "/") + (f"?{parca.query}" if parca.query else "")
        if len(kisa) > 80:
            kisa = kisa[:77] + "…"
        if self.hata:
            return f"{self.yontem} {kisa} — BAŞARISIZ: {self.hata}"
        durum = self.durum or "?"
        sure = f"{self.sure_ms:.0f} ms" if self.sure_ms else "—"
        return f"{self.yontem} {kisa} → {durum} · {sure}"


def _arg_metni(arg: dict[str, Any]) -> str:
    """CDP RemoteObject'ini okunur metne çevirir.

    `value` varsa odur; yoksa Chrome'un kendi tarifi (`description`) —
    bir Error nesnesinde yığın izinin tamamı orada duruyor.
    """
    if "value" in arg:
        deger = arg["value"]
        if isinstance(deger, (dict, list)):
            try:
                return json.dumps(deger, ensure_ascii=False)[:400]
            except (TypeError, ValueError):  # pragma: no cover
                return str(deger)[:400]
        return str(deger)
    for anahtar in ("description", "unserializableValue", "className"):
        if arg.get(anahtar):
            return str(arg[anahtar])
    return str(arg.get("type") or "?")


def _yer(url: Any, satir: Any) -> str:
    """"http://x/app.js:41" — ikisi de yoksa boş."""
    metin = str(url or "").strip()
    if not metin:
        return ""
    kisa = metin.rsplit("/", 1)[-1] or metin
    try:
        n = int(satir)
    except (TypeError, ValueError):
        return kisa
    return f"{kisa}:{n + 1}"


class Kayit:
    """Bir sekmeye kalıcı bağlı dinleyici: konsol ve ağ tamponu.

    Kendi WebSocket bağlantısını tutuyor ve arka planda okuyor. `Browser`in
    diğer çağrıları her seferinde taze bir bağlantı açıyor (`_call`); modern
    Chrome aynı hedefe birden çok istemciyi kabul ediyor, o yüzden ikisi
    yan yana yaşayabiliyor. Bağlanamazsak bu bir felaket değil: `hata`
    doluyor ve araç "dinleyici kurulamadı" diyor — sayfa açma işlemi
    yine de sürüyor.
    """

    def __init__(self, ws_url: str, *, limit: int = TAMPON) -> None:
        import threading

        self.konsol: deque[KonsolSatiri] = deque(maxlen=limit)
        self.istekler: deque[Istek] = deque(maxlen=limit)
        self.hata = ""
        # Dinleyici sayfa yüklendikten sonra bağlandıysa: baştaki mesajlar
        # kaçtı. Model bunu bilmeli.
        self.eksik = False
        self.baslangic = time.monotonic()
        self._acik: dict[str, Istek] = {}
        self._kapali = False
        self._wire: Wire | None = None
        self._sira = 1000
        # Kaçıncı ana-çerçeve gezinmesindeyiz? Birincisi beklediğimiz
        # sayfanın kendi yüklenmesi; onu temizlemiyoruz.
        self._gezinme = 0

        try:
            wire = Wire(ws_url, timeout=CALL_TIMEOUT_S)
            # Dinleme süresiz: zaman aşımı bir çerçevenin ortasında kesip
            # akışı bozardı. Bağlantı `kapat()` ile sonlanıyor.
            wire.sock.settimeout(None)
            self._wire = wire
            for alan in ("Runtime.enable", "Log.enable", "Network.enable",
                         "Page.enable"):
                self._sira += 1
                wire.send(json.dumps({"id": self._sira, "method": alan,
                                      "params": {}}))
        except Exception as exc:
            self.hata = f"{type(exc).__name__}: {exc}"
            return

        self._thread = threading.Thread(target=self._dinle, daemon=True)
        self._thread.start()

    @property
    def calisiyor(self) -> bool:
        return self._wire is not None and not self._kapali

    def temizle(self) -> None:
        """Yeni sayfaya geçildi: eski sayfanın kayıtları gürültü."""
        self.konsol.clear()
        self.istekler.clear()
        self._acik.clear()
        self.eksik = False
        self._gezinme = 0
        self.baslangic = time.monotonic()

    def kapat(self) -> None:
        self._kapali = True
        if self._wire is not None:
            self._wire.close()

    # -- olay döngüsü --------------------------------------------------

    def _dinle(self) -> None:
        wire = self._wire
        assert wire is not None
        while not self._kapali:
            try:
                ham = wire.recv()
            except Exception:
                return  # bağlantı kapandı ya da koptu; sessizce bit
            try:
                mesaj = json.loads(ham)
            except ValueError:  # pragma: no cover - bozuk çerçeve
                continue
            yontem = mesaj.get("method")
            if not yontem:
                continue  # bizim `enable` çağrılarımızın cevabı
            try:
                self._isle(str(yontem), mesaj.get("params") or {})
            except Exception:  # pragma: no cover - tek olay her şeyi bozmasın
                continue

    def _isle(self, yontem: str, p: dict[str, Any]) -> None:
        if yontem == "Runtime.consoleAPICalled":
            seviye = _SEVIYE.get(str(p.get("type") or "log"), "log")
            metin = " ".join(_arg_metni(a) for a in (p.get("args") or [])
                             if isinstance(a, dict))
            kareler = ((p.get("stackTrace") or {}).get("callFrames") or [])
            ilk = kareler[0] if kareler else {}
            self.konsol.append(KonsolSatiri(
                seviye, metin.strip() or "(boş mesaj)",
                _yer(ilk.get("url"), ilk.get("lineNumber")), "konsol"))

        elif yontem == "Runtime.exceptionThrown":
            ayrinti = p.get("exceptionDetails") or {}
            nesne = ayrinti.get("exception") or {}
            # `description` yığın izini de taşıyor; yoksa `text` kalıyor.
            metin = str(nesne.get("description") or ayrinti.get("text")
                        or "yakalanmamış istisna")
            self.konsol.append(KonsolSatiri(
                "hata", metin.strip(),
                _yer(ayrinti.get("url"), ayrinti.get("lineNumber")), "istisna"))

        elif yontem == "Log.entryAdded":
            # Tarayıcının kendi günlüğü: "Failed to load resource: 404",
            # CSP ihlalleri, karışık içerik uyarıları. Sayfanın konsolunda
            # görünen ama `console.*` çağrısı OLMAYAN satırlar burada.
            giris = p.get("entry") or {}
            seviye = _SEVIYE.get(str(giris.get("level") or "info"), "log")
            self.konsol.append(KonsolSatiri(
                seviye, str(giris.get("text") or "").strip() or "(boş kayıt)",
                _yer(giris.get("url"), giris.get("lineNumber")), "tarayici"))

        elif yontem == "Network.requestWillBeSent":
            istek = p.get("request") or {}
            kayit = Istek(
                url=str(istek.get("url") or ""),
                yontem=str(istek.get("method") or "GET"),
                tur=str(p.get("type") or ""),
                _t0=float(p.get("timestamp") or 0.0),
            )
            kimlik = str(p.get("requestId") or "")
            if kimlik:
                self._acik[kimlik] = kayit
            self.istekler.append(kayit)

        elif yontem == "Network.responseReceived":
            if (kayit := self._acik.get(str(p.get("requestId") or ""))) is None:
                return
            cevap = p.get("response") or {}
            kayit.durum = int(cevap.get("status") or 0)
            if tur := str(p.get("type") or ""):
                kayit.tur = tur

        elif yontem in ("Network.loadingFinished", "Network.loadingFailed"):
            kimlik = str(p.get("requestId") or "")
            if (kayit := self._acik.pop(kimlik, None)) is None:
                return
            bitis = float(p.get("timestamp") or 0.0)
            if kayit._t0 and bitis > kayit._t0:
                kayit.sure_ms = (bitis - kayit._t0) * 1000.0
            if yontem == "Network.loadingFailed":
                iptal = bool(p.get("canceled"))
                kayit.hata = str(p.get("errorText") or
                                 ("iptal edildi" if iptal else "yüklenemedi"))

        elif yontem == "Page.frameNavigated":
            # Yeni belge: eski sayfanın kayıtları artık gürültü — model A
            # sayfasının hatalarını B sayfasına yazmasın.
            #
            # AMA ilk gezinme silinmez ve bu ölçülerek öğrenildi: dinleyici
            # sayfa yüklenmeden bağlanıyor, sonra belgenin kendi commit'i
            # `frameNavigated` olarak geliyor ve o ana kadar biriken
            # istekleri (belgenin kendisi, ilk betikler, ilk 404'ler)
            # süpürüyordu. Canlı denemede ağ listesi 4 istek yerine 2 ile
            # geldi. Bu yüzden yalnızca İKİNCİ ve sonraki gezinmeler
            # temizliyor: birincisi zaten bizim beklediğimiz sayfa.
            if (p.get("frame") or {}).get("parentId"):
                return  # iframe gezinmesi sayfayı değiştirmiyor
            self._gezinme += 1
            if self._gezinme > 1:
                self.konsol.clear()
                self.istekler.clear()
                self._acik.clear()


# -- tarayıcı -----------------------------------------------------------


class Browser:
    """Hata ayıklama kapısı açık bir Chrome/Edge ve onun sekmeleri."""

    def __init__(self, state_dir: Path | str, port: int = DEFAULT_PORT) -> None:
        import threading

        self.state_dir = Path(state_dir)
        self.port = port
        self._proc: subprocess.Popen[bytes] | None = None
        # Paylaşılan örnekte iki alt ajan aynı anda başlatmaya kalkabilir;
        # başlatma tek seferde olsun.
        self._boot_lock = threading.Lock()
        # Sekme kimliği → dinleyici. Sekme başına tek dinleyici yeter.
        self._kayitlar: dict[str, Kayit] = {}

    # -- http yüzü -----------------------------------------------------

    def _http(self, path: str, method: str = "GET") -> Any:
        import urllib.request

        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method=method
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}

    def alive(self) -> bool:
        try:
            return bool(self._http("/json/version"))
        except Exception:
            return False

    def ensure(self) -> None:
        """Tarayıcı ayaktaysa dokunmaz; değilse kendi profiliyle başlatır."""
        if self.alive():
            return
        with self._boot_lock:
            # Kilidi beklerken başkası başlatmış olabilir.
            if self.alive():
                return
            self._launch()

    def _launch(self) -> None:
        exe = executable()
        if exe is None:
            raise BrowseError(
                "Chrome ya da Edge bulunamadı. Biri kuruluysa PATH'e ekli olmalı."
            )
        profile = self.state_dir / "chrome"
        profile.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(
            [
                exe,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Chrome/Edge zaten pencereli (GUI) süreç; bayrak konsollu
            # bir sarmalayıcıdan başlatılsa bile cmd parlatmamayı garantiler.
            **ortam.sessiz_bayraklar(),
        )
        deadline = time.monotonic() + BOOT_WAIT_S
        while time.monotonic() < deadline:
            if self.alive():
                return
            time.sleep(0.4)
        raise BrowseError("Tarayıcı açıldı ama hata ayıklama kapısı cevap vermiyor.")

    def tabs(self) -> list[dict[str, Any]]:
        found = self._http("/json/list")
        return [t for t in found if isinstance(t, dict) and t.get("type") == "page"]

    def open(self, url: str) -> dict[str, Any]:
        """Yeni sekmede adres açar — dinleyici bağlandıktan SONRA gezinerek.

        Sekme doğrudan hedef adresle açılabilirdi (`/json/new?<url>`) ve
        önce öyleydi; ama o zaman yükleme, biz dinleyiciyi bağlayana kadar
        çoktan başlıyor. Canlı denemede sonuç ölçüldü: belgenin kendi
        isteği ve ilk betiğin 404'ü ağ listesinde HİÇ görünmedi.
        Bu yüzden sekme boş açılıyor, dinleyici bağlanıyor, gezinme ondan
        sonra başlıyor — ilk bayttan itibaren her şey kayıt altında.
        """
        from urllib.parse import quote

        spot = "/json/new?" + quote("about:blank", safe=":/?&=%")
        try:
            # Yeni Chrome PUT istiyor; eskisi GET kabul ediyordu.
            made = self._http(spot, method="PUT")
        except Exception:
            made = self._http(spot)
        if not isinstance(made, dict) or not made.get("id"):
            raise BrowseError("Sekme açılamadı.")

        self.dinle(made, taze=True)
        try:
            self._call(made, "Page.navigate", {"url": url})
        except BrowseError:
            # Gezinme kurulamadıysa sekmeyi adresiyle açmayı dene: yarım
            # bir dinleyici uğruna sayfayı hiç açmamak kötü bir takas.
            geri = "/json/new?" + quote(url, safe=":/?&=%")
            try:
                made = self._http(geri, method="PUT")
            except Exception:
                made = self._http(geri)
            self.dinle(made, taze=True)
        made["url"] = url
        return made

    def close_tab(self, tab_id: str) -> None:
        if (kayit := self._kayitlar.pop(str(tab_id), None)) is not None:
            kayit.kapat()
        try:
            self._http(f"/json/close/{tab_id}")
        except Exception:
            pass

    # -- dinleyici -----------------------------------------------------

    def dinle(self, tab: dict[str, Any], *, taze: bool = False) -> Kayit:
        """Sekmeye kalıcı dinleyici bağlar; zaten varsa mevcut olanı verir.

        `taze=True` yeni bir sayfaya geçildiğini bildiriyor: eski sayfanın
        kayıtları temizleniyor ve "geç kaldım" bayrağı düşüyor.

        Dinleyici KURULAMAZSA ortalık yıkılmıyor — `Kayit.hata` doluyor ve
        araç bunu dürüstçe söylüyor. Sayfayı açamamak, sayfayı açıp konsolu
        dinleyememekten kötüdür.
        """
        kimlik = str(tab.get("id") or "")
        kayit = self._kayitlar.get(kimlik)
        if kayit is not None and kayit.calisiyor:
            if taze:
                kayit.temizle()
            return kayit
        if kayit is not None:
            kayit.kapat()

        spot = str(tab.get("webSocketDebuggerUrl") or "")
        if not spot:
            kayit = Kayit.__new__(Kayit)   # bağlantısız kabuk
            kayit.konsol, kayit.istekler = deque(), deque()
            kayit.hata = "sekmenin hata ayıklama adresi yok"
            kayit.eksik = True
            kayit._kapali = True
            kayit._wire = None
            self._kayitlar[kimlik] = kayit
            return kayit

        kayit = Kayit(spot)
        # Taze değilse sayfa çoktan yüklenmiş olabilir: baştaki mesajlar
        # kaçtı ve bunu saklamıyoruz.
        kayit.eksik = not taze
        self._kayitlar[kimlik] = kayit
        return kayit

    def kayit(self, tab: dict[str, Any]) -> Kayit:
        """Sekmenin dinleyicisi; yoksa şimdi kurulur (geç kalmış olarak)."""
        return self.dinle(tab)

    # -- sayfanın içi (ws) ---------------------------------------------

    def _call(self, tab: dict[str, Any], method: str, params: dict[str, Any]) -> dict[str, Any]:
        spot = tab.get("webSocketDebuggerUrl")
        if not spot:
            raise BrowseError("Sekmenin hata ayıklama adresi yok (başka istemci bağlı olabilir).")
        wire = Wire(str(spot))
        try:
            wire.send(json.dumps({"id": 1, "method": method, "params": params}))
            deadline = time.monotonic() + CALL_TIMEOUT_S
            while time.monotonic() < deadline:
                answer = json.loads(wire.recv())
                if answer.get("id") != 1:
                    continue  # olay bildirimi; bizim cevabımız değil
                if "error" in answer:
                    raise BrowseError(str(answer["error"].get("message") or "CDP hatası"))
                result = answer.get("result")
                return result if isinstance(result, dict) else {}
            raise BrowseError(f"Cevap gelmedi: {method}")
        finally:
            wire.close()

    def eval(self, tab: dict[str, Any], expression: str) -> Any:
        answer = self._call(tab, "Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        if "exceptionDetails" in answer:
            raise BrowseError(
                "Sayfa betiği hata verdi: "
                + str(answer["exceptionDetails"].get("text") or "")
            )
        return (answer.get("result") or {}).get("value")

    def read(self, tab: dict[str, Any], limit: int = 6000) -> dict[str, Any]:
        """Sayfanın görünen metni. Yüklenmesini kısa bir süre bekliyor.

        Yalnızca `readyState` yetmiyor: yeni açılan sekme bir an
        `about:blank` oluyor ve o sayfa anında "complete" — gezinme daha
        başlamadan boş sayfa okunuyordu. Adres de yerine oturmalı.
        """
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            state = self.eval(tab, "document.readyState")
            spot = str(self.eval(tab, "location.href") or "")
            if state == "complete" and spot not in ("", "about:blank"):
                break
            time.sleep(0.4)
        text = str(self.eval(
            tab, "document.body ? document.body.innerText : ''"
        ) or "").strip()
        title = str(self.eval(tab, "document.title") or "")
        spot = str(self.eval(tab, "location.href") or tab.get("url") or "")
        clipped = len(text) > limit
        return {
            "title": title,
            "url": spot,
            "text": text[:limit] + ("\n… (kırpıldı)" if clipped else ""),
            # Çerçeve hata sayfası — varsa ayrı alan. Metnin içinde kaybolan
            # bir "Whoops!" başlığı gözden kaçıyordu.
            "hata": self.hata_katmani(tab),
        }

    def hata_katmani(self, tab: dict[str, Any]) -> dict[str, Any] | None:
        """Sayfa bir çerçeve hata sayfası mı? Öyleyse özü, değilse None.

        Neden ayrı alan: CodeIgniter'ın "Whoops!", Django'nun sarı hata
        sayfası, Werkzeug'un yığın izi — hepsi `innerText` içinde SIRADAN
        metin olarak akıyor. Model uzun bir sayfa metninin ortasında
        istisna sınıfını fark etmeyip "sayfa açıldı" diyordu.

        Tespit kanıta dayalı: çerçevenin kendi imzası (DOM işareti ya da
        başlık deseni) aranıyor. Hiçbiri tutmuyorsa None — bir sayfayı
        "hata sayfası" diye yaftalamak, olmayan bir hatayı rapor etmektir.
        """
        try:
            bulgu = self.eval(tab, _HATA_JS)
        except BrowseError:  # pragma: no cover - sayfa okunamıyorsa sus
            return None
        return bulgu if isinstance(bulgu, dict) and bulgu.get("tur") else None

    def js(self, tab: dict[str, Any], ifade: str) -> dict[str, Any]:
        """Sayfada küçük bir ifade çalıştırır ve SONUCU döndürür (teşhis).

        Sonuç JSON'a çevrilebiliyorsa değeriyle, çevrilemiyorsa metin
        haliyle geliyor: bir DOM düğümü ya da fonksiyon `returnByValue`
        ile serileşmiyor ve çıplak çağrı orada patlıyordu.

        İfadenin kendi istisnası bir ARAÇ hatası değil, bir BULGUDUR:
        modele "şu satırda şu hata" diye dönüyor, çünkü sorduğu şey zaten
        buydu.
        """
        cevap = self.eval(tab, _JS_SARGI % json.dumps(ifade))
        if not isinstance(cevap, dict):  # pragma: no cover - sargı hep dict döner
            return {"tip": "?", "deger": cevap}
        if cevap.get("hata"):
            return {"tip": "hata", "deger": str(cevap["hata"])}
        return {"tip": str(cevap.get("tip") or "?"), "deger": cevap.get("deger")}

    def screenshot(self, tab: dict[str, Any]) -> str:
        """Görünen alanın görüntüsü, data: adresi olarak."""
        answer = self._call(tab, "Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 72,
        })
        data = str(answer.get("data") or "")
        if not data:
            raise BrowseError("Görüntü alınamadı.")
        return "data:image/jpeg;base64," + data

    # -- faz 2: sayfayla etkileşim -------------------------------------

    def navigate(self, tab: dict[str, Any], url: str) -> dict[str, Any]:
        """Aynı sekmede başka adrese gider ve yeni sayfayı okur."""
        # Dinleyici gezinmeden ÖNCE: yeni sayfanın ilk hatası da yakalansın.
        self.dinle(tab, taze=True)
        self._call(tab, "Page.navigate", {"url": url})
        return self.read(tab)

    def click(self, tab: dict[str, Any], text: str) -> str:
        """Metnine göre bir düğme ya da bağlantıya tıklar.

        Piksel değil metin: model "Giriş" düğmesini görüyor, koordinatını
        değil. Sayfadaki tıklanabilirler (buton, bağlantı, role=button,
        input) taranıyor ve metni en iyi eşleşen tıklanıyor. Görünmeyen
        eşleşme atlanıyor — gizli bir bağlantıya tıklamak işe yaramaz.
        """
        want = json.dumps(text)
        found = self.eval(tab, _CLICK_JS % want)
        if not found:
            raise BrowseError(
                f"'{text}' ile eşleşen tıklanabilir bir şey bulunamadı. "
                "`read` ile sayfadaki bağlantı/düğme metinlerine bak."
            )
        return str(found)

    def type(self, tab: dict[str, Any], text: str, into: str = "") -> str:
        """Bir alana metin yazar.

        `into` verilirse etiketine/placeholder'ına göre alan seçilir; boşsa
        o an odakta olan (ya da ilk boş metin) alan kullanılıyor. Yazma DOM'a
        doğrudan değil, gerçek tuş olaylarıyla: bazı sayfalar `input`
        olayını dinliyor ve doğrudan değer atamayı görmüyor.
        """
        focused = self.eval(tab, _FOCUS_JS % json.dumps(into))
        if not focused:
            raise BrowseError(
                (f"'{into}' alanı bulunamadı." if into else "Yazılacak bir alan bulunamadı.")
                + " `read` ile forma bak."
            )
        # Odaklı alana karakterleri gerçek tuş olayı olarak gönder.
        for ch in text:
            self._call(tab, "Input.dispatchKeyEvent", {"type": "keyDown", "text": ch})
            self._call(tab, "Input.dispatchKeyEvent", {"type": "keyUp", "text": ch})
        return str(focused)

    def press(self, tab: dict[str, Any], key: str) -> None:
        """Tek bir özel tuş: Enter, Tab, Escape…"""
        spec = _KEYS.get(key.lower())
        if spec is None:
            raise BrowseError(f"Bilinmeyen tuş: {key}. (Enter, Tab, Escape…)")
        for phase in ("keyDown", "keyUp"):
            self._call(tab, "Input.dispatchKeyEvent", {"type": phase, **spec})

    def fill(
        self,
        tab: dict[str, Any],
        text: str,
        *,
        selector: str = "",
        label: str = "",
        name: str = "",
        placeholder: str = "",
    ) -> str:
        """Bir form alanını bulur, temizler ve değeri yazar.

        `type`'tan farkı hedefli olması: alan CSS seçiciyle ya da görünen
        etiket / name / placeholder ile seçiliyor. Yazma doğrudan `value`
        ataması değil — çerçeveler (React vb.) yerli ayarlayıcı + `input`
        ve `change` olaylarını görmeden değeri saymıyor; sayfa içindeki
        yardımcı ikisini de yapıyor. Birden çok alan eşleşirse adaylar
        sayılarak hata dönüyor; sessizce yanlış alana yazılmıyor.
        """
        if not (selector or label or name or placeholder):
            raise BrowseError(
                "Alan belirt: `selector`, `label`, `name` ya da `placeholder` gerekli. "
                "`read` ile formdaki alanlara bak."
            )
        spec = json.dumps({
            "selector": selector, "label": label,
            "name": name, "placeholder": placeholder,
        })
        return _outcome(self.eval(tab, _FILL_JS % (spec, json.dumps(text))),
                        "Alan doldurulamadı.")

    def submit(self, tab: dict[str, Any], selector: str = "") -> str:
        """Formu gönderir.

        Seçici verilirse o form ya da düğme; verilmezse odaklı alanın formu,
        o da yoksa sayfadaki tek form. Gönderme düğmesi varsa tıklanıyor
        (sayfanın kendi akışı çalışsın); yoksa `requestSubmit` — o da
        `submit` olayını tetikliyor, çıplak `form.submit()` tetiklemezdi.
        """
        return _outcome(self.eval(tab, _SUBMIT_JS % json.dumps(selector)),
                        "Form gönderilemedi.")


def _outcome(answer: Any, fallback: str) -> str:
    """Sayfa yardımcılarının ortak sözleşmesi: {ok} ya da {err, adaylar}."""
    if not isinstance(answer, dict):
        raise BrowseError(fallback + " (Sayfa beklenmedik bir cevap verdi.)")
    if answer.get("err"):
        message = str(answer["err"])
        candidates = answer.get("adaylar") or []
        if candidates:
            message += " Adaylar: " + "; ".join(str(c) for c in candidates)
        raise BrowseError(message)
    return str(answer.get("ok") or "tamam")


# -- sayfa içinde çalışan yardımcılar -----------------------------------
#
# Tıklama ve alan seçimi sayfanın kendi DOM'unda çözülüyor: koordinat
# hesaplamak kırılgan (kaydırma, ölçek, gizli katman) ve model zaten metin
# düşünüyor — "Giriş düğmesi", "e-posta alanı". Eşleşme önce birebir, sonra
# içeren; görünmeyen aday atlanıyor.

_CLICK_JS = """(() => {
  const want = %s.trim().toLowerCase();
  const seen = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const nodes = [...document.querySelectorAll(
    "a,button,[role=button],input[type=submit],input[type=button],[onclick]")];
  const label = (el) => (
    el.innerText || el.value || el.getAttribute("aria-label") || el.title || ""
  ).trim().toLowerCase();
  let hit = nodes.find((el) => seen(el) && label(el) === want)
         || nodes.find((el) => seen(el) && label(el).includes(want));
  if (!hit) return "";
  hit.click();
  return (hit.innerText || hit.value || hit.getAttribute("aria-label") || "tıklandı").trim().slice(0, 80);
})()"""

_FOCUS_JS = """(() => {
  const want = %s.trim().toLowerCase();
  const seen = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !el.disabled && !el.readOnly;
  };
  const fields = [...document.querySelectorAll(
    "input:not([type=hidden]):not([type=submit]):not([type=button]),textarea,[contenteditable=true]")]
    .filter(seen);
  if (!fields.length) return "";
  let pick;
  if (want) {
    const near = (el) => {
      let t = (el.getAttribute("aria-label") || el.placeholder || el.name || el.id || "").toLowerCase();
      if (el.labels && el.labels.length) t += " " + el.labels[0].innerText.toLowerCase();
      return t;
    };
    pick = fields.find((el) => near(el).includes(want));
    if (!pick) return "";
  } else {
    pick = (document.activeElement && fields.includes(document.activeElement))
      ? document.activeElement
      : fields.find((el) => !el.value) || fields[0];
  }
  pick.focus();
  return (pick.getAttribute("aria-label") || pick.placeholder || pick.name || pick.id || "alan").slice(0, 80);
})()"""

# Alan bulma + doldurma da sayfa içinde. Sözleşme: {ok: "..."} ya da
# {err: "...", adaylar: [...]} döner — Python tarafı `_outcome` ile açıyor.
# Değer yazma yerli ayarlayıcıyla (React'in kendi value takibini aşmak için)
# ve ardından input+change olaylarıyla: çerçevelerin dinlediği yol bu.
# iframe içindeki formlara buradan ulaşılamıyor; hata mesajı bunu söylüyor.

_FILL_JS = """(() => { // dornick:fill
  const spec = %s;
  const text = %s;
  const desc = (el) => {
    const parts = [];
    if (el.labels && el.labels.length && el.labels[0].innerText.trim())
      parts.push(el.labels[0].innerText.trim());
    if (el.name) parts.push("name=" + el.name);
    if (el.placeholder) parts.push("placeholder=" + el.placeholder);
    if (!parts.length && el.id) parts.push("#" + el.id);
    if (!parts.length) parts.push(el.tagName.toLowerCase());
    return parts.join(" / ").slice(0, 80);
  };
  const seen = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !el.disabled && !el.readOnly;
  };
  const iframeNote = document.querySelector("iframe")
    ? " Sayfada iframe var; iframe içindeki formlar bu sürümde kapsam dışı." : "";
  let hits;
  if (spec.selector) {
    let found;
    try { found = [...document.querySelectorAll(spec.selector)]; }
    catch (e) { return {err: "Geçersiz CSS seçici: " + spec.selector}; }
    if (!found.length)
      return {err: "'" + spec.selector + "' hiçbir öğeyle eşleşmedi." + iframeNote};
    hits = found.filter((el) =>
      el.matches("input,textarea,select,[contenteditable=true],[contenteditable='']"));
    if (!hits.length)
      return {err: "'" + spec.selector + "' eşleşti ama doldurulabilir bir alan değil."};
  } else {
    const all = [...document.querySelectorAll(
      "input:not([type=hidden]):not([type=submit]):not([type=button]),textarea,select,[contenteditable=true]")]
      .filter(seen);
    let fields = all;
    const narrow = (want, get) => {
      const w = want.trim().toLowerCase();
      const exact = fields.filter((el) => get(el).trim().toLowerCase() === w);
      fields = exact.length
        ? exact
        : fields.filter((el) => get(el).toLowerCase().includes(w));
    };
    if (spec.label) narrow(spec.label, (el) => {
      let t = el.getAttribute("aria-label") || "";
      if (el.labels && el.labels.length) t = el.labels[0].innerText + " " + t;
      return t;
    });
    if (spec.name) narrow(spec.name, (el) => el.name || "");
    if (spec.placeholder) narrow(spec.placeholder, (el) => el.placeholder || "");
    if (!fields.length)
      return {err: "Eşleşen alan bulunamadı." + iframeNote,
              adaylar: all.map(desc).slice(0, 8)};
    hits = fields;
  }
  if (hits.length > 1)
    return {err: "Birden çok alan eşleşti; hedefi daralt.",
            adaylar: hits.map(desc).slice(0, 8)};
  const el = hits[0];
  if (!seen(el))
    return {err: "Alan bulundu ama görünür/etkin değil: " + desc(el)};
  el.focus();
  if (el.tagName === "SELECT") {
    const opt = [...el.options].find((o) => o.value === text || o.text.trim() === text);
    if (!opt) return {err: "Seçenek bulunamadı: " + text,
                      adaylar: [...el.options].map((o) => o.text.trim()).slice(0, 12)};
    el.value = opt.value;
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  } else if (el.isContentEditable) {
    el.textContent = text;
    el.dispatchEvent(new Event("input", {bubbles: true}));
  } else {
    const proto = el.tagName === "TEXTAREA"
      ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = (Object.getOwnPropertyDescriptor(proto, "value") || {}).set;
    if (setter) setter.call(el, text); else el.value = text;
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  }
  return {ok: desc(el)};
})()"""

_SUBMIT_JS = """(() => { // dornick:submit
  const sel = %s;
  const desc = (f) => {
    const parts = [];
    if (f.id) parts.push("#" + f.id);
    if (f.getAttribute("name")) parts.push("name=" + f.getAttribute("name"));
    if (f.getAttribute("action")) parts.push("→ " + f.getAttribute("action"));
    return parts.join(" ") || "form";
  };
  const fire = (form) => {
    const btn = form.querySelector(
      "button[type=submit],input[type=submit],button:not([type])");
    if (btn) {
      btn.click();
      return ((btn.innerText || btn.value || "").trim() || "düğme").slice(0, 60);
    }
    if (form.requestSubmit) form.requestSubmit(); else form.submit();
    return desc(form);
  };
  const iframeNote = document.querySelector("iframe")
    ? " Sayfada iframe var; iframe içindeki formlar bu sürümde kapsam dışı." : "";
  if (sel) {
    let el;
    try { el = document.querySelector(sel); }
    catch (e) { return {err: "Geçersiz CSS seçici: " + sel}; }
    if (!el) return {err: "'" + sel + "' bulunamadı." + iframeNote};
    if (el.tagName === "FORM") return {ok: fire(el)};
    if (el.matches("button,input[type=submit],input[type=button],[role=button]")) {
      el.click();
      return {ok: ((el.innerText || el.value || "").trim() || "düğme").slice(0, 60)};
    }
    if (el.form) return {ok: fire(el.form)};
    return {err: "'" + sel + "' bir form ya da düğme değil."};
  }
  const active = document.activeElement;
  let form = active && active.form ? active.form : null;
  if (!form) {
    const forms = [...document.forms];
    if (!forms.length) return {err: "Sayfada form yok." + iframeNote};
    if (forms.length > 1)
      return {err: "Birden çok form var; `selector` ile birini seç.",
              adaylar: forms.map(desc).slice(0, 8)};
    form = forms[0];
  }
  return {ok: fire(form)};
})()"""

# Teşhis ifadesinin sargısı. `eval` bilinçli: model bazen tek bir ifade
# değil iki satırlık bir yoklama gönderiyor ve düz `Runtime.evaluate`
# bunu sözdizimi hatası sayıyordu. Sonuç JSON'a çevrilemezse metne
# düşülüyor — DOM düğümü ve fonksiyon serileşmiyor.
_JS_SARGI = """(function () { // dornick:js
  let r;
  try { r = eval(%s); }
  catch (e) { return {hata: String((e && (e.stack || e.message)) || e)}; }
  const t = (r === null) ? "null" : typeof r;
  try { return {tip: t, deger: JSON.parse(JSON.stringify(r === undefined ? null : r))}; }
  catch (e) { return {tip: t, deger: String(r).slice(0, 2000)}; }
})()"""

# Çerçeve hata sayfalarının imzaları. Her madde gerçekten o çerçevenin
# ürettiği sayfada bulunan bir işaret; genel bir "sayfada 'error' geçiyor
# mu" taraması bilerek YOK — o, sıradan bir blog yazısını hata sayfası
# ilan ederdi.
_HATA_JS = """(() => { // dornick:hata
  const kes = (s, n) => (s || "").trim().replace(/\\s+/g, " ").slice(0, n || 300);
  const q = (s) => document.querySelector(s);
  const baslik = document.title || "";

  // CodeIgniter 4 — "Whoops!" başlığı, .header h1 istisna sınıfını taşır.
  if (q(".container.text-center h1") && /whoops/i.test(document.body.innerText.slice(0, 400))) {
    const h = q("h1"), p = q(".header p") || q("p");
    return {tur: "CodeIgniter 4 hata sayfası", baslik: kes(h && h.innerText, 200),
            mesaj: kes(p && p.innerText, 300),
            yer: kes((q(".source") || {}).innerText, 200)};
  }
  if (/whoops/i.test(baslik) || q("#exception-card") || q(".exception__message")) {
    const h = q(".exception__title, .exception-message, h1");
    return {tur: "PHP çerçeve hata sayfası (Whoops/Ignition)",
            baslik: kes(h && h.innerText, 200), mesaj: kes(baslik, 200), yer: ""};
  }
  // Django hata ayıklama sayfası: "TypeError at /yol"
  if (q("#summary") && q("#traceback") && / at \\//.test(baslik)) {
    const h = q("#summary h1"), p = q("#summary pre.exception_value");
    return {tur: "Django hata sayfası", baslik: kes(h && h.innerText, 200),
            mesaj: kes(p && p.innerText, 300), yer: ""};
  }
  // Flask/Werkzeug hata ayıklayıcı
  if (/werkzeug debugger/i.test(baslik) || q(".traceback .frame")) {
    const h = q("h1"), p = q(".errormsg") || q(".detail .errormsg");
    return {tur: "Werkzeug (Flask) hata ayıklayıcı", baslik: kes(h && h.innerText, 200),
            mesaj: kes(p && p.innerText, 300), yer: ""};
  }
  // Çıplak PHP: gövdenin başında "Fatal error:" / "Parse error:" / "Warning:"
  const bas = (document.body ? document.body.innerText : "").slice(0, 500);
  const m = bas.match(/(Fatal error|Parse error|Warning|Notice|Deprecated):\\s*([^\\n]+)/);
  if (m) return {tur: "PHP " + m[1], baslik: kes(m[1], 60), mesaj: kes(m[2], 300),
                 yer: kes((bas.match(/ in (.+ on line \\d+)/) || [])[1], 200)};
  // Node/Express varsayılan hata sayfası
  if (q("pre") && /^\\s*(Error|TypeError|ReferenceError):/.test(q("pre").innerText || ""))
    return {tur: "Node/Express hata sayfası", baslik: kes(q("pre").innerText.split("\\n")[0], 200),
            mesaj: "", yer: ""};
  return null;
})()"""

# Özel tuşlar için CDP anahtar tanımları.
_KEYS = {
    "enter": {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
    "tab": {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
    "escape": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    "esc": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    "backspace": {"key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
}
