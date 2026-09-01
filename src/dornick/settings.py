"""Ayarların okunması ve yazılması.

Arayüzün ayar sayfası buradan besleniyor. İki dosyaya yazılıyor:

    .dornick/config.json   model, bağlam, izin — paylaşılabilir
    .dornick/keys.json     API anahtarları — paylaşılamaz

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
from . import organs, ortam, sandbox, shell_assoc, startup
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


# Sağlayıcı listesi tek yerde: hem ayar sayfası hem `dornick setup` buradan
# okuyor. `env` alanı anahtarın hangi ortam değişkenine yazılacağını söyler;
# None olanlar yerel sunucular, anahtar istemiyorlar.
#
# Bulut önayarları resmi OpenAI-uyumlu uçlardan (2026): rastgele ekleme yok.
# Kaynaklar: ai.google.dev/gemini-api/docs/openai · build.nvidia.com ·
# api-docs.deepseek.com · console.groq.com/docs/openai · docs.mistral.ai ·
# help.aliyun.com/en/model-studio/base-url
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
        "id": "gemini",
        "label": "Gemini",
        "provider": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env": "GEMINI_API_KEY",
        "hint": "aistudio.google.com — OpenAI-uyumlu uç",
    },
    {
        "id": "nvidia",
        "label": "NVIDIA NIM",
        "provider": "openai",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "env": "NVIDIA_API_KEY",
        "hint": "build.nvidia.com/settings",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "provider": "openai",
        "base_url": "https://api.deepseek.com",
        "env": "DEEPSEEK_API_KEY",
        "hint": "platform.deepseek.com",
    },
    {
        "id": "groq",
        "label": "Groq",
        "provider": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "env": "GROQ_API_KEY",
        "hint": "console.groq.com",
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "provider": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "env": "MISTRAL_API_KEY",
        "hint": "console.mistral.ai",
    },
    {
        "id": "qwen",
        "label": "Qwen (DashScope)",
        "provider": "openai",
        # Ortak DashScope alanı hâlâ geçerli; üretimde workspace/bölge
        # adresine geçmek için Model › Adres alanını düzenle.
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "env": "DASHSCOPE_API_KEY",
        "hint": "Model Studio — bölgeye göre adresi değiştir",
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
    {"env": "DORNICK_IMAP_HOST", "label": "IMAP sunucusu", "hint": "imap.gmail.com", "secret": "0"},
    {"env": "DORNICK_SMTP_HOST", "label": "SMTP sunucusu", "hint": "smtp.gmail.com", "secret": "0"},
    {"env": "DORNICK_MAIL_USER", "label": "adres", "hint": "ornek@gmail.com", "secret": "0"},
    {
        "env": "DORNICK_MAIL_PASSWORD",
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


# İlk kurulum yönlendirmesi: hiçbir sağlayıcı kullanılabilir değilken
# kullanıcı yazarsa (ya da konuşursa) model hiç çağrılmıyor; sohbete bu
# mesaj düşüyor. Metin arayüzde t() ile İngilizceye çevriliyor (app.js).
KURULUM_YONLENDIRME = (
    "Henüz bir yapay zekâ sağlayıcısı tanımlı değil. Ayarlar › Model'den bir "
    "sağlayıcı seçip API anahtarı girmelisin. Varsayılan sağlayıcı "
    "OpenRouter'dır — anahtarını girdiğinde ücretsiz modellerle 'Oto' modda "
    "hemen başlayabilirsin."
)


def _gpu_snapshot() -> list[dict[str, Any]]:
    """Ayarlar › Makine için VRAM özeti. nvidia-smi yoksa []."""
    try:
        from . import gpu as gpu_module
        return [
            {
                "name": g.name,
                "total_mb": g.total_mb,
                "free_mb": g.free_mb,
                "used_mb": g.used_mb,
            }
            for g in gpu_module.nvidia_gpus()
        ]
    except Exception:
        return []


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


def _gerekli_env(model: ModelConfig) -> str | None:
    """Bu yapılandırmanın çalışması için gereken anahtar değişkeni.

    Adres bilinen bir sağlayıcıya denk düşüyorsa onun anahtarı; düşmüyorsa
    (özel/yerel bir uç) kullanıcı ne yazdıysa o. None = anahtar gerekmiyor.
    """
    entry = next((e for e in PROVIDERS if e["id"] == provider_of(model)), None)
    if entry is not None and entry["base_url"] == (model.base_url or entry["base_url"]):
        return entry["env"]
    return model.api_key_env


def yapilandirilmamis(model: ModelConfig) -> bool:
    """Hiçbir sağlayıcı kullanılabilir durumda değil mi?

    Tanım: model adı boş YA DA anahtar isteyen sağlayıcıda anahtar yok.
    Yerel sunucular (env=None) anahtar istemiyor — onlar adla yapılandırılmış
    sayılır. Anahtarlar açılışta ortama yükleniyor (export_keys), o yüzden
    tek bakılan yer ortam.
    """
    if not (model.name or "").strip():
        return True
    env = _gerekli_env(model)
    return bool(env) and not os.environ.get(env)


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


def _sandbox_snapshot(config: Config) -> dict[str, Any]:
    """Atölye + proje durumu, ayar sayfasının çizdiği hâliyle."""
    box = config.open_sandbox()
    secilen = config.sandbox.project.strip()
    # Ayarda duran yol geçersizleşmiş olabilir (klasör silinmiş, elle
    # düzenlenmiş): sandbox onu sessizce düşürüyor, kullanıcı SEBEBİNİ
    # burada görüyor.
    engel = sandbox.kok_engeli(Path(secilen).expanduser()) if secilen else None
    return {
        **asdict(config.sandbox),
        # Ayarda göreli bir ad durabiliyor; kullanıcının görmesi
        # gereken çözülmüş hali.
        "root": str(box.root),
        "project_root": str(box.project) if box.project else "",
        "project_error": engel or "",
        "project_note": box.note,
        "recent": sandbox.son_projeler(config.state_dir),
    }


def snapshot(config: Config) -> dict[str, Any]:
    """Ayar sayfasının çizdiği her şey. Anahtar değerleri asla girmiyor."""
    keys = load_keys(config.state_dir)
    return {
        "model": asdict(config.model),
        "context": asdict(config.context),
        "permissions": asdict(config.permissions),
        "sandbox": _sandbox_snapshot(config),
        "voice": {**asdict(config.voice), "available": voice_module.available()},
        # Konum ve otomatik başlatma. İkisi de kapalı geliyor: biri
        # kullanıcının adresini üçüncü bir servise gönderiyor, diğeri
        # açılışa bir kayıt yazıyor.
        "place": asdict(config.place),
        # Makinede gerçekten var mı. Olmayan bir aygıtı açılabilir
        # göstermek, çalışmayan bir düğmeye tıklatmak demek.
        # Kurulu düzen mi (sihirbazla)? Arayüz eksik-özellik metnini buna
        # göre seçiyor: kuruluda pip önerilmez, sihirbaz önerilir.
        "installed": ortam.kurulu_mu(),
        # Sahada "hangi sürüm kurulu?" sorusu cevapsızdı: Makine sekmesi
        # salt-okunur gösteriyor, kurulu/geliştirme ayrımı installed'dan.
        "surum": ortam.surum(),
        "hardware": {
            "microphone": organs.has_microphone(),
            "camera": organs.has_camera(),
            "gpu": _gpu_snapshot(),
        },
        "startup": {
            "available": startup.available(),
            "enabled": startup.enabled(),
            "command": startup.current() or startup.command(),
        },
        "shell_assoc": {
            "available": shell_assoc.available(),
            "enabled": shell_assoc.enabled(),
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
# Bulut katalogları (NVIDIA, OpenRouter…) yerelden yavaş olabilir; 2 sn
# sessizce boş listeye düşüyordu — "model yüklenmiyor" gibi görünüyordu.
REMOTE_PROBE_TIMEOUT = 10.0

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
    "max_model_len",
)


def _openai_models_payload(
    config: Config,
) -> tuple[dict[str, Any] | None, str | None]:
    """OpenAI-uyumlu `{base}/models`.

    Dönüş: (payload, hata). Anahtarlı uçlar Bearer ister (Gemini…).
    Hata kısa Türkçe — ayar sayfası 'liste yok' yerine nedeni göstersin.
    """
    if config.model.provider != "openai" or not config.model.base_url:
        return None, None

    import urllib.error
    import urllib.request

    url = config.model.base_url.rstrip("/") + "/models"
    headers = {"User-Agent": "dornick"}
    env = config.model.api_key_env
    if env and (key := os.environ.get(env)):
        headers["Authorization"] = f"Bearer {key}"
    timeout = (
        PROBE_TIMEOUT
        if lmstudio.is_local_url(config.model.base_url)
        else REMOTE_PROBE_TIMEOUT
    )
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except TimeoutError:
        return None, "zaman aşımı"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return None, str(reason)[:80]
    if not isinstance(payload, dict):
        return None, "beklenmeyen yanıt"
    return payload, None


def detect_window(config: Config) -> int | None:
    """Sunucudan modelin gerçek pencere boyutunu sorar.

    Bulamazsa None döner — uydurmak, yanlış ayarı sessizce sürdürmekten
    daha kötü.
    """
    caps = detect_caps(config)
    window = caps.get("max_context")
    return int(window) if isinstance(window, int) and window > 0 else None


def detect_caps(config: Config) -> dict[str, Any]:
    """Seçili modelin katalogdaki yetenekleri. Bilinmeyen alan yok.

    Sağlayıcıya göre şekil değişir: OpenRouter `context_length` +
    `architecture.input_modalities` + `supported_parameters`; LM Studio
    `max_context_length` + `capabilities`; Anthropic listede pencere yok,
    düşünme/görüntü Claude sohbet modellerinde var sayılır; OpenAI resmi
    listede bu alanlar yok — uydurulmaz.
    """
    name = (config.model.name or "").strip()
    if not name or name.lower() == "oto":
        return {}
    caps: dict[str, Any] = {}
    for entry in scan_models(config):
        if entry.get("id") == name:
            caps = {
                key: entry[key]
                for key in ("max_context", "vision", "thinking", "tools")
                if key in entry
            }
            break
    # Ollama `/v1/models` yalnız kimlik verir; pencere/yetenek `/api/show`
    # ile seçili modele sorulur — katalogda N çağrı yok, yalnız Algıla.
    if any(key not in caps for key in ("max_context", "vision", "thinking")):
        for key, value in _ollama_show_caps(config, name).items():
            caps.setdefault(key, value)
    return caps


def _caps_of(entry: dict[str, Any]) -> dict[str, Any]:
    """Tek bir `/models` kaydından bilinen yetenekler. Eksik alan eklenmez."""
    ident = str(entry.get("id") or entry.get("key") or "")
    out: dict[str, Any] = {"id": ident}
    shown = entry.get("name") or entry.get("display_name")
    if shown:
        out["name"] = str(shown)

    window = _window_of(entry)
    top = entry.get("top_provider")
    if window is None and isinstance(top, dict):
        window = _window_of(top)
    if window is not None:
        out["max_context"] = window

    arch = entry.get("architecture")
    if isinstance(arch, dict):
        modalities = arch.get("input_modalities")
        if isinstance(modalities, list):
            out["vision"] = any(str(m).lower() in ("image", "vision") for m in modalities)
        elif isinstance(arch.get("modality"), str):
            out["vision"] = "image" in arch["modality"].lower()

    params = entry.get("supported_parameters")
    if isinstance(params, list):
        low = {str(p).lower() for p in params}
        out["tools"] = "tools" in low or "tool_choice" in low
        out["thinking"] = bool(
            low & {"reasoning", "include_reasoning", "reasoning_effort"}
        )

    skills = entry.get("capabilities")
    if isinstance(skills, dict):
        if "vision" in skills and "vision" not in out:
            out["vision"] = bool(skills["vision"])
        if "trained_for_tool_use" in skills and "tools" not in out:
            out["tools"] = bool(skills["trained_for_tool_use"])
        for key in ("reasoning", "think", "thinking"):
            if key in skills:
                out["thinking"] = bool(skills[key])
                break
    elif isinstance(skills, list) and "vision" not in out:
        out["vision"] = any(str(s).lower() in ("vision", "image") for s in skills)

    return out


def _window_of(entry: dict[str, Any]) -> int | None:
    for field in WINDOW_FIELDS:
        value = entry.get(field)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def scan_models(config: Config) -> list[dict[str, Any]]:
    """Sunucudaki modeller, yetenekleriyle birlikte.

    Yalnızca ad listelemek yetmiyordu: görüntü kabul etmeyen bir modelde
    kamerayı açmanın, araç kullanmak için eğitilmemiş bir modelde araçları
    beklemenin anlamı yok. LM Studio bunları söylüyor.
    """
    return scan_models_result(config)["models"]


def batch_only_model(ident: str) -> bool:
    """OpenRouter `:batch` varyantı — canlı sohbet değil, Batch API'ye özel.

    Bu modeller `/v1/chat/completions` ile 404 verir; asenkron
    `/api/beta/batches` uçuna aittir (saatler sürebilir, araçlı tur
    döngüsüne uymaz). Katalogda ve kayıttta elenir.
    """
    text = str(ident or "").strip()
    if ":" not in text:
        return False
    return text.rsplit(":", 1)[-1].lower() == "batch"


def scan_models_result(config: Config) -> dict[str, Any]:
    """`{models, error}` — ayar sayfası boş listede nedeni göstersin."""
    # LM Studio yönetimi yalnız localhost — NVIDIA/OpenRouter'a
    # /api/v1/models yoklamak yanlış ve gecikme.
    if lmstudio.is_local_url(config.model.base_url):
        found = lmstudio.models(config.model.base_url)
        if found:
            models = []
            for m in found:
                row: dict[str, Any] = {
                    "id": m.key,
                    "name": m.name,
                    "max_context": m.max_context,
                    "vision": m.vision,
                    "tools": m.tools,
                    "loaded": [
                        {"id": i.id, "context": i.context} for i in m.instances
                    ],
                }
                if m.thinking is not None:
                    row["thinking"] = m.thinking
                models.append(row)
            return {"models": models, "error": None}

    if config.model.provider == "anthropic":
        entries, err = _anthropic_catalog(config)
        return {"models": entries, "error": err if not entries else None}

    payload, err = _openai_models_payload(config)
    raw_list = payload.get("data") if isinstance(payload, dict) else None
    entries: list[dict[str, Any]] = []
    if isinstance(raw_list, list):
        for raw in raw_list:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            if raw.get("type") in ("embeddings", "embedding"):
                continue
            ident = str(raw.get("id"))
            if "embed" in ident.lower():
                continue
            # `:batch` canlı sohbet değil — seçilirse 404 + Batch API uyarısı.
            if batch_only_model(ident):
                continue
            entries.append(_caps_of(raw))
    if provider_of(config.model) == "openrouter":
        from .config import OTO_MODEL

        entries.insert(0, {"id": OTO_MODEL, "name": "Oto — ücretsiz model havuzu"})
    return {"models": entries, "error": err if not entries else None}


def _anthropic_catalog(config: Config) -> tuple[list[dict[str, Any]], str | None]:
    """Claude model listesi. Listede pencere yok; sohbet modelleri görüntü
    ve düşünme kabul eder — bu, uçtan gelen bir sayı değil, sağlayıcı gerçeği.
    """
    import urllib.error
    import urllib.request

    env = config.model.api_key_env or "ANTHROPIC_API_KEY"
    key = os.environ.get(env) or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return [], "anahtar yok"
    url = (config.model.base_url or "https://api.anthropic.com").rstrip("/")
    if url.endswith("/v1"):
        url = url + "/models"
    else:
        url = url + "/v1/models"
    req = urllib.request.Request(
        url,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "dornick",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REMOTE_PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        return [], f"HTTP {exc.code}"
    except TimeoutError:
        return [], "zaman aşımı"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return [], str(reason)[:80]
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return [], "liste yok"
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        ident = str(raw["id"])
        if "embed" in ident.lower():
            continue
        item = _caps_of(raw)
        # Claude sohbet modelleri görüntü ve düşünme kabul eder; listede
        # pencere yok — sayı uydurulmaz.
        item.setdefault("vision", True)
        item.setdefault("thinking", True)
        item.setdefault("tools", True)
        out.append(item)
    return out, None


def _ollama_show_caps(config: Config, name: str) -> dict[str, Any]:
    """Ollama `/api/show` — uç söylemezse boş. Katalogda çağrılmaz."""
    base = config.model.base_url or ""
    if "11434" not in base and "ollama" not in base.lower():
        return {}
    import urllib.error
    import urllib.request

    root = lmstudio.root_of(base)
    req = urllib.request.Request(
        root.rstrip("/") + "/api/show",
        data=json.dumps({"name": name}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "dornick"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    info = payload.get("model_info") or payload.get("modelinfo") or {}
    if isinstance(info, dict):
        for key, value in info.items():
            if not str(key).endswith("context_length"):
                continue
            if isinstance(value, (int, float)) and value > 0:
                out["max_context"] = int(value)
                break
    skills = payload.get("capabilities")
    if isinstance(skills, list):
        low = {str(s).lower() for s in skills}
        out["vision"] = "vision" in low or "image" in low
        out["thinking"] = bool(low & {"thinking", "reasoning"})
        out["tools"] = "tools" in low
    return out


def available_models(config: Config) -> list[str]:
    """Sunucunun sunduğu model kimlikleri."""
    names, _err = available_models_with_error(config)
    return names


def available_models_with_error(config: Config) -> tuple[list[str], str | None]:
    """Sunucunun sunduğu model kimlikleri + hata özeti."""
    payload, err = _openai_models_payload(config)
    if not payload:
        return [], err

    entries = payload.get("data")
    if not isinstance(entries, list):
        return [], err or "liste yok"

    names = [
        str(entry.get("id"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("id")
        # Gömme modelleri sohbet edemiyor; listede görünmeleri yanlış seçime
        # yol açıyor ve hata ancak ilk mesajda çıkıyor.
        and entry.get("type") not in ("embeddings", "embedding")
        and "embed" not in str(entry.get("id")).lower()
        # `:batch` yalnız asenkron Batch API — canlı sohbet listesinde yok.
        and not batch_only_model(str(entry.get("id")))
    ]
    return sorted(dict.fromkeys(names)), None


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


# Çıktı tavanı bağlamdan taşmasın diye bırakılan pay (istem + araçlar).
_TOKEN_REZERV = 2048


def adopt_caps(config: Config, model: ModelConfig) -> ModelConfig:
    """Katalog/detect ile model yeteneklerini doldurur. Uydurma yok.

    Pencere/thinking/vision biliniyorsa yazar; bilinmiyorsa dokunmaz.
    max_tokens pencereden büyükse kısılır.
    """
    ad = (model.name or "").strip()
    if not ad or ad.lower() == "oto":
        return _clamp_max_tokens(model)

    from dataclasses import replace as _degistir

    probe = _degistir(config, model=model)
    try:
        caps = detect_caps(probe)
    except Exception:
        return _clamp_max_tokens(model)

    fields: dict[str, Any] = {}
    window = caps.get("max_context")
    if isinstance(window, int) and window > 0:
        fields["context_window"] = window
    if "thinking" in caps:
        fields["can_think"] = bool(caps["thinking"])
        fields["thinking"] = bool(caps["thinking"])
    if "vision" in caps:
        fields["vision"] = bool(caps["vision"])
    if fields:
        model = _degistir(model, **fields)
    return _clamp_max_tokens(model)


def _clamp_max_tokens(model: ModelConfig) -> ModelConfig:
    from dataclasses import replace as _degistir

    window = int(model.context_window or 0)
    if window <= 0:
        return model
    tavan = max(256, window - _TOKEN_REZERV)
    if model.max_tokens <= tavan:
        return model
    return _degistir(model, max_tokens=tavan)


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
    patch_model = patch.get("model") or {}
    # Model kimliği değiştiyse bağlamı API'den doldur (Algıla şart değil).
    # Kullanıcı aynı yamada context_window gönderdiyse ona dokunma.
    kimlik_degisti = (
        model.name != base.model.name
        or model.provider != base.model.provider
        or (model.base_url or "") != (base.model.base_url or "")
    )
    if kimlik_degisti and "context_window" not in patch_model:
        try:
            model = adopt_caps(base, model)
        except Exception:
            model = _clamp_max_tokens(model)
    else:
        model = _clamp_max_tokens(model)

    context = _section(ContextConfig, base.context, patch.get("context"))
    permissions = _section(PermissionConfig, base.permissions, patch.get("permissions"))
    workshop = _section(SandboxConfig, base.sandbox, patch.get("sandbox"))
    speech = _section(VoiceConfig, base.voice, patch.get("voice"))
    located = _section(PlaceConfig, base.place, patch.get("place"))

    # Otomatik başlatma bir dosyaya değil kayda yazılıyor; ayar nesnesinde
    # tutmanın anlamı yok, gerçek durum kaydın kendisi.
    if (wanted := (patch.get("startup") or {}).get("enabled")) is not None:
        startup.apply(bool(wanted))
    if (wanted := (patch.get("shell_assoc") or {}).get("enabled")) is not None:
        shell_assoc.apply(bool(wanted))
    hearing = _section(ListenConfig, base.listen, patch.get("listen"))
    eye = _section(CameraConfig, base.camera, patch.get("camera"))
    surfing = _section(BrowserConfig, base.browser, patch.get("browser"))

    if permissions.mode not in {m["id"] for m in PERMISSION_MODES}:
        raise ValueError(f"Bilinmeyen izin kipi: {permissions.mode}")
    # OpenRouter anahtarı kaydedilmeden ÖNCE canlı doğrulanıyor: yanlış
    # yapıştırılan bir anahtar ancak ilk mesajda patlıyordu ve hata ayar
    # sayfasından uzaktaydı. Ağ yoksa doğrulama atlanıyor — çevrimdışı bir
    # kurulum kilitlenmemeli.
    _dogrula_openrouter_anahtari(patch.get("keys") or {})
    if model.max_tokens < 256:
        raise ValueError("max_tokens en az 256 olmalı.")
    if model.context_window < model.max_tokens:
        raise ValueError("Bağlam penceresi max_tokens'tan küçük olamaz.")
    if not workshop.directory.strip():
        raise ValueError("Atölye klasörü boş olamaz.")
    # Proje seçimi yazma iznini genişletiyor: doğrulama burada, arayüzde
    # değil. Geçersiz bir kök (sürücü kökü, sistem klasörü) ancak ajan
    # oraya yazmaya çalışınca patlardı ve o çok geç.
    if (proje := workshop.project.strip()):
        if (engel := sandbox.kok_engeli(Path(proje).expanduser())) is not None:
            raise ValueError(engel)

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

    # Proje DEĞİŞTİYSE son projeler defterine yaz. Her kaydedişte değil:
    # kullanıcı sesi değiştirdiğinde defterin başı karışmamalı.
    if proje and proje != base.sandbox.project.strip():
        sandbox.proje_hatirla(updated.state_dir, str(Path(proje).expanduser()))

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


def _dogrula_openrouter_anahtari(keys: dict[str, Any]) -> None:
    """Yamadaki OpenRouter anahtarını kaydetmeden yoklar.

    401 dönerse ValueError: ayar sayfası bunu kırmızı satır olarak basıyor
    ve HİÇBİR ŞEY diske yazılmıyor. Ağ yoksa (belirsiz) atla-kaydet; not
    terminale düşüyor — çevrimdışı kurulum kilitlenmemeli.
    """
    aday = str(keys.get("OPENROUTER_API_KEY") or "").strip()
    if not aday or aday == MASK:
        return

    from . import otomod

    durum = otomod.dogrula_anahtar(aday)
    if durum == "gecersiz":
        raise ValueError(
            "OpenRouter anahtarı geçersiz (401) — kaydedilmedi. "
            "openrouter.ai/keys sayfasından anahtarı kontrol et."
        )
    if durum == "belirsiz":
        print(
            "[dornick] OpenRouter anahtarı doğrulanamadı (ağ yok?) — "
            "doğrulama atlandı, anahtar kaydedildi.",
            flush=True,
        )


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
    for name in ("vision", "can_think"):
        if name in fields and fields[name] is not None:
            fields[name] = bool(fields[name])

    # Yerel opt açılınca çift kopyayı engelle — kullanıcı açıkça max_calls
    # yazmadıysa 1'e çek.
    if fields.get("local_optimize") is True and "max_calls" not in fields:
        fields["max_calls"] = 1

    # OpenRouter `:batch` canlı chat completions kabul etmez; aynı modelin
    # senkron kimliğine düşür (google/…:batch → google/…).
    if "name" in fields and batch_only_model(str(fields.get("name") or "")):
        raw = str(fields["name"]).strip()
        fields["name"] = raw.rsplit(":", 1)[0]

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
