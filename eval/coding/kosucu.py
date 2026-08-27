"""Kodlama ölçüm koşucusu: görevleri gerçek ajana verir, karneyi çıkarır.

Akış (görev başına, sırayla):

    geçici alan kur → tohumu kopyala → İZOLE neo örneği başlat
    → dış kapıdan (POST /api/gate) ham istemi ver → tur bitene kadar bekle
    → örneği kapat → atölyeyi puanla → oturum günlüğünden davranışı çıkar

Her görev kendi geçici çalışma alanında ve kendi neo örneğinde koşuyor
(bkz. `ornek.py`): kullanıcının zihni, atölyesi ve açık uygulaması
etkilenmiyor; görevler de birbirinin artığını görmüyor.

Kullanım:

    py eval/coding/kosucu.py --gorev k1-modul,k2-cli
    py eval/coding/kosucu.py --zorluk kolay,orta --tekrar 1
    py eval/coding/kosucu.py --gorev hepsi --model openai/gpt-5.6-luna

Parametreler:
    --gorev    virgüllü görev adı listesi ("hepsi" = tümü)
    --zorluk   kolay/orta/zor süzgeci
    --model    modeli EZER (verilmezse kullanıcının config.json'ındaki model
               olduğu gibi kullanılır — ölçüm ayarı değiştirmez)
    --tekrar   her görev kaç kez koşulsun (gürültü ölçmek için)
    --bekle    bir turun azami süresi (saniye)
    --sakla    geçici çalışma alanlarını silme (hata ayıklamak için)
    --onceki   önceki bir sonuç JSON'u; yeniden koşulmayan görevler oradan
               devralınır. Tek bir görevi (gürültülü çıkan, ya da ölçümü
               dışarıdan bozulan bir görevi) yeniden koşup raporu BÜTÜN
               halinde üretmek için. Devralınan satır raporda `†` ile
               işaretlenir — hangi rakamın hangi koşudan geldiği gizlenmez.

Çıktı: `sonuclar/<zaman>-<model>.json` + insan-okur `sonuclar/RAPOR.md`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BURASI = Path(__file__).resolve().parent
KOK = BURASI.parents[1]
sys.path.insert(0, str(BURASI))
sys.path.insert(0, str(KOK / "src"))

import davranis  # noqa: E402
import puanla  # noqa: E402
from puanla import Karne  # noqa: E402

GOREVLER_DIZINI = BURASI / "gorevler"
SONUC_DIZINI = BURASI / "sonuclar"

# Örneğin açılması için verilen süre. Model ısınması ve yetenek yüklemesi
# saniyeler sürüyor; indirilecek bir şey varsa daha da.
ACILIS_SN = 180.0
VARSAYILAN_BEKLE = 900.0

# Kullanıcının açık neo'suyla (8765) ve tarayıcı kapısıyla (9222) çakışmasın.
PORT_TABANI = 8791
TARAYICI_PORT_TABANI = 9333


# -- görev keşfi --------------------------------------------------------


class Gorev:
    """Diskteki bir görev klasörü: ham istem + puanlayıcı + tohum."""

    def __init__(self, klasor: Path) -> None:
        self.klasor = klasor
        self.ad = klasor.name
        self.istem = (klasor / "gorev.md").read_text(encoding="utf-8").strip()
        self.tohum = klasor / "tohum"
        self._modul = self._yukle()

    def _yukle(self) -> Any:
        yol = self.klasor / "olcut.py"
        spec = importlib.util.spec_from_file_location(f"olcut_{self.ad}", yol)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"puanlayıcı yüklenemedi: {yol}")
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return modul

    @property
    def baslik(self) -> str:
        return getattr(self._modul, "BASLIK", self.ad)

    @property
    def zorluk(self) -> str:
        return getattr(self._modul, "ZORLUK", "?")

    @property
    def dil(self) -> str:
        return getattr(self._modul, "DIL", "?")

    def olc(self, atolye: Path) -> list[puanla.Eksen]:
        return self._modul.olc(atolye)


def gorevleri_bul() -> list[Gorev]:
    return [Gorev(p) for p in sorted(GOREVLER_DIZINI.iterdir())
            if p.is_dir() and (p / "gorev.md").is_file()
            and (p / "olcut.py").is_file()]


# -- izole alan ---------------------------------------------------------


def bos_port(taban: int) -> int:
    for port in range(taban, taban + 200):
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("boş port bulunamadı")


def alan_kur(gorev: Gorev, kaynak_durum: Path, model: str | None,
             tarayici_port: int) -> Path:
    """Geçici çalışma alanı: kendi `.neocp`'si, kendi atölyesi, kendi ayarı."""
    alan = Path(tempfile.mkdtemp(prefix=f"neocp-eval-{gorev.ad}-"))
    durum = alan / ".neocp"
    durum.mkdir(parents=True, exist_ok=True)
    atolye = alan / "atolye"
    atolye.mkdir(parents=True, exist_ok=True)

    if gorev.tohum.is_dir():
        shutil.copytree(gorev.tohum, atolye, dirs_exist_ok=True)

    # Kullanıcının ayarı DEĞİŞTİRİLMİYOR, kopyalanıyor. Model olduğu gibi
    # geliyor; yalnız ölçümü bozacak ya da kullanıcının makinesine dokunacak
    # şeyler kapatılıyor (ses, kulak, kamera, konum) ve tarayıcı kapısı
    # kaydırılıyor.
    ayar: dict[str, Any] = {}
    kaynak_ayar = kaynak_durum / "config.json"
    if kaynak_ayar.is_file():
        try:
            ayar = json.loads(kaynak_ayar.read_text(encoding="utf-8"))
        except ValueError:
            ayar = {}
    if model:
        ayar.setdefault("model", {})["name"] = model
    ayar["voice"] = {"enabled": False}
    ayar["listen"] = {"enabled": False}
    ayar["camera"] = {"enabled": False}
    ayar["place"] = {"enabled": False}
    ayar.setdefault("browser", {})["port"] = tarayici_port
    # Ölçüm sırasında onay penceresi diye bir şey yok: tur onayda asılı
    # kalırsa ölçtüğümüz şey ajan değil, bekleme olur.
    ayar["permissions"] = {"mode": "yolo", "allow": [], "deny": []}
    (durum / "config.json").write_text(
        json.dumps(ayar, ensure_ascii=False, indent=2), encoding="utf-8")

    # Anahtarlar: kopyalanmadan model konuşamaz.
    kaynak_anahtar = kaynak_durum / "keys.json"
    if kaynak_anahtar.is_file():
        shutil.copyfile(kaynak_anahtar, durum / "keys.json")
    # Fiyat tablosu önbelleği: maliyet raporu ağa çıkmadan hesaplansın.
    kaynak_fiyat = kaynak_durum / "fiyat.json"
    if kaynak_fiyat.is_file():
        shutil.copyfile(kaynak_fiyat, durum / "fiyat.json")

    # Dış kapı açık gelsin — ölçümün tek konuşma yolu bu.
    (durum / "gate.json").write_text(json.dumps({"on": True}), encoding="utf-8")
    return alan


class Ornek:
    """İzole neo örneği (alt süreç). `with` bloğu bitince temizce kapanır."""

    def __init__(self, alan: Path, port: int) -> None:
        self.alan = alan
        self.port = port
        self.surec: subprocess.Popen[str] | None = None
        self.url = ""
        self.oturum = ""
        self.gunluk: list[str] = []
        self.hata = ""
        self._bosaltici: threading.Thread | None = None

    def __enter__(self) -> "Ornek":
        argv = [sys.executable, str(BURASI / "ornek.py"),
                "--alan", str(self.alan), "--port", str(self.port)]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        env.pop("NEOCP_WORKSPACE", None)
        env["NEOCP_STATE_DIR"] = str(self.alan / ".neocp")
        self.surec = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=str(KOK))
        son = time.time() + ACILIS_SN
        while time.time() < son:
            satir = self.surec.stdout.readline() if self.surec.stdout else ""
            if not satir:
                if self.surec.poll() is not None:
                    self.hata = "örnek süreci açılışta öldü"
                    break
                continue
            self.gunluk.append(satir.rstrip())
            print(f"    | {satir.rstrip()}", flush=True)
            if satir.startswith("HAZIR "):
                parcalar = satir.split()
                self.url = parcalar[1] if len(parcalar) > 1 else ""
                for p in parcalar[2:]:
                    if p.startswith("oturum="):
                        self.oturum = p.split("=", 1)[1]
                break
            if satir.startswith("PATLADI "):
                self.hata = satir.strip()
                break
        else:
            self.hata = f"örnek {ACILIS_SN:.0f} sn'de hazır olmadı"
        self._bosalt()
        return self

    def _bosalt(self) -> None:
        """Açılıştan sonra çocuğun stdout'unu sürekli boşaltır.

        Boşaltılmazsa boru dolduğunda çocuk `print` üzerinde BLOKLANIR ve tur
        sessizce donar — neo tur boyunca `[neo] ...` satırları basıyor,
        onbeş dakikalık bir turda 64 KB'lik boru rahat doluyor.
        """
        if self.surec is None or self.surec.stdout is None:
            return

        def dongu() -> None:
            try:
                for satir in self.surec.stdout:  # type: ignore[union-attr]
                    self.gunluk.append(satir.rstrip())
                    del self.gunluk[:-400]
            except Exception:
                pass

        self._bosaltici = threading.Thread(target=dongu, daemon=True,
                                           name="neo-eval-log")
        self._bosaltici.start()

    def sor(self, metin: str, bekle_sn: float) -> dict[str, Any]:
        """Dış kapıdan ham istemi verir ve turun tüm çıktısını döndürür."""
        if not self.url and self.hata:
            return {"ok": False, "error": self.hata}
        govde = json.dumps({"text": metin, "bekle_sn": bekle_sn}).encode("utf-8")
        istek = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/gate", data=govde,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(istek, timeout=bekle_sn + 90) as yanit:
                return json.loads(yanit.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def __exit__(self, *_: Any) -> None:
        if self.surec is None:
            return
        try:
            if self.surec.stdin:
                self.surec.stdin.write("dur\n")
                self.surec.stdin.flush()
        except Exception:
            pass
        try:
            self.surec.wait(timeout=25)
        except subprocess.TimeoutExpired:
            self.surec.kill()
        if self._bosaltici is not None:
            self._bosaltici.join(timeout=5)


# -- tek koşu -----------------------------------------------------------


def bir_kosu(gorev: Gorev, kaynak_durum: Path, model: str | None,
             bekle_sn: float, sakla: bool) -> Karne:
    port = bos_port(PORT_TABANI)
    tarayici = bos_port(TARAYICI_PORT_TABANI)
    alan = alan_kur(gorev, kaynak_durum, model, tarayici)
    atolye = alan / "atolye"
    notlar: list[str] = []
    kapi: dict[str, Any] = {}

    print(f"  alan: {alan}  port: {port}", flush=True)
    basladi = time.time()
    try:
        with Ornek(alan, port) as ornek:
            if ornek.hata:
                notlar.append(f"örnek açılmadı: {ornek.hata}")
                notlar.extend(ornek.gunluk[-6:])
                onceki: dict[str, str] = {}
            else:
                # Tur BAŞLAMADAN önce: açılışta atölyeye ne kondu?
                onceki = parmak_izi(atolye)
                kapi = ornek.sor(gorev.istem, bekle_sn)
                if not kapi.get("ok"):
                    notlar.append(f"dış kapı: {kapi.get('error')}")
            oturum_id = kapi.get("oturum") or ornek.oturum

        sayi = haric_yaz(atolye, onceki)
        if sayi:
            notlar.append(f"ölçüm dışı (dokunulmamış tur öncesi dosya): {sayi}")

        gunluk_yolu = alan / ".neocp" / "sessions" / f"{oturum_id}.jsonl"
        d = davranis.cikar(
            gunluk_yolu, kapi=kapi,
            model_adi=(model or _model_adi(kaynak_durum)),
            durum_dizini=alan / ".neocp")
        d["duvar_saati_sn"] = round(time.time() - basladi, 1)

        try:
            eksenler = gorev.olc(atolye)
        except Exception as exc:  # puanlayıcı patlarsa sıfır uydurmuyoruz
            notlar.append(f"puanlayıcı patladı: {type(exc).__name__}: {exc}")
            eksenler = [puanla.Eksen(ad, tavan, None, [],
                                     sebep="puanlayıcı patladı")
                        for ad, tavan in puanla.EKSENLER.items()]
        return Karne(gorev.ad, eksenler, d, notlar)
    finally:
        artik = alani_bosalt(alan)
        if artik:
            print(f"  (turdan sonra {artik} süreç kalmıştı, kapatıldı)",
                  flush=True)
        if sakla:
            print(f"  (alan saklandı: {alan})", flush=True)
        else:
            shutil.rmtree(alan, ignore_errors=True)


def alani_bosalt(alan: Path) -> int:
    """Bu çalışma alanına bağlı kalan süreçleri kapatır; sayısını döndürür.

    Örnek kapanınca neo'nun kendisi iniyor ama arkasında bıraktıkları
    inmiyordu: ajanın başlattığı `php -S`, `node`, ve neo'nun kendi Chrome'u
    (`kapat()` yalnız DevTools bağlantısını kapatıyor, süreci değil — üründe
    bilerek, çünkü oturumlar sıcak kalsın). Ölçümde bunun iki bedeli vardı:
    tutulu port yüzünden bir görev SAHTE 100.0 aldı, ve profil klasörü
    silinemediği için Temp'te 18 süreçlik çöp birikti.

    Ölçüt komut satırında bu alanın yolunun geçmesi. Yol benzersiz bir geçici
    dizin olduğu için kullanıcının kendi Chrome'u ya da sunucusu asla
    eşleşmez. Windows dışında sessizce hiçbir şey yapmıyor.
    """
    if sys.platform != "win32":
        return 0
    desen = str(alan).replace("'", "''")
    # `$_.ProcessId -ne $PID`: sorguyu koşan powershell'in KENDİ komut satırı
    # da bu yolu taşıyor — dışlanmazsa ilk kurbanı kendisi olur ve sayı hiç
    # yazılmaz.
    betik = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        f"$_.CommandLine -like '*{desen}*' -and $_.ProcessId -ne $PID }}; "
        "$p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
        "-ErrorAction SilentlyContinue }; "
        "($p | Measure-Object).Count"
    )
    try:
        cikti = subprocess.run(
            ["powershell", "-NoProfile", "-Command", betik],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        ).stdout.strip()
        return int(cikti or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0  # temizlik yapılamadıysa ölçüm yine de raporlanmalı


def parmak_izi(kok: Path) -> dict[str, str]:
    """Atölyedeki her dosyanın içerik özeti (göreli POSIX yol → sha1)."""
    import hashlib

    cikan: dict[str, str] = {}
    for dizin, altlar, dosyalar in os.walk(kok):
        altlar[:] = [d for d in altlar if d not in puanla.ATLA_KLASOR]
        for ad in dosyalar:
            yol = Path(dizin) / ad
            try:
                cikan[yol.relative_to(kok).as_posix()] = hashlib.sha1(
                    yol.read_bytes()).hexdigest()
            except OSError:
                continue
    return cikan


def haric_yaz(kok: Path, onceki: dict[str, str]) -> int:
    """Ajanın DOKUNMADIĞI, tur öncesinden kalma dosyaları ölçüm dışına alır.

    Atölyede tur başlamadan da dosya var: neo'nun açılışta kopyaladığı
    standart yetenekler ve görevin tohumu. Bunlar ajanın eseri değil ve kod
    sağlığı puanını kirletiyorlardı (ölçüldü: ilk koşuda karmaşıklık cezası
    tümüyle `yetenekler/pdf_uret.py`'den geliyordu). Ajan bir tohum dosyasını
    DÜZENLEDİYSE özeti değişir ve dosya ölçümde kalır — tamir görevlerinin
    ölçülmesi buna bağlı.
    """
    simdiki = parmak_izi(kok)
    haric = sorted(yol for yol, ozet in onceki.items()
                   if simdiki.get(yol) == ozet)
    (kok / puanla.HARIC_DOSYA).write_text(
        json.dumps(haric, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(haric)


def _model_adi(durum: Path) -> str:
    try:
        veri = json.loads((durum / "config.json").read_text(encoding="utf-8"))
        return str((veri.get("model") or {}).get("name") or "")
    except (OSError, ValueError):
        return ""


# -- rapor --------------------------------------------------------------


def _sayi(x: float | None, kalip: str = "{:.1f}") -> str:
    return "—" if x is None else kalip.format(x)


def rapor_yaz(sonuc: dict[str, Any], yol: Path) -> None:
    s: list[str] = []
    zaman = sonuc["zaman"]
    s.append("# Kodlama Ölçüm Raporu")
    s.append("")
    s.append(f"**Koşu:** {zaman} · **Model:** `{sonuc['model']}` · "
             f"**Tekrar:** {sonuc['tekrar']} · "
             f"**Düzenek:** `eval/coding/` (dış kapı + izole örnek)")
    s.append("")
    s.append("Puan dört eksenden: **çalışır mı** 40 · **istenen kapsam** 25 · "
             "**kod sağlığı** 20 · **test kalitesi** 15. Bir eksen ölçülemediyse "
             "paydadan da düşer; istem o işi istemiyorsa (*istenmedi*) ölçülür "
             "ama puana katılmaz. Puan sütunu 100'e normalize edilmiş haldir.")
    s.append("")

    # -- ana tablo
    s.append("## Puan kırılımı")
    s.append("")
    s.append("| görev | zorluk | dil | çalışır (40) | kapsam (25) | sağlık (20) "
             "| test (15) | **puan** |")
    s.append("|---|---|---|---|---|---|---|---|")
    for satir in sonuc["gorevler"]:
        k = satir["ozet"]
        hucre = []
        for ad in ("calisir", "kapsam", "saglik", "test"):
            e = next((x for x in k["eksenler"] if x["ad"] == ad), None)
            if e is None:
                hucre.append("—")
            elif e["alinan"] is None:
                hucre.append("ölçülemedi")
            else:
                etiket = f"{e['alinan']:.1f}"
                hucre.append(f"{etiket}*" if e["harici"] else etiket)
        puan = k["puan"]
        pd = "ölçülemedi" if puan is None else f"**{puan:.1f}**"
        if satir.get("puan_sapma") is not None and sonuc["tekrar"] > 1:
            pd += f" ±{satir['puan_sapma']:.1f}"
        ad = satir["ad"] + ("†" if satir.get("devralindi") else "")
        s.append(f"| {ad} | {satir['zorluk']} | {satir['dil']} | "
                 + " | ".join(hucre) + f" | {pd} |")
    s.append("")
    s.append("`*` = istem bu işi istemedi; ölçüldü, raporlanıyor, puana katılmıyor.")
    devralinan = {s2["ad"]: s2["devralindi"] for s2 in sonuc["gorevler"]
                  if s2.get("devralindi")}
    if devralinan:
        s.append("`†` = bu satır bu koşudan değil, önceki bir koşudan devralındı: "
                 + ", ".join(f"{k} ({v})" for k, v in sorted(devralinan.items()))
                 + ".")
    s.append("")

    # -- davranış tablosu
    s.append("## Davranış ölçütleri (puana katılmaz)")
    s.append("")
    s.append("| görev | tur bitti | araç çağrısı | hatalı araç | süre sn "
             "| token (giren/çıkan) | maliyet $ | kendini doğruladı | plan yazdı "
             "| bozuk teslim |")
    s.append("|---|---|---|---|---|---|---|---|---|---|")
    for satir in sonuc["gorevler"]:
        d = satir["ozet"].get("davranis") or {}
        if d.get("cikarilamadi"):
            s.append(f"| {satir['ad']} | " + " | ".join(["çıkarılamadı"] * 9) + " |")
            continue
        token = (f"{d.get('token_prompt_toplam') or '—'}/"
                 f"{d.get('token_cikti') or '—'}")
        # Tur bitmeden puanlanan atölye YARIM olabilir; okuyan bunu bilmeli.
        bitti = "evet" if d.get("kapi_ok") else "**HAYIR**"
        s.append(
            f"| {satir['ad']} | {bitti} | {d.get('arac_cagrisi', '—')} | "
            f"{d.get('hatali_arac', '—')} | {_sayi(d.get('sure_sn'))} | {token} | "
            f"{_sayi(d.get('maliyet_usd'), '{:.4f}')} | "
            f"{'evet' if d.get('dogruladi_mi') else 'hayır'} | "
            f"{'evet' if d.get('plan_yazdi_mi') else 'hayır'} | "
            f"{satir.get('bozuk_teslim', 0)}/{sonuc['tekrar']} |")
    s.append("")
    yarim = [g["ad"] for g in sonuc["gorevler"]
             if not (g["ozet"].get("davranis") or {}).get("kapi_ok")]
    if yarim:
        s.append(f"**Turu bitmeden puanlanan görevler:** {', '.join(yarim)}. "
                 "Bu satırlardaki puan ajanın BİTMİŞ işini değil, süre dolduğunda "
                 "atölyede ne varsa onu ölçüyor — aşağı yönlü sapmalıdır.")
        s.append("")

    olculdu = [g["ozet"]["puan"] for g in sonuc["gorevler"]
               if g["ozet"]["puan"] is not None]
    if olculdu:
        s.append(f"**Ortalama puan:** {sum(olculdu) / len(olculdu):.1f}/100 "
                 f"({len(olculdu)} görev ölçüldü)")
        s.append("")
    if sonuc.get("kosulmayan"):
        s.append("**Koşulmadı:** " + ", ".join(sonuc["kosulmayan"]))
        s.append("")

    # -- gürültü uyarısı: rakamı okuyan bunu görmeden okumasın
    s.append("## Bu sayılar ne kadar sağlam?")
    s.append("")
    if sonuc["tekrar"] < 2:
        s.append("**Tek koşu gürültüdür.** Buradaki her puan tek atıştan geliyor; "
                 "aynı görev aynı modelle yeniden koşulduğunda birkaç puan "
                 "oynayabilir, bazı görevlerde (araç hatası, zaman aşımı) çok "
                 "daha fazla. Bir iyileştirmenin işe yaradığını söylemek için "
                 "`--tekrar 3` ile koşup ± aralığına bakmak gerekiyor. Tek "
                 "koşudaki büyük fark (>15 puan) anlamlı, küçük fark (<5 puan) "
                 "gürültüden ayırt edilemez.")
    else:
        s.append(f"Her görev {sonuc['tekrar']} kez koşuldu; puan sütunundaki ± "
                 "koşular arası yayılımdır (min-maks yarı genişliği). Yayılımdan "
                 "küçük farklar iyileştirme sayılmaz.")
    s.append("")
    s.append("İzolasyon: her koşu kendi geçici çalışma alanında, **boş bir "
             "zihinle** ve kendi neo örneğiyle yapıldı. Kullanıcının anıları "
             "taşınmıyor — yani bu düzenek kodlama boru hattını ölçüyor, "
             "hafızanın kodlamaya katkısını ölçmüyor.")
    s.append("")

    # -- görev görev kanıt
    s.append("## Kanıt dökümü")
    s.append("")
    for satir in sonuc["gorevler"]:
        s.append(f"### {satir['ad']} — {satir['baslik']}")
        s.append("")
        for e in satir["ozet"]["eksenler"]:
            etiket = puanla.EKSEN_BASLIK.get(e["ad"], e["ad"])
            if e["alinan"] is None:
                s.append(f"- **{etiket}: ölçülemedi** — {e['sebep']}")
            else:
                ek = " *(istenmedi)*" if e["harici"] else ""
                s.append(f"- **{etiket}: {e['alinan']:.1f}/{e['tavan']}**{ek}")
            for kanit in e["kanit"]:
                s.append(f"  - `{kanit}`")
        d = satir["ozet"].get("davranis") or {}
        if d.get("dogrulama_izi"):
            s.append(f"- doğrulama izi: " +
                     "; ".join(f"`{x}`" for x in d["dogrulama_izi"][:4]))
        if d.get("araclar"):
            s.append(f"- araçlar: " +
                     ", ".join(f"{k}×{v}" for k, v in d["araclar"].items()))
        for notu in satir["ozet"].get("notlar") or []:
            s.append(f"- ! {notu}")
        s.append("")

    yol.write_text("\n".join(s), encoding="utf-8")


# -- ana ----------------------------------------------------------------


def _onceki_oku(yol: Path) -> tuple[dict[str, Any] | None, str]:
    """Devir dosyasını okur. Klasör verilirse en yeni sonuç JSON'unu seçer.

    Dönen ikili: (içerik, hata). Hata boş değilse koşuya hiç başlanmamalı.
    """
    if yol.is_dir():
        adaylar = [y for y in yol.glob("*.json") if y.is_file()]
        if not adaylar:
            return None, f"önceki sonuç yok: {yol} içinde .json bulunamadı"
        # Ada değil yazılma zamanına göre: klasöre elle konmuş bir dosya
        # ada göre sıralamada en sona düşüp yanlışlıkla seçilebiliyordu.
        yol = max(adaylar, key=lambda y: y.stat().st_mtime)
        print(f"devir dosyası: {yol.name}")
    try:
        icerik = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"önceki sonuç okunamadı: {exc}"
    if not isinstance(icerik, dict) or "gorevler" not in icerik:
        return None, f"önceki sonuç bir koşu dosyası değil: {yol}"
    return icerik, ""


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--gorev", default="hepsi")
    a.add_argument("--zorluk", default="")
    a.add_argument("--model", default="")
    a.add_argument("--tekrar", type=int, default=1)
    a.add_argument("--bekle", type=float, default=VARSAYILAN_BEKLE)
    a.add_argument("--sakla", action="store_true")
    a.add_argument("--durum", default="",
                   help="ayar/anahtar kaynağı (varsayılan: deponun .neocp'si)")
    a.add_argument("--onceki", default="",
                   help="önceki bir sonuç JSON'u (ya da sonuç klasörü: en "
                        "yenisi seçilir): yeniden koşulmayan görevler oradan "
                        "taşınır — tek bir görevi yeniden koşup raporu bütün "
                        "halinde üretmek için")
    args = a.parse_args(argv)

    kaynak_durum = Path(args.durum) if args.durum else (KOK / ".neocp")
    if not (kaynak_durum / "config.json").is_file():
        print(f"ayar bulunamadı: {kaynak_durum / 'config.json'}")
        return 2

    # Devir dosyası KOŞUDAN ÖNCE okunuyor. Sonda okumak, saatler süren ve
    # para harcayan bir koşunun sonunda "yol yanlış" deyip her şeyi
    # çöpe atmak demekti.
    eski: dict[str, Any] | None = None
    if args.onceki:
        eski, hata = _onceki_oku(Path(args.onceki))
        if hata:
            print(hata)
            return 2

    hepsi = gorevleri_bul()
    secili = hepsi
    if args.zorluk:
        istenen = {z.strip() for z in args.zorluk.split(",") if z.strip()}
        secili = [g for g in secili if g.zorluk in istenen]
    if args.gorev and args.gorev != "hepsi":
        adlar = {g.strip() for g in args.gorev.split(",") if g.strip()}
        secili = [g for g in secili if g.ad in adlar]
    if not secili:
        print("seçilen görev yok")
        return 2

    model = args.model or _model_adi(kaynak_durum)
    zaman = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"kodlama ölçümü · model {model} · {len(secili)} görev × "
          f"{args.tekrar} tekrar\n")

    satirlar: list[dict[str, Any]] = []
    for gorev in secili:
        print(f"[{gorev.ad}] {gorev.baslik} ({gorev.zorluk}/{gorev.dil})",
              flush=True)
        karneler: list[Karne] = []
        for tur in range(args.tekrar):
            if args.tekrar > 1:
                print(f"  tur {tur + 1}/{args.tekrar}", flush=True)
            karneler.append(bir_kosu(gorev, kaynak_durum, args.model or None,
                                     args.bekle, args.sakla))
        puanlar = [k.puan for k in karneler if k.puan is not None]
        sapma = ((max(puanlar) - min(puanlar)) / 2) if len(puanlar) > 1 else None
        # Rapora giren tek karne: MEDYAN değil ilk koşu — ortalama bir karne
        # diye bir şey yok, kanıt dökümü gerçek bir koşuya ait olmalı.
        satirlar.append({
            "ad": gorev.ad, "baslik": gorev.baslik, "zorluk": gorev.zorluk,
            "dil": gorev.dil,
            "ozet": karneler[0].sozluk(),
            "tum_puanlar": puanlar,
            "puan_sapma": sapma,
            "bozuk_teslim": sum(1 for k in karneler if k.bozuk_teslim),
        })
        p = karneler[0].puan
        print(f"  → {'ölçülemedi' if p is None else f'{p:.1f}/100'}"
              + (f"  (tüm turlar: {[round(x, 1) for x in puanlar]})"
                 if len(puanlar) > 1 else "") + "\n", flush=True)

    # Önceki koşudan devralma: bir görevi yeniden koşup raporu BÜTÜN halinde
    # üretmenin yolu. Devralınan satırlar `devralindi` ile işaretleniyor —
    # rapordaki tablonun hangi satırının bu koşudan geldiği gizlenmemeli.
    for satir in satirlar:
        satir["devralindi"] = ""
    if eski is not None:
        taze = {s["ad"] for s in satirlar}
        devir = [dict(s, devralindi=eski.get("zaman", "?"))
                 for s in eski.get("gorevler", []) if s["ad"] not in taze]
        satirlar = sorted(satirlar + devir, key=lambda s: s["ad"])
        if devir:
            print(f"önceki koşudan devralındı: "
                  f"{', '.join(s['ad'] for s in devir)}")

    kosuldu = {s["ad"] for s in satirlar}
    kosulmayan = [g.ad for g in hepsi if g.ad not in kosuldu]
    sonuc = {
        "zaman": zaman, "model": model, "tekrar": args.tekrar,
        "bekle_sn": args.bekle, "gorevler": satirlar,
        "kosulmayan": kosulmayan,
        "eksen_tavanlari": puanla.EKSENLER,
    }

    SONUC_DIZINI.mkdir(parents=True, exist_ok=True)
    guvenli = re.sub(r"[^\w.-]+", "-", model or "model")
    (SONUC_DIZINI / f"{zaman}-{guvenli}.json").write_text(
        json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
    rapor_yaz(sonuc, SONUC_DIZINI / "RAPOR.md")
    print(f"sonuç: {SONUC_DIZINI / f'{zaman}-{guvenli}.json'}")
    print(f"rapor: {SONUC_DIZINI / 'RAPOR.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
