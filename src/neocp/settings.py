"""Ayarların okunması ve yazılması.

Arayüzün ayar sayfası buradan besleniyor. İki dosyaya yazılıyor:

    .neocp/config.json   model, bağlam, izin — paylaşılabilir
    .neocp/keys.json     API anahtarları — paylaşılamaz

Ayrılmasının sebebi tek: config.json bir projeye girip sürüm kontrolüne
düşebilir, anahtar oraya yazılmamalı. keys.json ayrı duruyor ve tarayıcıya
hiçbir zaman gönderilmiyor — ayar sayfası yalnızca "anahtar var mı" bilgisini
görüyor. Girilen bir anahtar sunucuya bir kez gidiyor, bir daha geri gelmiyor.

Anahtarlar açılışta ortam değişkenine yükleniyor: backend'ler zaten oradan
okuyor, ikinci bir yol açmaya gerek yok.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from . import listen as listen_module
from . import lmstudio
from . import organs, startup
from . import voice as voice_module
from .config import (
    BrowserConfig,
    CameraConfig,
    Config,
    ContextConfig,
    ModelConfig,
    PermissionConfig,
    SandboxConfig,
)
from .listen import ListenConfig
from .place import PlaceConfig
from .voice import VoiceConfig

KEYS_FILE = "keys.json"
CONFIG_FILE = "config.json"

# Değeri girilmiş bir anahtarın tarayıcıya dönen hali. Gerçek değer değil,
# yalnızca "burada bir şey var" işareti.
MASK = "••••••••"


# Sağlayıcı listesi tek yerde: hem ayar sayfası hem `neocp setup` buradan
# okuyor. `env` alanı anahtarın hangi ortam değişkenine yazılacağını söyler;
# None olanlar yerel sunucular, anahtar istemiyorlar.
PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "id": "anthropic",
        "label": "Claude",
        "provider": "anthropic",
        "base_url": None,
        "env": "ANTHROPIC_API_KEY",
        "hint": "console.anthropic.com üzerinden alınır",
    },
    {
        "id": "openai",
        "label": "ChatGPT",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "env": "OPENAI_API_KEY",
        "hint": "platform.openai.com üzerinden alınır",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "provider": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
        "hint": "tek anahtarla çok sağlayıcı",
    },
    {
        "id": "lmstudio",
        "label": "LM Studio",
        "provider": "openai",
        "base_url": "http://localhost:1234/v1",
        "env": None,
        "hint": "Developer sekmesinden sunucuyu başlat",
    },
    {
        "id": "vllm",
        "label": "vLLM",
        "provider": "openai",
        "base_url": "http://localhost:8000/v1",
        "env": None,
        "hint": "python -m vllm.entrypoints.openai.api_server",
    },
    {
        "id": "ollama",
        "label": "Ollama",
        "provider": "openai",
        "base_url": "http://localhost:11434/v1",
        "env": None,
        "hint": "ollama serve",
    },
)

# Posta hesabı. Kimlik bilgileri API anahtarlarıyla aynı dosyada duruyor:
# config.json bir projeye girip sürüm kontrolüne düşebilir.
MAIL_FIELDS: tuple[dict[str, str], ...] = (
    {"env": "NEOCP_IMAP_HOST", "label": "IMAP sunucusu", "hint": "imap.gmail.com", "secret": "0"},
    {"env": "NEOCP_SMTP_HOST", "label": "SMTP sunucusu", "hint": "smtp.gmail.com", "secret": "0"},
    {"env": "NEOCP_MAIL_USER", "label": "adres", "hint": "ornek@gmail.com", "secret": "0"},
    {
        "env": "NEOCP_MAIL_PASSWORD",
        "label": "parola",
        "hint": "Gmail'de normal parola değil 'uygulama şifresi'",
        "secret": "1",
    },
)


PERMISSION_MODES: tuple[dict[str, str], ...] = (
    {"id": "auto", "label": "otomatik", "hint": "okuma serbest, yazma sorulur"},
    {"id": "ask", "label": "her seferinde sor", "hint": "en güvenlisi, en yavaşı"},
    {"id": "plan", "label": "salt okunur", "hint": "hiçbir şeyi değiştiremez"},
    {"id": "yolo", "label": "tam yetki", "hint": "hiçbir şey sorulmaz"},
)


def provider_of(config: ModelConfig) -> str:
    """Ayarlardaki modelin hangi sağlayıcıya denk düştüğü.

    Eşleştirme adrese bakıyor, sağlayıcı adına değil: "openai" altında altı
    farklı sunucu var ve ayar sayfasında hangisinin seçili olduğu görünmeli.
    """
    for entry in PROVIDERS:
        if entry["provider"] != config.provider:
            continue
        if entry["base_url"] == (config.base_url or entry["base_url"]):
            return str(entry["id"])
    return "anthropic" if config.provider == "anthropic" else "openai"


# -- okuma -------------------------------------------------------------


def load_keys(state_dir: Path) -> dict[str, str]:
    path = state_dir / KEYS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: str(v) for k, v in data.items() if isinstance(v, str) and v}


def export_keys(state_dir: Path) -> int:
    """Kaydedilmiş anahtarları ortama yükler. Kaç tane olduğunu döndürür.

    Ortamda zaten bir değer varsa dokunulmuyor: kullanıcının kabuğunda
    verdiği anahtar dosyadakinin önünde gelmeli.
    """
    loaded = 0
    for name, value in load_keys(state_dir).items():
        if not os.environ.get(name):
            os.environ[name] = value
            loaded += 1
    return loaded


def snapshot(config: Config) -> dict[str, Any]:
    """Ayar sayfasının çizdiği her şey. Anahtar değerleri asla girmiyor."""
    keys = load_keys(config.state_dir)
    return {
        "model": asdict(config.model),
        "context": asdict(config.context),
        "permissions": asdict(config.permissions),
        "sandbox": {
            **asdict(config.sandbox),
            # Ayarda göreli bir ad durabiliyor; kullanıcının görmesi
            # gereken çözülmüş hali.
            "root": str(config.open_sandbox().root),
        },
        "voice": {**asdict(config.voice), "available": voice_module.available()},
        # Konum ve otomatik başlatma. İkisi de kapalı geliyor: biri
        # kullanıcının adresini üçüncü bir servise gönderiyor, diğeri
        # açılışa bir kayıt yazıyor.
        "place": asdict(config.place),
        # Makinede gerçekten var mı. Olmayan bir aygıtı açılabilir
        # göstermek, çalışmayan bir düğmeye tıklatmak demek.
        "hardware": {
            "microphone": organs.has_microphone(),
            "camera": organs.has_camera(),
        },
        "startup": {
            "available": startup.available(),
            "enabled": startup.enabled(),
            "command": startup.current() or startup.command(),
        },
        "camera": asdict(config.camera),
        "browser": asdict(config.browser),
        "mail": [
            {**entry, "filled": bool(keys.get(entry["env"]) or os.environ.get(entry["env"]))}
            for entry in MAIL_FIELDS
        ],
        "listen": {
            **asdict(config.listen),
            "available": listen_module.available(),
            "sizes": list(listen_module.SIZES),
        },
        "provider": provider_of(config.model),
        "providers": [
            {
                **entry,
                # Ortamdan gelen anahtar da "var" sayılıyor: kullanıcı
                # kabuğunda vermişse ayar sayfası "eksik" dememeli.
                "has_key": bool(
                    entry["env"] and (keys.get(entry["env"]) or os.environ.get(entry["env"]))
                ),
                "from_env": bool(
                    entry["env"] and not keys.get(entry["env"]) and os.environ.get(entry["env"])
                ),
            }
            for entry in PROVIDERS
        ],
        "modes": list(PERMISSION_MODES),
        "workspace": str(config.workspace),
        "state_dir": str(config.state_dir),
    }


# -- pencere algılama ---------------------------------------------------
#
# Yanlış bir bağlam penceresi ayarının belirtisi sinsi: sıkıştırma hiç
# tetiklenmiyor, istem modelin gerçek sınırını aşıyor ve sunucu istemin
# **başını** sessizce atıyor. Model o noktada kim olduğunu ve ne istendiğini
# unutmuş oluyor — dışarıdan "sapıtıyor" gibi görünüyor.
#
# Varsayılan 200_000 Claude'un penceresi; yerel bir modelde çoğunlukla
# 8k–32k. Sunucuya sorup öğrenebiliyorsak tahmin etmeyelim.

PROBE_TIMEOUT = 2.0

# Uyumlu sunucuların pencereyi bildirdiği alan adları. Standart değil, her
# sunucu kendi adını kullanıyor.
# Sıra önemli: `loaded_context_length` modelin **o an yüklü olduğu**
# pencere, `max_context_length` ise desteklediği en büyük değer. LM Studio
# bir modeli 262144 desteklediği halde 4096 ile yükleyebiliyor; büyük olanı
# yazmak sıkıştırmayı hiç tetiklemeyip sunucunun istemin başını atmasına
# yol açıyor. Gerçek olan yüklü olan.
WINDOW_FIELDS = (
    "loaded_context_length",
    "context_length",
    "context_window",
    "n_ctx",
    "max_context_length",
)


def detect_window(config: Config) -> int | None:
    """Sunucudan modelin gerçek pencere boyutunu sorar.

    Bulamazsa None döner — uydurmak, yanlış ayarı sessizce sürdürmekten
    daha kötü.
    """
    if config.model.provider != "openai" or not config.model.base_url:
        return None

    import urllib.error
    import urllib.request

    try:
        url = config.model.base_url.rstrip("/") + "/models"
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return None

    # Önce yüklü modelin kendi kaydı; yoksa listedeki en büyük değer bir
    # şey söylemiyor, o yüzden eşleşme bulunamazsa None.
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("id") != config.model.name:
            continue
        if (window := _window_of(entry)) is not None:
            return window
    return None


def _window_of(entry: dict[str, Any]) -> int | None:
    for field in WINDOW_FIELDS:
        value = entry.get(field)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def scan_models(config: Config) -> list[dict[str, Any]]:
    """Sunucudaki modeller, yetenekleriyle birlikte.

    Yalnızca ad listelemek yetmiyordu: görüntü kabul etmeyen bir modelde
    kamerayı açmanın, araç kullanmak için eğitilmemiş bir modelde araçları
    beklemenin anlamı yok. LM Studio bunları söylüyor.
    """
    found = lmstudio.models(config.model.base_url)
    if found:
        return [
            {
                "id": m.key,
                "name": m.name,
                "max_context": m.max_context,
                "vision": m.vision,
                "tools": m.tools,
                "loaded": [{"id": i.id, "context": i.context} for i in m.instances],
            }
            for m in found
        ]
    # LM Studio değilse yalnızca ad var.
    return [{"id": name} for name in available_models(config)]


def available_models(config: Config) -> list[str]:
    """Sunucunun sunduğu model kimlikleri.

    Kimliği elle yazdırmak hataya davetiye: "qwen3.5-9b" ile
    "qwen/qwen3.5-9b" arasındaki fark 404 demek ve hata ancak ilk mesajda
    görünüyor. Sunucu listeyi veriyorsa seçtirmek doğrusu; vermiyorsa elle
    yazma yolu açık kalıyor.
    """
    if config.model.provider != "openai" or not config.model.base_url:
        return []

    import urllib.error
    import urllib.request

    try:
        url = config.model.base_url.rstrip("/") + "/models"
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return []

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []

    names = [
        str(entry.get("id"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("id")
        # Gömme modelleri sohbet edemiyor; listede görünmeleri yanlış seçime
        # yol açıyor ve hata ancak ilk mesajda çıkıyor.
        and entry.get("type") not in ("embeddings", "embedding")
        and "embed" not in str(entry.get("id")).lower()
    ]
    return sorted(dict.fromkeys(names))


def loaded_models(config: Config) -> list[dict[str, Any]]:
    """Sunucuda o an yüklü duran modeller.

    LM Studio meşgul bir modele ikinci istek gelince modelin **ikinci bir
    kopyasını** yüklüyor: `qwen3.5-9b`, `qwen3.5-9b:2`, `qwen3.5-9b:3`… Üç
    kopya 6.5 GB'lık bir modelde 20 GB demek ve makine buna dayanmıyor.

    Asıl çözüm önlemek — `model.max_calls = 1` sunucuya aynı anda tek istek
    gitmesini sağlıyor. Burası teşhis: kaç kopya durduğu görünsün ki
    kullanıcı ne olduğunu anlasın.

    `/api/v0/models` LM Studio'ya özgü; olmayan sunucularda boş dönüyor.
    """
    if config.model.provider != "openai" or not config.model.base_url:
        return []

    import urllib.error
    import urllib.request

    # `/v1` yerine `/api/v0`: durum bilgisini yalnızca o uç veriyor.
    root = config.model.base_url.rstrip("/")
    root = root[: -len("/v1")] if root.endswith("/v1") else root

    try:
        with urllib.request.urlopen(f"{root}/api/v0/models", timeout=PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return []

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []

    return [
        {
            "id": entry.get("id", ""),
            "kind": entry.get("type", ""),
            "window": _window_of(entry),
            # Kopyalar ada eklenen `:2`, `:3` ile ayrılıyor; hangi modelin
            # kaç kopyası olduğunu bulmak için taban ad gerekiyor.
            "base": str(entry.get("id", "")).split(":")[0],
        }
        for entry in entries
        if isinstance(entry, dict) and entry.get("state") == "loaded"
    ]


# -- yazma -------------------------------------------------------------


def apply(config: Config, patch: dict[str, Any]) -> Config:
    """Ayarları diske yazar ve güncellenmiş yapılandırmayı döndürür.

    Doğrulama burada yapılıyor, arayüzde değil: ayar sayfası tek istemci
    değil (dosya elle de düzenlenebiliyor) ve bozuk bir değer açılışta
    çöken bir programa dönüşüyor.
    """
    # Taban diskteki hal, çağıranın elindeki değil. Ayar sayfası kısmi yama
    # gönderiyor ("yalnızca izin kipini değiştirdim") ve elde bayat bir
    # Config varsa dokunulmayan alanlar sessizce eski değerlerine dönüyordu.
    base = _from_disk(config)

    model = _model_patch(base.model, patch)
    context = _section(ContextConfig, base.context, patch.get("context"))
    permissions = _section(PermissionConfig, base.permissions, patch.get("permissions"))
    workshop = _section(SandboxConfig, base.sandbox, patch.get("sandbox"))
    speech = _section(VoiceConfig, base.voice, patch.get("voice"))
    located = _section(PlaceConfig, base.place, patch.get("place"))

    # Otomatik başlatma bir dosyaya değil kayda yazılıyor; ayar nesnesinde
    # tutmanın anlamı yok, gerçek durum kaydın kendisi.
    if (wanted := (patch.get("startup") or {}).get("enabled")) is not None:
        startup.apply(bool(wanted))
    hearing = _section(ListenConfig, base.listen, patch.get("listen"))
    eye = _section(CameraConfig, base.camera, patch.get("camera"))
    surfing = _section(BrowserConfig, base.browser, patch.get("browser"))

    if permissions.mode not in {m["id"] for m in PERMISSION_MODES}:
        raise ValueError(f"Bilinmeyen izin kipi: {permissions.mode}")
    if model.max_tokens < 256:
        raise ValueError("max_tokens en az 256 olmalı.")
    if model.context_window < model.max_tokens:
        raise ValueError("Bağlam penceresi max_tokens'tan küçük olamaz.")
    if not workshop.directory.strip():
        raise ValueError("Atölye klasörü boş olamaz.")

    updated = replace(
        base,
        model=model,
        context=context,
        permissions=permissions,
        sandbox=workshop,
        voice=speech,
        place=located,
        listen=hearing,
        camera=eye,
        browser=surfing,
    )
    _write_config(updated)

    if keys := patch.get("keys"):
        _write_keys(config.state_dir, keys)
        # Kullanıcı ayar sayfasından bir anahtarı AÇIKÇA değiştirdi: ortamda
        # eski bir değer olsa bile üzerine yazılmalı. `export_keys` "zaten
        # varsa dokunma" diyor (kabuktaki anahtar dosyadan önce gelsin diye);
        # ama açık bir değişiklik o kuralın istisnası — yoksa yeni anahtar
        # çalışan sürece hiç ulaşmıyor ve yalnızca yeniden başlatınca etkili
        # oluyordu.
        for name, value in keys.items():
            if value:
                os.environ[name] = value
        export_keys(config.state_dir)

    return updated


def _from_disk(config: Config) -> Config:
    """Yapılandırmanın diskteki hali.

    `Config.load` kullanılmıyor: o ortam değişkenlerini de karıştırıyor ve
    kabuktan gelen geçici bir değer kalıcı dosyaya yazılmış olurdu.
    """
    path = config.state_dir / CONFIG_FILE
    if not path.exists():
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return config

    return replace(
        config,
        model=_section(ModelConfig, ModelConfig(), raw.get("model")),
        context=_section(ContextConfig, ContextConfig(), raw.get("context")),
        permissions=_section(PermissionConfig, PermissionConfig(), raw.get("permissions")),
        sandbox=_section(SandboxConfig, SandboxConfig(), raw.get("sandbox")),
        voice=_section(VoiceConfig, VoiceConfig(), raw.get("voice")),
        place=_section(PlaceConfig, PlaceConfig(), raw.get("place")),
        listen=_section(ListenConfig, ListenConfig(), raw.get("listen")),
        camera=_section(CameraConfig, CameraConfig(), raw.get("camera")),
    )


def _model_patch(current: ModelConfig, patch: dict[str, Any]) -> ModelConfig:
    fields = dict(patch.get("model") or {})

    # Sağlayıcı seçimi adresi ve anahtar değişkenini birlikte belirliyor;
    # üçünü elle tutarlı tutmayı kullanıcıya bırakmak hataya davetiye.
    if chosen := patch.get("provider"):
        entry = next((e for e in PROVIDERS if e["id"] == chosen), None)
        if entry is None:
            raise ValueError(f"Bilinmeyen sağlayıcı: {chosen}")
        fields.setdefault("provider", entry["provider"])
        fields.setdefault("base_url", entry["base_url"])
        fields.setdefault("api_key_env", entry["env"])

    unknown = set(fields) - set(ModelConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"Bilinmeyen model alanı: {', '.join(sorted(unknown))}")

    for name in ("max_tokens", "context_window"):
        if name in fields and fields[name] is not None:
            fields[name] = int(fields[name])

    return replace(current, **fields)


def _section(kind: type, current: Any, data: Any) -> Any:
    if not data:
        return current
    unknown = set(data) - set(kind.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{kind.__name__} için bilinmeyen alan: {', '.join(sorted(unknown))}")
    return replace(current, **data)


def _write_config(config: Config) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": asdict(config.model),
        "context": asdict(config.context),
        "permissions": asdict(config.permissions),
        "sandbox": asdict(config.sandbox),
        "voice": asdict(config.voice),
        "place": asdict(config.place),
        "listen": asdict(config.listen),
        "camera": asdict(config.camera),
        "browser": asdict(config.browser),
        # Posta kimliği burada değil: `keys.json` içinde, tıpkı API
        # anahtarları gibi. config.json bir projeye girip sürüm kontrolüne
        # düşebilir.
    }
    _atomic(config.state_dir / CONFIG_FILE, json.dumps(payload, ensure_ascii=False, indent=2))


def _write_keys(state_dir: Path, incoming: dict[str, Any]) -> None:
    """Anahtarları birleştirip yazar.

    Maskeli gelen alan "değiştirilmedi" demek: ayar sayfası gerçek değeri
    hiç görmediği için geri de gönderemiyor. Boş dize ise silme isteği.
    """
    keys = load_keys(state_dir)
    for name, value in incoming.items():
        text = str(value or "").strip()
        if text == MASK:
            continue
        if text:
            keys[name] = text
        else:
            keys.pop(name, None)

    path = state_dir / KEYS_FILE
    state_dir.mkdir(parents=True, exist_ok=True)
    _atomic(path, json.dumps(keys, ensure_ascii=False, indent=2))
    try:
        # Yalnızca sahibi okuyabilsin. Windows'ta bu çağrı sessizce etkisiz
        # kalıyor; orada dosya zaten kullanıcı profilinin altında.
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _atomic(path: Path, text: str) -> None:
    """Yarım yazılmış bir ayar dosyası programı açılmaz hale getirir."""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)
