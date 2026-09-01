"""İlk kurulum: `dornick setup`.

Amaç tek bir sürtünmeyi kaldırmak — her açılışta ortam değişkeni yazmak.
Bu komut ortamı yoklar, ne bulduğunu söyler, seçimi alır ve
`.dornick/config.json` dosyasına yazar. Sonrasında `dornick --app` yeter.

Ağ yoklaması bilinçli olarak burada; `Config.load()` içinde değil. Yapılandırma
okumanın ağ beklemesi, hem yavaş hem de sürpriz olurdu.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Config

# Yerel sunucu adayları. Hepsi OpenAI-uyumlu konuşuyor.
CANDIDATES = (
    ("LM Studio", "http://localhost:1234/v1"),
    ("Ollama", "http://localhost:11434/v1"),
    ("vLLM", "http://localhost:8000/v1"),
)

PROBE_TIMEOUT = 2.5


@dataclass(slots=True)
class Provider:
    label: str
    provider: str
    model: str
    base_url: str | None = None

    def describe(self) -> str:
        where = f" · {self.base_url}" if self.base_url else ""
        return f"{self.label} · {self.model}{where}"


def discover() -> list[Provider]:
    """Ortamda ne varsa bulur. Sessizce başarısız olur — yok olan yoktur."""
    found: list[Provider] = []

    if os.getenv("ANTHROPIC_API_KEY"):
        found.append(Provider("Anthropic", "anthropic", "claude-opus-4-8"))

    for label, base_url in CANDIDATES:
        for model in _models(base_url):
            # Gömme modelleri sohbet edemez; listeyi kirletmesinler.
            if "embed" in model.lower():
                continue
            found.append(Provider(label, "openai", model, base_url))

    return found


def _models(base_url: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return []
    return [item.get("id", "") for item in payload.get("data", []) if item.get("id")]


def write_config(config: Config, choice: Provider) -> None:
    config.ensure_dirs()
    path = config.state_dir / "config.json"

    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    model = dict(existing.get("model") or {})
    model["provider"] = choice.provider
    model["name"] = choice.model
    # Adres AÇIKÇA yazılıyor (None dahil): alanı dosyadan silmek, varsayılana
    # (artık OpenRouter) düşmek demek — Anthropic'e geçen kullanıcının
    # istekleri OpenRouter'a gider ve hata ancak ilk mesajda görünürdü.
    model["base_url"] = choice.base_url
    # Anahtar değişkeni de sağlayıcıyla birlikte: yerel sunucular anahtar
    # istemiyor, kalan bir OPENROUTER_API_KEY "anahtar yok" uyarısı üretirdi.
    model["api_key_env"] = "ANTHROPIC_API_KEY" if choice.provider == "anthropic" else None
    existing["model"] = model

    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def run(config: Config, console: Any) -> int:
    console.print("\n[bold]dornick kurulumu[/bold]\n")
    console.print("[dim]Ortam yoklanıyor…[/dim]")

    options = discover()
    if not options:
        console.print(
            "\n[yellow]Kullanılabilir bir model bulunamadı.[/yellow]\n\n"
            "İki yoldan biri:\n"
            "  • LM Studio'yu aç, bir model yükle (Developer sekmesi ya da "
            "[cyan]lms load <model>[/cyan]), sonra bu komutu tekrar çalıştır.\n"
            "  • Ya da Anthropic anahtarını tanımla:\n"
            '    [cyan]$env:ANTHROPIC_API_KEY="sk-ant-..."[/cyan]\n'
        )
        return 1

    console.print()
    for index, option in enumerate(options, 1):
        console.print(f"  [cyan]{index}[/cyan]  {option.describe()}")

    choice = options[0]
    if len(options) > 1:
        # Boru ile beslenen girdide stdin kapalı olur; varsayılanla devam
        # etmek, yığın izi basıp çıkmaktan iyidir.
        try:
            raw = input(f"\nHangisi? [1-{len(options)}, varsayılan 1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            raw = ""
            console.print()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            choice = options[int(raw) - 1]

    write_config(config, choice)

    console.print(f"\n[green]Seçildi:[/green] {choice.describe()}")
    console.print(f"[dim]Yazıldı: {config.state_dir / 'config.json'}[/dim]\n")
    console.print("Artık şununla açabilirsin:\n")
    console.print("  [cyan]dornick --app[/cyan]      masaüstü penceresi")
    console.print("  [cyan]dornick[/cyan]            terminalde")
    console.print("  [cyan]dornick --web[/cyan]      tarayıcıda\n")
    console.print(
        "[dim]İlk açılışta zihin boş olur. Konuştukça kendi kendine "
        "dolar ve bir sonraki oturumda seni hatırlar.[/dim]"
    )
    if choice.provider == "openai":
        # LM Studio indirilmiş modelleri listeliyor; seçilen model yüklü
        # değilse ilk istekte belleğe alınıyor ve o istek uzun sürüyor.
        console.print(
            "[dim]Model yüklü değilse ilk mesaj modeli belleğe alırken "
            "bekletebilir. Önceden yüklemek için: "
            f"[/dim][cyan]lms load {choice.model}[/cyan]\n"
        )
    else:
        console.print()
    return 0
