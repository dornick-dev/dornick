"""Kancalar: kullanıcının kendi komutlarını araç yaşam döngüsüne takması.

Neden var: Dornick'in ne yapıp ne yapmayacağı iki yerden belirleniyordu —
sistem promptu (modeli İKNA eder) ve izin motoru (araç adı ve argümanına
bakar). İkisinin arasında bir boşluk var: "bu depoda `main` dalına asla
yazma", "her Python dosyası yazıldıktan sonra `black` çalıştır", "üretim
yapılandırmasına dokunulacaksa önce beni uyar". Bunlar kullanıcının kendi
kuralları ve hiçbiri prompta ya da izin desenine sığmıyor.

Kanca bu boşluğu dolduruyor: kullanıcı `.dornick/kancalar.json` dosyasına
kendi komutunu yazıyor, komut aracın önünde ya da arkasında koşuyor.

    [
      {"olay": "arac_oncesi", "arac": "write_file",
       "komut": "py .dornick/koru.py", "zaman_asimi": 10},
      {"olay": "arac_sonrasi", "arac": "write_file|edit_file",
       "komut": "black -q \\"%DORNICK_YOL%\\" && echo bicimlendirildi"}
    ]

`arac_oncesi` VETO yetkisine sahiptir: komut sıfırdan farklı bir çıkış
koduyla dönerse araç hiç çalışmaz ve komutun çıktısı modele gerekçe olarak
gider. `arac_sonrasi` yalnızca bilgilendirir; çıktısı araç sonucuna tek
satır olarak eklenir.

GÜVENLİK — bilinçli iki karar ve gerekçeleri:

  1. **Kancalar izin motorunun DIŞINDA çalışır.** Onay penceresi çıkmaz,
     `plan` kipinde bile koşarlar. Bu bir gözden kaçırma değil: kanca
     kullanıcının KENDİ komutudur, kendi diskindeki kendi dosyasına kendi
     eliyle yazmıştır. Ona her seferinde "kendi kuralını çalıştırayım mı?"
     diye sormak, kuralı işe yaramaz hale getirirdi — hele ki kuralın işi
     modeli engellemekse.
  2. **Model kancaları DEĞİŞTİREMEZ.** Birinci karar ancak bununla
     güvenli: dosyayı model yazabilseydi, kendisini engelleyen kancayı
     silerek ya da oraya kendi komutunu koyarak izin motorunu tümüyle
     atlardı. Bu yüzden `.dornick/kancalar.json` dosya yazma araçlarına
     kapalı (`tools/files.py` içindeki `_guard`) ve tek düzenleyicisi
     kullanıcının kendisi.

Dosya yoksa hiçbir şey olmaz: kanca katmanı sessizce devre dışıdır.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ortam

DOSYA_ADI = "kancalar.json"

# Bir kancaya verilen varsayılan süre. Kanca aracın önünde durduğu için
# cömert olamaz: her `write_file`a eklenen 30 saniye, turu yaşanmaz yapar.
VARSAYILAN_ZAMAN_ASIMI = 20.0
MAX_ZAMAN_ASIMI = 120.0

# Kanca çıktısının modele giden kırpılmış hali. Kanca bir gerekçe yazar,
# rapor değil.
MAX_CIKTI = 1200

OLAYLAR = ("arac_oncesi", "arac_sonrasi")


@dataclass(slots=True)
class Kanca:
    """Tek bir kanca tanımı."""

    olay: str
    arac: str                   # fnmatch deseni; "|" ile birden çok
    komut: str
    zaman_asimi: float = VARSAYILAN_ZAMAN_ASIMI

    def uyar_mi(self, arac: str) -> bool:
        """Bu kanca `arac` için mi?

        Desen `|` ile bölünüyor: "write_file|edit_file" iki ayrı desen.
        Tek tek satır yazmak zorunda kalmak, kullanıcıyı kopyala-yapıştıra
        iterdi ve kopyalar birbirinden ayrı bozulurdu.
        """
        for parca in self.arac.split("|"):
            if fnmatch.fnmatch(arac, parca.strip()):
                return True
        return False


@dataclass(slots=True)
class Cikti:
    """Bir kanca koşumunun sonucu."""

    kanca: Kanca
    kod: int = 0
    metin: str = ""
    durum: str = "kostu"        # kostu | zaman_asimi | baslatilamadi

    @property
    def engelliyor(self) -> bool:
        """`arac_oncesi` için: araç çalışmamalı mı?

        Zaman aşımı da engelliyor. Güvenli taraf bu: kullanıcı bir bekçi
        yazdıysa ve bekçi cevap vermiyorsa, "herhalde izin verirdi" demek
        bekçinin varlık sebebini ortadan kaldırır.
        """
        return self.durum == "zaman_asimi" or (self.durum == "kostu" and self.kod != 0)


@dataclass(slots=True)
class Karar:
    """`arac_oncesi` kancalarının toplu sonucu."""

    izin: bool = True
    gerekce: str = ""
    # Engellemeyen ama söylenmesi gereken şeyler (bozuk kanca gibi).
    notlar: list[str] = field(default_factory=list)


# -- yapılandırma -------------------------------------------------------


def dosya_yolu(state_dir: Path | str) -> Path:
    return Path(state_dir) / DOSYA_ADI


def korunan_mu(yol: Path | str) -> bool:
    """Bu yol bir kanca dosyası mı? (yazma araçları buna bakıyor)

    Yalnızca etkin `.dornick` klasörüne değil, ADI `.dornick` olan herhangi bir
    klasörün altındaki `kancalar.json`a bakıyoruz. Model başka bir projenin
    kanca dosyasını da yazamamalı — ve `state_dir`i bilmeyen bir çağıran
    yine de korunmalı.
    """
    yol = Path(yol)
    return (yol.name.lower() == DOSYA_ADI
            and yol.parent.name.lower() == ".dornick")


def cagri_kancaya_dokunuyor_mu(arac: str, girdi: Any) -> bool:
    """Bu DEĞİŞTİREN çağrı kanca dosyasına uzanıyor mu? (yürütücü sorar)

    `korunan_mu` yazma araçlarının yolunu kapatıyor; ama kabuk bir yazma
    aracı değil ve `Set-Content .dornick/kancalar.json` diye bir komut o
    kapıdan hiç geçmiyordu. "Model kendisini durduran çiti sökemez"
    iddiasındaki delik buydu.

    Yürütücü bunu yalnız `mutates` araçlar için soruyor; `read_file`,
    `grep`, `list_dir` etkilenmiyor — model hangi kuralın altında
    çalıştığını okuyabilmeli. Kabukla okumak da kapanıyor (kabuk hem
    okur hem yazar, ikisi komut metninden ayrılamaz); red mesajı
    `read_file`'a yönlendiriyor.

    Bu bir HAPİS DEĞİL, kasıt kapısıdır: adı gizleyen bir komut
    (değişkene atama, parça parça kurma, base64) bunu aşar — kabuk
    komutunu ayrıştırarak kazanılacak bir yarış yok. Kapattığı şey
    gerçek başarısızlık kipi: modelin "şu kancayı kaldırayım da iş
    görsün" deyip doğrudan yazması. Kasıtlı bir düşmana karşı çit,
    izin motorudur.
    """
    if arac in {"write_file", "edit_file", "copy_in"}:
        return False  # kendi kapıları var (`korunan_mu`); mesajları daha iyi
    if not isinstance(girdi, dict):
        return False
    return any(isinstance(d, str) and DOSYA_ADI in d.lower()
               for d in girdi.values())


def _ayrıstir(ham: Any) -> list[Kanca]:
    """JSON gövdesinden kanca listesi. Bozuk maddeler SESSİZCE düşer.

    Neden sessizce: kanca dosyası kullanıcının elindedir ve bir yazım
    hatası yüzünden bütün araç katmanını durdurmak orantısız. Tanınmayan
    olay adı ya da boş komut, olmayan bir kanca demektir — o kadar.
    """
    if not isinstance(ham, list):
        return []
    bulunan: list[Kanca] = []
    for madde in ham:
        if not isinstance(madde, dict):
            continue
        olay = str(madde.get("olay") or "").strip()
        komut = str(madde.get("komut") or "").strip()
        if olay not in OLAYLAR or not komut:
            continue
        try:
            sure = float(madde.get("zaman_asimi") or VARSAYILAN_ZAMAN_ASIMI)
        except (TypeError, ValueError):
            sure = VARSAYILAN_ZAMAN_ASIMI
        bulunan.append(Kanca(
            olay=olay,
            arac=str(madde.get("arac") or "*").strip() or "*",
            komut=komut,
            zaman_asimi=max(1.0, min(sure, MAX_ZAMAN_ASIMI)),
        ))
    return bulunan


# Dosya her araç çağrısında okunuyor gibi görünmesin diye küçük bir
# önbellek: (yol) -> (mtime_ns, boyut, kancalar). Kullanıcı dosyayı
# düzenlediği anda mtime değişiyor ve önbellek kendiliğinden düşüyor —
# yeniden başlatmaya gerek yok.
_bellek: dict[str, tuple[int, int, list[Kanca]]] = {}


def yukle(state_dir: Path | str) -> list[Kanca]:
    """`.dornick/kancalar.json` içindeki kancalar; dosya yoksa boş liste.

    Dosyanın YOKLUĞU olağan durum: kanca kullanan kullanıcı azınlıktır ve
    kullanmayan hiçbir bedel ödememeli. O yüzden hızlı yol tek bir `stat`.
    """
    yol = dosya_yolu(state_dir)
    try:
        bilgi = yol.stat()
    except OSError:
        _bellek.pop(str(yol), None)
        return []

    anahtar = str(yol)
    if (onceki := _bellek.get(anahtar)) is not None:
        if onceki[0] == bilgi.st_mtime_ns and onceki[1] == bilgi.st_size:
            return onceki[2]

    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Bozuk JSON: kancasız çalış. Sessiz değil — çağıran bunu
        # `bozuk_mu` ile sorup kullanıcıya söyleyebiliyor.
        _bellek[anahtar] = (bilgi.st_mtime_ns, bilgi.st_size, [])
        return []

    kancalar = _ayrıstir(ham)
    _bellek[anahtar] = (bilgi.st_mtime_ns, bilgi.st_size, kancalar)
    return kancalar


def bozuk_mu(state_dir: Path | str) -> str:
    """Dosya var ama okunamıyorsa hatanın insan okur hali; yoksa boş dize."""
    yol = dosya_yolu(state_dir)
    if not yol.is_file():
        return ""
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except OSError as exc:
        return f"{yol} okunamadı ({exc.strerror or exc})"
    except ValueError as exc:
        return f"{yol} geçerli JSON değil ({exc})"
    if not isinstance(ham, list):
        return f"{yol} bir liste olmalı (köşeli parantezle başlamalı)"
    return ""


def bellegi_temizle() -> None:
    """Testler için: dosya önbelleğini boşaltır."""
    _bellek.clear()


def eslesenler(state_dir: Path | str, olay: str, arac: str) -> list[Kanca]:
    return [k for k in yukle(state_dir) if k.olay == olay and k.uyar_mi(arac)]


# -- koşum --------------------------------------------------------------


def _ortam(arac: str, args: dict[str, Any], oturum: str) -> dict[str, str]:
    """Kancaya bağlam ORTAM DEĞİŞKENİYLE geçiyor.

    JSON'u komut satırına gömmek kaçış cehennemidir: içindeki tırnaklar
    kabuğun tırnaklarıyla dövüşür, Windows'ta `cmd` ile PowerShell farklı
    kaçış kuralları ister ve kullanıcının kancası ilk yolunda ters eğik
    çizgi görünce sessizce bozulur. Ortam değişkeni bu sorunu hiç
    doğurmuyor.
    """
    cevre = dict(os.environ)
    cevre["DORNICK_ARAC"] = arac
    cevre["DORNICK_OTURUM"] = oturum
    try:
        cevre["DORNICK_ARGS"] = json.dumps(args, ensure_ascii=False)[:32_000]
    except (TypeError, ValueError):  # pragma: no cover - serileşmeyen argüman
        cevre["DORNICK_ARGS"] = "{}"
    # En sık kullanılacak alan ayrıca ve çıplak: kancanın JSON ayrıştırmak
    # zorunda kalmadan `$DORNICK_YOL` yazabilmesi, tek satırlık kancaları
    # mümkün kılan şey.
    yol = args.get("path") or args.get("target") or ""
    cevre["DORNICK_YOL"] = str(yol) if isinstance(yol, str) else ""
    return cevre


def _kirp(metin: str) -> str:
    metin = metin.strip()
    if len(metin) <= MAX_CIKTI:
        return metin
    return metin[:MAX_CIKTI] + "\n… [kanca çıktısı kırpıldı]"


async def _baslat(komut: str, ortak: dict[str, Any]):
    """Komutu platformun kabuğunda başlatır.

    Windows'ta PowerShell açıkça çağrılıyor (`shell` aracının yaptığı gibi):
    `create_subprocess_shell` orada `cmd.exe`ye düşüyor ve kullanıcının
    kanca dosyasına yazdığı komut, Dornick'in her yerde kullandığı kabuktan
    başka bir kabukta koşuyordu — aynı satır bir yerde çalışıp burada
    çalışmıyordu.
    """
    import sys

    if sys.platform == "win32":
        import shutil

        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        # ÇIKIŞ KODU SADAKATİ. Kancanın sözleşmesi çıkış koduna dayanıyor
        # ("sıfır değilse aracı çalıştırma") ve PowerShell kendi çıkış
        # kodunu native bir programın kodundan ayrı tutuyor: `python -c
        # "sys.exit(3)"` çağıran bir kanca dışarıya 1 olarak görünüyordu.
        # Engelleme kararı yine doğru çıkıyordu ama modele giden gerekçe
        # yanlış kodu yazıyordu. `$LASTEXITCODE` varsa onunla çıkılıyor;
        # yoksa (saf cmdlet koştuysa) PowerShell'in kendi kodu geçerli.
        sarmal = f"{komut}\nif ($null -ne $LASTEXITCODE) {{ exit $LASTEXITCODE }}"
        return await asyncio.create_subprocess_exec(
            exe, "-NoProfile", "-NonInteractive", "-Command", sarmal, **ortak)
    # POSIX: kendi oturumunda başlasın ki zaman aşımında bütün ağaç
    # tek sinyalle düşsün.
    ortak.setdefault("start_new_session", True)  # pragma: no cover
    return await asyncio.create_subprocess_shell(komut, **ortak)  # pragma: no cover


async def kos(
    kanca: Kanca,
    *,
    arac: str,
    args: dict[str, Any],
    oturum: str,
    cwd: Path | str,
) -> Cikti:
    """Tek bir kancayı koşturur.

    Kabuk üzerinden: kullanıcı kanca dosyasına boru, `&&`, değişken içeren
    gerçek bir komut satırı yazar. Konsol penceresi açtırmıyor
    (`ortam.sessiz_bayraklar`) — dornick pythonw altında koşarken her yazma
    ekranda bir cmd parlatırdı.
    """
    ortak: dict[str, Any] = dict(
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_ortam(arac, args, oturum),
        **ortam.sessiz_bayraklar(),
    )
    try:
        proc = await _baslat(kanca.komut, ortak)
    except (OSError, ValueError) as exc:
        # Kancanın kendi arızası aracı öldürmemeli: bu bir yapılandırma
        # sorunu, kullanıcının işine engel değil.
        return Cikti(kanca, durum="baslatilamadi",
                     metin=f"{type(exc).__name__}: {exc}")

    is_ = asyncio.ensure_future(proc.communicate())
    try:
        cikti, hata = await asyncio.wait_for(asyncio.shield(is_), kanca.zaman_asimi)
    except asyncio.TimeoutError:
        # Süreç AĞACINI öldür. Yalnızca kabuğu öldürmek kullanıcının asıl
        # kanca komutunu makinede çalışır halde bırakıyor ve boruları açık
        # tuttuğu için burası yine bekliyordu: ölçüldü, 2 saniyelik zaman
        # aşımı 60 saniyelik bir bekleyişe dönüştü.
        await ortam.agaci_oldur(proc)
        try:
            await asyncio.wait_for(is_, 5)
        except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
            is_.cancel()
        return Cikti(kanca, durum="zaman_asimi")

    ham = (cikti or b"").decode("utf-8", errors="replace").strip()
    if not ham:
        ham = (hata or b"").decode("utf-8", errors="replace").strip()
    return Cikti(kanca, kod=proc.returncode or 0, metin=_kirp(ham))


async def arac_oncesi(
    state_dir: Path | str,
    arac: str,
    args: dict[str, Any],
    *,
    oturum: str = "",
    cwd: Path | str = ".",
) -> Karar:
    """Araç çalışmadan ÖNCE koşan kancalar. Biri reddederse araç çalışmaz.

    İlk reddedende duruyoruz: ikinci bir bekçiye sormanın anlamı yok,
    karar çoktan verildi ve kalan kancaları koşturmak yalnızca zaman
    (ve olası yan etki) demek.
    """
    karar = Karar()
    for kanca in eslesenler(state_dir, "arac_oncesi", arac):
        sonuc = await kos(kanca, arac=arac, args=args, oturum=oturum, cwd=cwd)

        if sonuc.durum == "baslatilamadi":
            # Bozuk kanca aracı engellemiyor ama saklanmıyor da: kullanıcı
            # kuralının hiç koşmadığını bilmeli.
            karar.notlar.append(
                f"kanca çalıştırılamadı (`{kanca.komut}`): {sonuc.metin} — "
                "bu kural bu çağrıda uygulanmadı."
            )
            continue

        if sonuc.durum == "zaman_asimi":
            karar.izin = False
            karar.gerekce = (
                f"Kanca reddetti: `{kanca.komut}` {kanca.zaman_asimi:.0f} "
                "saniyede cevap vermedi. Kullanıcının bu araç için bir bekçisi "
                "var ve bekçi cevap vermiyor; güvenli taraf çalıştırmamak. "
                "Kullanıcıya bildir — kancayı ancak o düzeltebilir."
            )
            return karar

        if sonuc.kod != 0:
            karar.izin = False
            aciklama = sonuc.metin or "(kanca bir açıklama yazmadı)"
            karar.gerekce = (
                f"Kanca reddetti (çıkış kodu {sonuc.kod}): {aciklama}\n"
                "Bu, kullanıcının kendi kuralı — sistem promptunda ya da "
                "izin listesinde değil, kendi kanca dosyasında. Kuralı aşmaya "
                "çalışma; başka bir yol dene ya da kullanıcıya sor."
            )
            return karar
    return karar


async def arac_sonrasi(
    state_dir: Path | str,
    arac: str,
    args: dict[str, Any],
    *,
    oturum: str = "",
    cwd: Path | str = ".",
) -> list[str]:
    """Araç çalıştıktan SONRA koşan kancalar. Veto yetkisi YOK.

    Sonucu değiştiremezler çünkü iş çoktan oldu: dosya diske düştü, komut
    koştu. "Reddediyorum" demenin bir karşılığı olmadığı için çıkış kodu
    yalnızca not olarak geçiyor.
    """
    satirlar: list[str] = []
    for kanca in eslesenler(state_dir, "arac_sonrasi", arac):
        sonuc = await kos(kanca, arac=arac, args=args, oturum=oturum, cwd=cwd)
        if sonuc.durum == "baslatilamadi":
            satirlar.append(f"kanca çalıştırılamadı (`{kanca.komut}`): {sonuc.metin}")
            continue
        if sonuc.durum == "zaman_asimi":
            satirlar.append(
                f"kanca `{kanca.komut}` {kanca.zaman_asimi:.0f} saniyede "
                "bitmedi ve durduruldu.")
            continue
        if sonuc.metin:
            onek = "kanca" if sonuc.kod == 0 else f"kanca (çıkış {sonuc.kod})"
            satirlar.append(f"{onek}: {_tek_satir(sonuc.metin)}")
        elif sonuc.kod != 0:
            satirlar.append(
                f"kanca `{kanca.komut}` {sonuc.kod} koduyla bitti (çıktı yok).")
    return satirlar


def _tek_satir(metin: str, tavan: int = 300) -> str:
    """Çok satırlı kanca çıktısını araç sonucuna sığacak hale getirir."""
    duz = " ".join(metin.split())
    return duz if len(duz) <= tavan else duz[:tavan] + "…"
