"""Yapılandırma.

Öncelik sırası: açık argüman > ortam değişkeni > config dosyası > varsayılan.
Config dosyası: <workspace>/.neocp/config.json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from . import sandbox
from .listen import ListenConfig
from .place import PlaceConfig
from .voice import VoiceConfig

# Model kimlikleri tahmin edilmez. Bkz. platform.claude.com/docs -> models.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"

# Taze kurulumun varsayılanı OpenRouter + "oto": tek anahtarla çok sağlayıcı
# ve anahtar girilir girilmez ücretsiz modellerle çalışan bir kurulum
# (bkz. otomod.py). Mevcut kullanıcılar etkilenmez — ayar sayfası model
# bölümünü TÜM alanlarıyla yazıyor, dosyadaki değerler bu varsayılanları
# eziyor.
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OTO_MODEL = "oto"
DEFAULT_MODEL = OTO_MODEL

# Streaming olmadan bu değerin üstü SDK'da HTTP timeout riski taşır.
NONSTREAM_TOKEN_CEILING = 16_000


@dataclass(slots=True)
class ModelConfig:
    name: str = DEFAULT_MODEL
    max_tokens: int = 32_000
    # Modelin bağlam penceresi. Sıkıştırma bu değere göre tetikleniyor,
    # o yüzden gerçeğe yakın olmalı: fazla büyük verilirse pencere
    # sıkıştırma hiç tetiklenmeden dolar. Yerel modellerde çoğunlukla
    # çok daha küçük (8k–32k); ayar sayfasından değiştirilebiliyor.
    context_window: int = 200_000
    # low | medium | high | xhigh | max — ajanik iş için en az high.
    # Yalnızca Anthropic; yerel sağlayıcılarda yoksayılır.
    effort: str = "high"
    # Adaptif düşünme. budget_tokens Opus 4.7+ üzerinde kaldırıldı, 400 döner.
    thinking: bool = True
    # "omitted" varsayılan; kullanıcıya düşünceyi göstereceksek "summarized".
    thinking_display: str = "summarized"

    # Asıl model KALICI olarak çalışmazsa (kredi bitti, kimlik geçersiz,
    # model kaldırıldı) turun ölmesi yerine devreye giren model. Boşsa
    # bugünkü davranış: hata olduğu gibi yüzeye çıkar. Geçici hatalar
    # (bağlantı, 429, 5xx) buraya hiç uğramaz — onlar zaten yeniden
    # deneniyor ve yedeğe düşmek onları gizlerdi.
    fallback_model: str = ""

    # anthropic | openai
    # "openai" OpenAI-uyumlu her sunucuyu kapsar: LM Studio, Ollama, vLLM,
    # llama.cpp server, OpenRouter, OpenAI'nin kendisi.
    provider: str = "openai"
    # LM Studio: http://localhost:1234/v1 · Ollama: http://localhost:11434/v1
    base_url: str | None = OPENROUTER_URL
    # API anahtarının okunacağı ortam değişkeni. Yerel sunucular anahtar
    # istemez ama istemci bir değer bekler.
    api_key_env: str | None = "OPENROUTER_API_KEY"
    # Yerel modellerde işe yarar; Anthropic 4.7+ üzerinde 400 döndüğü için
    # yalnızca openai sağlayıcısında gönderilir.
    temperature: float | None = None
    # Modelin sunucuda yüklü kalacağı süre (saniye). LM Studio `ttl`,
    # Ollama `keep_alive` adıyla anlıyor; ikisi de gönderiliyor ve
    # tanımadığı alanı yok sayıyorlar. 0 = dokunma, sunucunun kendi
    # davranışı geçerli. Her istekte yeniden yükleme onlarca saniye
    # sürüyor ve ilk cevabı bekletiyor.
    keep_loaded: int = 0
    # Aynı anda sunucuya gidebilecek azami istek. Yerel sunucularda 1
    # olmalı: LM Studio meşgul bir modele ikinci istek gelince modelin
    # **ikinci bir kopyasını** yüklüyor. Üç alt ajan üç kopya demek —
    # 6.5 GB'lık bir modelde 20 GB. Resmî API'lerde böyle bir sorun yok,
    # orada yükseltilebilir.
    max_calls: int = 1
    # Yerel LLM optimizasyonu (opt-in). Açıkken: diğer modelleri boşalt,
    # tek kopya tut, VRAM/model boyutuna göre bağlamı düşür. Kapalıysa
    # bugünkü davranış — kullanıcı ne yazdıysa o.
    local_optimize: bool = False

    @property
    def is_local(self) -> bool:
        return self.provider == "openai"

    def thinking_param(self) -> dict[str, Any] | None:
        if not self.thinking:
            return {"type": "disabled"}
        return {"type": "adaptive", "display": self.thinking_display}


@dataclass(slots=True)
class ContextConfig:
    """Bağlam ve önbellek politikası.

    cache_message_breakpoints: mesaj listesine konacak breakpoint sayısı.
        Toplam sınır 4; biri sistem promptuna gider, kalanı buraya.
    lookback_blocks: iki breakpoint arasındaki azami içerik bloğu sayısı.
        API geriye doğru en fazla 20 blok tarar; 20'yi aşarsak önbellek
        sessizce ıskalar. Güvenli pay bırakmak için 15.
    keep_recent_images: geçmişte tutulacak son N görüntü. Öncekiler metin
        yer tutucusuyla değiştirilir (ekran görüntüsü ağır: ~1.5-4.8k token).
    clear_tool_uses: sunucu tarafı bağlam düzenleme (beta). Eski tool_result
        bloklarını temizler. Öneki değiştirdiği için önbelleği o noktadan
        sonra düşürür — seyrek ve öngörülebilir tetikle.
    """

    cache_message_breakpoints: int = 3
    lookback_blocks: int = 15
    keep_recent_images: int = 3
    clear_tool_uses: bool = False
    compact: bool = False
    # Aynı anda koşabilecek azami araç. Model bir turda on araç birden
    # isteyebiliyor; hepsini aynı anda başlatmak zayıf bir makinede
    # belleği ve işlemciyi tüketiyor. Alt ajanlar da bu sınırın içinde.
    max_parallel: int = 4
    # Aynı anda koşabilecek azami ALT AJAN. Araç sınırından ayrı: bir alt
    # ajan tek araçtan çok daha ağır (kendi model çağrıları, kendi araçları).
    # Sınıra takılan spawn beklemeye giriyor, reddedilmiyor — iş sıraya
    # giriyor. Yerel sunucuda model tek kopyaysa 1 mantıklı.
    max_agents: int = 3


@dataclass(slots=True)
class PermissionConfig:
    """İzin politikası.

    mode:
        auto  — mutasyon yapmayan her şey serbest, mutasyon yapanlar sorulur
        ask   — her araç sorulur (allow listesindekiler hariç)
        plan  — mutasyon yapan hiçbir araç çalışmaz (salt okunur keşif)
        yolo  — hiçbir şey sorulmaz. Kendi riskin.

    Kurallar "araç_adı:argüman-deseni" biçiminde fnmatch desenleri:
        "shell:git *"      -> git komutlarına izin
        "write_file:*"     -> tüm yazmalara izin
        "shell:*"          -> tüm kabuk komutları
    """

    mode: str = "ask"
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SandboxConfig:
    """Ajanın kendi klasörü.

    enabled: kapatılırsa yazma kısıtı kalkar ve ajan her yere yazabilir.
        Kapatmak bilinçli bir karar olmalı — açık hali varsayılan.
    directory: çalışma alanına göre ya da mutlak yol.
    """

    enabled: bool = True
    directory: str = sandbox.DEFAULT_DIR
    # Kullanıcının seçtiği proje klasörü. Boşsa yalnızca atölye yazılabilir
    # (bugüne kadarki davranış). Doluysa orası da yazılabilir oluyor:
    # seçimin kendisi onaydır — kullanıcı "burada çalış" demiş demektir.
    # Proje bir OTURUM değil: değiştirmek zihni, anıları ya da konuşma
    # geçmişini etkilemiyor, yalnızca nerede çalışıldığını değiştiriyor.
    project: str = ""


@dataclass(slots=True)
class CameraConfig:
    """Kamera.

    Kapalı geliyor ve açıkken bile sürekli değil: kare alınırken açılıp
    hemen kapanıyor. Arkada açık duran bir kamera kabul edilemez.

    Modelin görüntü kabul etmesi ayrı bir mesele — yerel modellerin çoğu
    etmiyor ve o durumda sağlayıcı anlaşılır bir hata döndürüyor.
    """

    enabled: bool = False


@dataclass(slots=True)
class BrowserConfig:
    """neo chrome — DevTools kapısıyla sürülen tarayıcı.

    Kapalı geliyor: kendi kendine sayfa açan bir asistan, kendi kendine
    konuşandan daha rahatsız edici. Açıldığında tarayıcı neo'nun ayrı
    profiliyle çalışıyor (`.neocp/chrome/`) — kullanıcının gündelik
    tarayıcısına dokunulmuyor.
    """

    enabled: bool = False
    port: int = 9222


@dataclass(slots=True)
class Config:
    workspace: Path
    state_dir: Path
    model: ModelConfig = field(default_factory=ModelConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    permissions: PermissionConfig = field(default_factory=PermissionConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    # Konum: "yarın hava nasıl?" sorusunun cevabı buna bağlı.
    place: PlaceConfig = field(default_factory=PlaceConfig)
    listen: ListenConfig = field(default_factory=ListenConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    # Ek sistem promptu parçası (kişilik / kalıcı yönerge).
    persona_path: Path | None = None

    @property
    def sessions_dir(self) -> Path:
        return self.state_dir / "sessions"

    @property
    def mind_dir(self) -> Path:
        return self.state_dir / "mind"

    def open_sandbox(self) -> "sandbox.Sandbox":
        return sandbox.Sandbox.open(
            self.workspace, self.sandbox.directory, enabled=self.sandbox.enabled,
            project=self.sandbox.project, state_dir=self.state_dir,
        )

    def ensure_dirs(self) -> None:
        for d in (self.state_dir, self.sessions_dir, self.mind_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, workspace: Path | str | None = None) -> Config:
        ws = _resolve_workspace(workspace)
        state = Path(os.getenv("NEOCP_STATE_DIR") or (ws / ".neocp"))

        cfg = cls(workspace=ws, state_dir=state)

        raw = _read_json(state / "config.json")
        if raw:
            cfg = _merge(cfg, raw)

        # Ortam değişkenleri dosyayı ezer.
        if model := os.getenv("NEOCP_MODEL"):
            cfg.model = replace(cfg.model, name=model)
        if effort := os.getenv("NEOCP_EFFORT"):
            cfg.model = replace(cfg.model, effort=effort)
        if provider := os.getenv("NEOCP_PROVIDER"):
            cfg.model = replace(cfg.model, provider=provider)
        if base_url := os.getenv("NEOCP_BASE_URL"):
            cfg.model = replace(cfg.model, base_url=base_url)
        if mode := os.getenv("NEOCP_PERMISSION_MODE"):
            cfg.permissions.mode = mode

        if cfg.persona_path is None:
            candidate = state / "persona.md"
            if candidate.exists():
                cfg.persona_path = candidate

        return cfg


# Çalışma alanı (ev) çözümü. Sorun: ev `Path.cwd()`'den türetiliyordu, o yüzden
# neo başka bir dizinden (ör. bir üst klasörden) açılınca `.neocp` ve `atolye`'yi
# ORAYA kuruyor, verisini bulunduğu yere saçıyordu — kullanıcı: "kendine
# belirlediğimiz yerin dışına çıkmamalı". Artık ev bir kez belirlenince
# SABİTLENİYOR: neo'yu nereden açarsan aç aynı evi kullanır.
#
# Öncelik: açık argüman (test/çağıran; sabitlemez) > NEOCP_WORKSPACE (sabitler)
# > sabitlenmiş ev işaretçisi > cwd'den yukarı var olan bir .neocp (git'in .git
# bulması gibi; sabitler) > cwd (sabitler).
def _home_pointer() -> Path:
    return Path.home() / ".neocp" / "home"


def _read_home() -> Path | None:
    try:
        txt = _home_pointer().read_text(encoding="utf-8").strip()
        return Path(txt).expanduser().resolve() if txt else None
    except Exception:
        return None


def _pin_home(ws: Path) -> None:
    try:
        p = _home_pointer()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(ws), encoding="utf-8")
    except Exception:
        pass


def _resolve_workspace(explicit: Path | str | None) -> Path:
    # 1. Açık argüman: kesin ve SABİTLEMEZ (testler tmp_path geçiyor; ev
    #    işaretçisini bir teste kurban etmemeli).
    if explicit:
        return Path(explicit).expanduser().resolve()
    # 2. NEOCP_WORKSPACE: kullanıcının bilinçli seçimi — sabitler.
    env = os.getenv("NEOCP_WORKSPACE")
    if env:
        ws = Path(env).expanduser().resolve()
        _pin_home(ws)
        return ws
    # 3. Sabitlenmiş ev: nereden açılırsa açılsın aynı ev.
    pinned = _read_home()
    if pinned and pinned.is_dir():
        return pinned
    # 4. cwd'den yukarı var olan bir ev ara, bulunca sabitle.
    cur = Path.cwd().resolve()
    for cand in [cur, *cur.parents]:
        if (cand / ".neocp").is_dir():
            _pin_home(cand)
            return cand
    # 5. Hiçbiri yok: cwd ev olur ve sabitlenir.
    _pin_home(cur)
    return cur


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} okunamadı: {exc}") from exc


def _merge(cfg: Config, raw: dict[str, Any]) -> Config:
    if m := raw.get("model"):
        cfg.model = replace(cfg.model, **_only_fields(ModelConfig, m))
    if c := raw.get("context"):
        cfg.context = replace(cfg.context, **_only_fields(ContextConfig, c))
    if p := raw.get("permissions"):
        cfg.permissions = replace(cfg.permissions, **_only_fields(PermissionConfig, p))
    if s := raw.get("sandbox"):
        cfg.sandbox = replace(cfg.sandbox, **_only_fields(SandboxConfig, s))
    if v := raw.get("voice"):
        cfg.voice = replace(cfg.voice, **_only_fields(VoiceConfig, v))
    if v := raw.get("place"):
        cfg.place = replace(cfg.place, **_only_fields(PlaceConfig, v))
    if l := raw.get("listen"):
        cfg.listen = replace(cfg.listen, **_only_fields(ListenConfig, l))
    if c := raw.get("camera"):
        cfg.camera = replace(cfg.camera, **_only_fields(CameraConfig, c))
    if b := raw.get("browser"):
        cfg.browser = replace(cfg.browser, **_only_fields(BrowserConfig, b))
    if persona := raw.get("persona_path"):
        cfg.persona_path = (cfg.state_dir / persona).resolve()
    return cfg


def _only_fields(kind: type, data: dict[str, Any]) -> dict[str, Any]:
    known = set(kind.__dataclass_fields__)
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"{kind.__name__} için bilinmeyen alan: {', '.join(sorted(unknown))}")
    return data
