"""Atölye ve proje: ajanın nereye yazabildiği.

Kural tek cümle: **okumak her yerde serbest, yazmak yalnızca atölyede —
bir de kullanıcının açıkça seçtiği projede.**

Ayrımın sebebi pratik. Bir şey yapması istendiğinde ajanın bilgisayardaki
her şeyi görebilmesi gerekiyor — hangi dosya nerede, ne yazıyor. Ama ürettiği
şey (betik, site, rapor, kendi MCP'si) kullanıcının dosyalarının arasına
karışmamalı. Lazım olan bir dosya varsa kopyalanıyor: `copy_in` tam olarak
bunun için var, kopya atölyeye düşüyor ve orijinale dokunulmuyor.

Proje kipi bu kuralın istisnası değil, tamamlayıcısı. Kullanıcı kendi
kodunda çalıştırmak istediğinde ("şu projede şunu düzelt") her dosyayı
atölyeye kopyalamak işi imkânsız kılıyor: proje bir dosya değil bir ağaç,
kopyası da orijinali olmuyor. O yüzden kullanıcı bir klasörü AÇIKÇA
seçince orası da yazılabilir oluyor — **seçimin kendisi onaydır**. Atölye
her koşulda açık kalıyor: dornick'nun kendi işleri oraya yazılmaya devam
ediyor, projeyle karışmıyor.

Kapsamın sınırı dürüstçe söylenmeli: bu katman **dosya araçlarını** bağlıyor.
Kabuk bağlanmıyor — bir komut istediği yere yazabilir. Kabuğun çalışma dizini
atölyeye kuruluyor ve gerisini izin motoru tutuyor. Gerçek bir hapis işletim
sistemi seviyesinde iş (kapsayıcı, AppContainer, seccomp) ve bu programın
kurulumunu taşıyabileceğinden ağır.

Yol karşılaştırması `resolve()` üzerinden yapılıyor: `..`, sembolik bağ ve
Windows'un kısa adları (`PROGRA~1`) ancak çözümlendikten sonra karşılaştırılabilir.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Atölyenin çalışma alanı içindeki varsayılan adı.
DEFAULT_DIR = "atolye"

# Son projeler defteri (`.dornick/projeler.json`) ve kaç tane tutulduğu.
PROJECTS_FILE = "projeler.json"
MAX_RECENT = 8

REFUSAL = (
    "Yazma yalnızca atölyende ve seçili projede serbest.\n"
    "Açık kökler: {roots}\n"
    "İstenen yol dışarıda: {path}\n"
    "Dışarıdaki bir dosya lazımsa `copy_in` ile atölyene kopyala; "
    "orijinali olduğu yerde kalır. Kullanıcı başka bir klasörde çalışmanı "
    "istiyorsa onu Ayarlar › Proje'den seçmeli — seçim bir onaydır ve "
    "senin verebileceğin bir karar değil."
)


class OutsideSandbox(Exception):
    """Açık köklerin dışına yazma girişimi. Araç katmanı hataya çeviriyor."""


# -- proje kökü güvenliği ------------------------------------------------
#
# Bir klasörü "yazılabilir" ilan etmek ciddi bir karar. Kullanıcı seçse
# bile bazı kökler kabul edilemez: `C:\` seçmek "her yere yazabilirsin"
# demenin uzun yoludur ve seçim ekranında bunun ne anlama geldiği
# görünmüyor. Bu liste dar ve açık: sistem kökleri, işletim sistemi
# klasörleri ve kullanıcı profilinin KENDİSİ (altındaki projeler serbest).

_TEHLIKELI_ADLAR = (
    "windows", "program files", "program files (x86)", "programdata",
    "system32", "syswow64", "$recycle.bin", "recovery",
    "/bin", "/sbin", "/usr", "/etc", "/var", "/lib", "/boot", "/dev", "/proc", "/sys",
)


def kok_engeli(path: Path) -> str | None:
    """Bu klasör proje kökü olabilir mi? Olamıyorsa sebebini söyler.

    Dönen metin doğrudan kullanıcıya gösteriliyor: "geçersiz" demek
    yetmiyor, NEDEN geçersiz olduğu ve ne yapması gerektiği yazmalı.
    """
    try:
        kok = path.expanduser().resolve()
    except OSError:
        return "Bu yol çözümlenemedi."

    if not kok.exists():
        return f"Böyle bir klasör yok: {kok}"
    if not kok.is_dir():
        return f"Bu bir klasör değil: {kok}"

    # Sürücü/dosya sistemi kökü: `C:\` ya da `/`. Parent'ı kendisiyse köktür.
    if kok.parent == kok:
        return (
            f"{kok} bir sürücü kökü — proje olarak seçmek 'her yere yazabilirsin' "
            "demek olur. Üzerinde çalıştığın projenin kendi klasörünü seç."
        )

    duz = str(kok).replace("\\", "/").lower()
    ad = kok.name.lower()
    for tehlikeli in _TEHLIKELI_ADLAR:
        if ad == tehlikeli or duz == tehlikeli or duz.endswith("/" + tehlikeli.strip("/")):
            return (
                f"{kok} bir işletim sistemi klasörü. Buraya yazmak sistemi "
                "bozabilir; projenin kendi klasörünü seç."
            )

    # Kullanıcı profilinin KENDİSİ fazla geniş (Masaüstü, Belgeler, indirilenler,
    # tarayıcı profilleri hepsi altında). Altındaki bir proje klasörü serbest.
    if (ev := _ev_dizini()) is not None and kok == ev:
        return (
            f"{kok} kullanıcı klasörünün kendisi — altındaki her şeyi (belgeler, "
            "masaüstü, indirilenler) yazılabilir yapardı. İçindeki proje "
            "klasörünü seç."
        )
    return None


def _ev_dizini() -> Path | None:
    try:
        return Path.home().resolve()
    except (OSError, RuntimeError):  # pragma: no cover - ev tanımsız olabilir
        return None


def kok_uyarisi(path: Path, *, state_dir: Path | None = None) -> str:
    """Engel değil ama söylenmesi gereken haller. Boş dize = söylenecek yok.

    Kendi kaynak ağacını ya da `.dornick` durumunu kapsayan bir seçim
    ENGELLENMİYOR: kendi kodunu dornick'ya düzelttirmek meşru bir istek ve bu
    depo tam olarak öyle geliştiriliyor. Ama sessiz de kalınmıyor —
    kullanıcı neyin kapsandığını bilerek seçsin.
    """
    try:
        kok = path.expanduser().resolve()
    except OSError:
        return ""

    notlar: list[str] = []
    if state_dir is not None:
        try:
            durum = state_dir.expanduser().resolve()
            if durum == kok or kok in durum.parents:
                notlar.append(
                    "dornick'nun kendi durumu (.dornick: ayarlar, anılar, oturumlar) "
                    "bu klasörün altında — buraya yazmak dornick'nun hafızasına "
                    "dokunabilir."
                )
        except OSError:
            pass

    # Kaynak ağacı: bu dosyanın kendisi nerede duruyorsa oradaki paket.
    try:
        kaynak = Path(__file__).resolve().parent
        if kaynak == kok or kok in kaynak.parents:
            notlar.append(
                "dornick'nun kendi kaynak kodu bu klasörün altında — kendi "
                "kodunu düzenletmek istiyorsan bu doğru; istemiyorsan daha "
                "dar bir klasör seç."
            )
    except OSError:  # pragma: no cover
        pass
    return " ".join(notlar)


# -- son projeler defteri ------------------------------------------------


def son_projeler(state_dir: Path) -> list[str]:
    """En son seçilenden başlayarak proje yolları."""
    path = state_dir / PROJECTS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if isinstance(x, str) and x.strip()][:MAX_RECENT]


def proje_hatirla(state_dir: Path, yol: str) -> list[str]:
    """Seçilen projeyi defterin başına alır; kopyaları eler, listeyi kırpar."""
    temiz = (yol or "").strip()
    if not temiz:
        return son_projeler(state_dir)
    kalan = [x for x in son_projeler(state_dir) if x.lower() != temiz.lower()]
    yeni = [temiz, *kalan][:MAX_RECENT]
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / PROJECTS_FILE).write_text(
            json.dumps(yeni, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return yeni


@dataclass(slots=True)
class Sandbox:
    root: Path
    enabled: bool = True
    # Atölye DIŞINDA yazılabilir kökler: kullanıcının seçtiği proje.
    # Çoğul, çünkü kavram tek bir projeye bağlı değil; bugün arayüz bir
    # tane veriyor.
    open_roots: tuple[Path, ...] = ()
    # Uyarı gerektiren ama engellenmeyen haller (bkz. kok_uyarisi).
    note: str = ""

    @classmethod
    def open(
        cls,
        workspace: Path,
        directory: str = DEFAULT_DIR,
        *,
        enabled: bool = True,
        project: str = "",
        state_dir: Path | None = None,
    ) -> Sandbox:
        root = Path(directory).expanduser()
        if not root.is_absolute():
            root = workspace / root

        acik: list[Path] = []
        note = ""
        if (secilen := (project or "").strip()):
            aday = Path(secilen).expanduser()
            if not aday.is_absolute():
                aday = workspace / aday
            # Geçersiz bir proje yolu programı AÇILMAZ yapmamalı: ayar
            # dosyası elle düzenlenmiş ya da klasör silinmiş olabilir.
            # Sessizce atölyeye dönülüyor; ayar sayfası sebebi söylüyor.
            if kok_engeli(aday) is None:
                acik.append(aday.resolve())
                note = kok_uyarisi(aday, state_dir=state_dir)

        sandbox = cls(root=root.resolve(), enabled=enabled,
                      open_roots=tuple(acik), note=note)
        if enabled:
            sandbox.ensure()
        return sandbox

    @property
    def project(self) -> Path | None:
        """Seçili proje kökü (varsa). Bugün en çok bir tane."""
        return self.open_roots[0] if self.open_roots else None

    @property
    def roots(self) -> tuple[Path, ...]:
        """Yazmanın serbest olduğu tüm kökler — atölye her zaman ilk."""
        return (self.root, *self.open_roots)

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    # -- sınır ---------------------------------------------------------

    def contains(self, path: Path) -> bool:
        """Yol açık köklerden birinin içinde mi?

        Var olmayan bir yol da doğru cevaplanmalı: yazma çoğunlukla henüz
        olmayan bir dosyaya yapılıyor. `Path.resolve()` var olmayan yolu da
        çözüyor, o yüzden ayrı bir yola gerek yok.
        """
        try:
            resolved = path.expanduser().resolve()
        except OSError:  # Windows'ta bozuk bir bağ burada patlayabiliyor
            return False
        return any(resolved == kok or kok in resolved.parents for kok in self.roots)

    def check(self, path: Path) -> Path:
        """Yazılabilir mi diye bakar; değilse anlatan bir hata atar."""
        if not self.enabled:
            return path
        if not self.contains(path):
            raise OutsideSandbox(REFUSAL.format(
                roots=", ".join(str(k) for k in self.roots), path=path))
        return path

    def relative(self, path: Path) -> str:
        """En yakın açık köke göre yol; hiçbirinin altında değilse mutlak hali."""
        try:
            resolved = path.resolve()
        except OSError:
            return str(path)
        for kok in self.roots:
            try:
                return resolved.relative_to(kok).as_posix()
            except ValueError:
                continue
        return str(resolved)

    # -- prompt --------------------------------------------------------

    def briefing(self) -> str:
        if not self.enabled:
            return ""

        atolye = (
            "Atölyen:\n"
            f"- Kendi klasörün: {self.root}\n"
            "- Dışarıdaki bir dosya lazımsa `copy_in` ile kopyala, "
            "orijinaline dokunma.\n"
            "- Burada istediğini kurabilirsin: her dilde proje (Python, Node, "
            ".NET, PHP...), site, veri çekici, kendi MCP sunucun. Ortamını da "
            "kendin kurarsın (venv, npm, ne gerekiyorsa). Proje başlatırken "
            "önce kendine bir alt klasör aç; hiyerarşi senin."
        )

        if (proje := self.project) is None:
            return (
                atolye
                + "\n- Okuma her yerde serbest; **yazma yalnızca bu klasörde**.\n"
                f"- Göreli yol zaten buraya çözülüyor: `site/index.html` yaz, "
                f"`{self.root.name}/site/index.html` yazma."
            )

        # Proje seçiliyken sıra tersine dönüyor: asıl iş projede, atölye
        # dornick'nun kendi işleri için. Model hangisinin ne olduğunu bilmeli,
        # yoksa kullanıcının projesine "kendi denemelerini" bırakır.
        uyari = f"\n- Dikkat: {self.note}" if self.note else ""
        return (
            "Nerede çalışıyorsun:\n"
            f"- **Çalışılan proje: {proje}** — kullanıcının klasörü, yazma "
            "serbest. Kullanıcı bu klasörü Ayarlar › Proje'den bilerek seçti; "
            "asıl iş burada. Göreli yollar buraya çözülüyor.\n"
            f"- dornick'nun kendi atölyesi: {self.root} — kendi işlerin, "
            "denemelerin ve kullanıcının istemediği ara ürünler için. "
            "Projeye ait olmayan şeyleri buraya koy.\n"
            "- Okuma her yerde serbest; yazma yalnızca bu iki klasörde.\n"
            "- Projede çalışırken oranın kendi düzenine uy: var olan dosya "
            "yapısını, adlandırmayı ve araçları kullan; kendi kalıbını "
            "dayatma." + uyari + "\n\n" + atolye
        )
