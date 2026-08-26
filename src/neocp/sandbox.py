"""Atölye: ajanın kendi klasörü.

Kural tek cümle: **okumak her yerde serbest, yazmak yalnızca burada.**

Ayrımın sebebi pratik. Bir şey yapması istendiğinde ajanın bilgisayardaki
her şeyi görebilmesi gerekiyor — hangi dosya nerede, ne yazıyor. Ama ürettiği
şey (betik, site, rapor, kendi MCP'si) kullanıcının dosyalarının arasına
karışmamalı. Lazım olan bir dosya varsa kopyalanıyor: `copy_in` tam olarak
bunun için var, kopya atölyeye düşüyor ve orijinale dokunulmuyor.

Kapsamın sınırı dürüstçe söylenmeli: bu katman **dosya araçlarını** bağlıyor.
Kabuk bağlanmıyor — bir komut istediği yere yazabilir. Kabuğun çalışma dizini
atölyeye kuruluyor ve gerisini izin motoru tutuyor. Gerçek bir hapis işletim
sistemi seviyesinde iş (kapsayıcı, AppContainer, seccomp) ve bu programın
kurulumunu taşıyabileceğinden ağır.

Yol karşılaştırması `resolve()` üzerinden yapılıyor: `..`, sembolik bağ ve
Windows'un kısa adları (`PROGRA~1`) ancak çözümlendikten sonra karşılaştırılabilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Atölyenin çalışma alanı içindeki varsayılan adı.
DEFAULT_DIR = "atolye"

REFUSAL = (
    "Yazma yalnızca atölyende serbest: {root}\n"
    "İstenen yol dışarıda: {path}\n"
    "Dışarıdaki bir dosya lazımsa `copy_in` ile atölyene kopyala; "
    "orijinali olduğu yerde kalır."
)


class OutsideSandbox(Exception):
    """Atölye dışına yazma girişimi. Araç katmanı bunu hataya çeviriyor."""


@dataclass(slots=True)
class Sandbox:
    root: Path
    enabled: bool = True

    @classmethod
    def open(cls, workspace: Path, directory: str = DEFAULT_DIR, *, enabled: bool = True) -> Sandbox:
        root = Path(directory).expanduser()
        if not root.is_absolute():
            root = workspace / root
        sandbox = cls(root=root.resolve(), enabled=enabled)
        if enabled:
            sandbox.ensure()
        return sandbox

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    # -- sınır ---------------------------------------------------------

    def contains(self, path: Path) -> bool:
        """Yol atölyenin içinde mi?

        Var olmayan bir yol da doğru cevaplanmalı: yazma çoğunlukla henüz
        olmayan bir dosyaya yapılıyor. `Path.resolve()` var olmayan yolu da
        çözüyor, o yüzden ayrı bir yola gerek yok.
        """
        try:
            resolved = path.expanduser().resolve()
        except OSError:  # Windows'ta bozuk bir bağ burada patlayabiliyor
            return False
        return resolved == self.root or self.root in resolved.parents

    def check(self, path: Path) -> Path:
        """Yazılabilir mi diye bakar; değilse anlatan bir hata atar."""
        if not self.enabled:
            return path
        if not self.contains(path):
            raise OutsideSandbox(REFUSAL.format(root=self.root, path=path))
        return path

    def relative(self, path: Path) -> str:
        """Atölyeye göre yol; dışarıdaysa mutlak hali."""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except (ValueError, OSError):
            return str(path)

    # -- prompt --------------------------------------------------------

    def briefing(self) -> str:
        if not self.enabled:
            return ""
        return (
            "Atölyen:\n"
            f"- Kendi klasörün: {self.root}\n"
            "- Okuma her yerde serbest; **yazma yalnızca bu klasörde**.\n"
            f"- Göreli yol zaten buraya çözülüyor: `site/index.html` yaz, "
            f"`{self.root.name}/site/index.html` yazma.\n"
            "- Dışarıdaki bir dosya lazımsa `copy_in` ile kopyala, "
            "orijinaline dokunma.\n"
            "- Burada istediğini kurabilirsin: her dilde proje (Python, Node, "
            ".NET, PHP...), site, veri çekici, kendi MCP sunucun. Ortamını da "
            "kendin kurarsın (venv, npm, ne gerekiyorsa). Proje başlatırken "
            "önce kendine bir alt klasör aç; hiyerarşi senin."
        )
