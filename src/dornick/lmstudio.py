"""LM Studio'nun kendi API'si.

OpenAI-uyumlu uç noktası modeli *kullanmaya* yetiyor ama *yönetmeye*
yetmiyor, ve yönetememek somut iki soruna yol açıyordu:

**Yanlış pencereyle yükleme.** LM Studio kendiliğinden yüklerken 4096 token
kullanıyor — model 262144 desteklese bile. Sistem promptu artı araç şemaları
zaten bunu aşıyor ve sunucu istemin başını atıyor; model kim olduğunu ve ne
istendiğini unutuyor. `/api/v1/models/load` `context_length` alıyor, yani
modeli **ayarlardaki pencereyle** yükleyebiliyoruz.

**Kopyalanan model.** Meşgul bir modele ikinci istek gelince LM Studio ikinci
bir kopya yüklüyor: `qwen3.5-9b`, `:2`, `:3`. 6.5 GB'lık bir modelde üç kopya
20 GB. Kopyalar burada görülüp kaldırılabiliyor.

Ayrıca model listesi modelin ne yapabildiğini de söylüyor — görüntü kabul
ediyor mu, araç kullanmak için eğitilmiş mi. Ayar sayfası bunu gösteriyor:
görüntü kabul etmeyen bir modelde kamerayı açmanın anlamı yok.

Bu dosya LM Studio'ya özgü. Başka bir sunucuda uçlar yok ve her çağrı
sessizce boş dönüyor — özellik kaybolur, program çalışmaya devam eder.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

# Liste ucu hızlı; yükleme yavaş (model diskten belleğe çıkıyor).
LIST_TIMEOUT = 3.0
LOAD_TIMEOUT = 180.0

# LM Studio kendiliğinden yüklerken bunu kullanıyor. Bir eşik değil, bir
# gözlem: bu değerle karşılaşınca "kullanıcı böyle istedi" demek yerine
# "kendiliğinden yüklenmiş" demek doğru oluyor.
JIT_CONTEXT = 4096


@dataclass(slots=True)
class Instance:
    """Yüklü duran bir model kopyası."""

    id: str
    context: int


@dataclass(slots=True)
class Model:
    key: str
    name: str
    max_context: int
    vision: bool
    tools: bool
    instances: list[Instance]
    size_bytes: int = 0
    params_b: float = 0.0
    # Katalog `capabilities` içinde varsa; yoksa None — uydurulmaz.
    thinking: bool | None = None

    @property
    def loaded(self) -> bool:
        return bool(self.instances)


def root_of(base_url: str | None) -> str:
    """`http://localhost:1234/v1` → `http://localhost:1234`"""
    text = (base_url or "").rstrip("/")
    return text[: -len("/v1")] if text.endswith("/v1") else text


def models(base_url: str | None) -> list[Model]:
    """Sunucudaki modeller. LM Studio değilse boş liste."""
    payload = _get(base_url, "/api/v1/models")
    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []

    out: list[Model] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "llm":
            continue
        skills = entry.get("capabilities") or {}
        thinking = None
        if isinstance(skills, dict):
            for key in ("reasoning", "think", "thinking"):
                if key in skills:
                    thinking = bool(skills[key])
                    break
        out.append(
            Model(
                key=str(entry.get("key") or ""),
                name=str(entry.get("display_name") or entry.get("key") or ""),
                max_context=int(entry.get("max_context_length") or 0),
                vision=bool(skills.get("vision")) if isinstance(skills, dict) else False,
                tools=bool(skills.get("trained_for_tool_use")) if isinstance(skills, dict) else False,
                size_bytes=int(entry.get("size_bytes") or 0),
                params_b=_params_b(entry.get("params_string")),
                thinking=thinking,
                instances=[
                    Instance(
                        id=str(item.get("id") or ""),
                        context=int((item.get("config") or {}).get("context_length") or 0),
                    )
                    for item in (entry.get("loaded_instances") or [])
                    if isinstance(item, dict)
                ],
            )
        )
    return out


def find(base_url: str | None, key: str) -> Model | None:
    return next((m for m in models(base_url) if m.key == key), None)


def ensure_loaded(base_url: str | None, key: str, context: int, ttl: int = 0) -> dict[str, Any]:
    """Modeli istenen pencereyle yüklü hale getirir.

    `ttl` > 0: model bu kadar saniye boşta kalınca boşaltılsın (LM Studio
    `ttl` alanı). 0 boş bırakılırsa LM Studio kendi varsayılanını kullanıyor —
    ki o da JIT modelleri kısa sürede boşaltıp sonraki isteği "Model unloaded"
    ile düşürüyordu. Çağıran (masaüstü) yerel model için cömert bir değer
    veriyor ki konuşmanın ortasında model kaybolmasın.

    Dönen sözlük ne yapıldığını söylüyor; arayüz de kullanıcıya bunu
    gösteriyor:

        ok       zaten doğru pencereyle yüklüydü, dokunulmadı
        loaded   yüklendi
        capped   istenen pencere modelin sınırından büyüktü, sınıra çekildi
        skipped  LM Studio değil ya da ulaşılamadı

    Yeniden yüklemekten kaçınmak önemli: yükleme saniyeler sürüyor ve her
    açılışta yapmak programı ağır gösteriyor.
    """
    model = find(base_url, key)
    if model is None:
        return {"state": "skipped"}

    wanted = context
    capped = model.max_context and wanted > model.max_context
    if capped:
        wanted = model.max_context

    # Zaten yeterli pencereyle duran bir kopya varsa yeniden yükleme. Daha
    # büyüğü de kabul: istenen sığıyorsa sorun yok.
    if any(inst.context >= wanted for inst in model.instances):
        return {"state": "ok", "context": wanted}

    payload: dict[str, Any] = {"model": key, "context_length": wanted}
    if ttl > 0:
        payload["ttl"] = ttl
    answer = _post(base_url, "/api/v1/models/load", payload)
    if answer.get("error") or not answer:
        return {"state": "skipped", "error": _error_of(answer)}

    return {
        "state": "capped" if capped else "loaded",
        "context": wanted,
        "instance": answer.get("instance_id", ""),
        "seconds": answer.get("load_time_seconds", 0),
    }


def unload(base_url: str | None, instance_id: str) -> bool:
    answer = _post(base_url, "/api/v1/models/unload", {"instance_id": instance_id})
    return not answer.get("error") if answer else False


def drop_duplicates(base_url: str | None, key: str) -> list[str]:
    """Aynı modelin fazla kopyalarını kaldırır; kaldırılanları döndürür.

    En geniş pencereli kopya kalıyor — istemler ona gidiyor zaten ve dar
    olanı tutmak baştaki sorunu sürdürmek olurdu.
    """
    model = find(base_url, key)
    if model is None or len(model.instances) < 2:
        return []

    keep = max(model.instances, key=lambda i: i.context)
    dropped = [i.id for i in model.instances if i.id != keep.id and unload(base_url, i.id)]
    return dropped


def unload_others(base_url: str | None, keep_key: str) -> list[str]:
    """Seçili model dışındaki TÜM yüklü kopyaları boşaltır.

    İki farklı model aynı anda VRAM'de kalmasın diye — yerel optimizasyon
    açıkken `_prepare_model` burayı çağırıyor.
    """
    dropped: list[str] = []
    for model in models(base_url):
        if model.key == keep_key:
            continue
        for inst in model.instances:
            if inst.id and unload(base_url, inst.id):
                dropped.append(inst.id)
    return dropped


def suggest_context(
    wanted: int,
    *,
    max_context: int = 0,
    size_bytes: int = 0,
    params_b: float = 0.0,
    free_vram_mb: int | None = None,
) -> int:
    """İstenen bağlamı GPU / model boyutuna sığacak şekilde düşürür.

    VRAM ölçümü yoksa yalnızca modelin `max_context` tavanı uygulanır.
    Ölçüm varsa: ağırlık + %15 pay + 512 MB yedek düşülür; kalan KV önbelleğe
    ayrılır. Kabaca ~0.06 MB × parametre_B / 1k token (Q4 sınıfı).
    """
    ceiling = wanted if wanted > 0 else 8192
    if max_context and max_context > 0:
        ceiling = min(ceiling, max_context)
    if free_vram_mb is None or free_vram_mb <= 0 or size_bytes <= 0:
        return ceiling if ceiling > 0 else JIT_CONTEXT

    model_mb = size_bytes / (1024 * 1024)
    headroom = free_vram_mb - model_mb * 1.15 - 512.0
    if headroom < 256:
        # Modele zar zor yer: JIT penceresi — konuşma yine de başlasın.
        return min(ceiling, JIT_CONTEXT)

    # KV önbellek kabaca: ~2.5 MB × B-parametre / 1k token (Q4, dikkatli).
    # Eski 0.06×B tahmini VRAM'i aşırı iyimser okuyordu.
    params = params_b if params_b > 0 else max(7.0, model_mb / 550.0)
    kv_mb_per_1k = max(16.0, 2.5 * params)
    from_vram = int(headroom / kv_mb_per_1k * 1000)
    fitted = min(ceiling, max(JIT_CONTEXT, from_vram))
    return _snap_context(fitted)


def is_local_url(base_url: str | None) -> bool:
    """localhost / 127.0.0.1 / ::1 — bulut uçlarında optimizasyon yok."""
    host = (base_url or "").lower()
    return any(
        token in host
        for token in ("localhost", "127.0.0.1", "[::1]", "0.0.0.0")
    )


def _snap_context(n: int) -> int:
    """Bağlamı bilinen basamaklara yuvarla (LM Studio dostu)."""
    steps = (4096, 6144, 8192, 12288, 16384, 24576, 32768, 49152, 65536,
             98304, 131072, 196608, 262144)
    best = steps[0]
    for step in steps:
        if step <= n:
            best = step
        else:
            break
    return best


def _params_b(raw: Any) -> float:
    """'9.0B' / '70B' → float milyar parametre."""
    text = str(raw or "").strip().upper().replace(",", ".")
    if not text:
        return 0.0
    if text.endswith("B"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return 0.0


# -- HTTP --------------------------------------------------------------


def _get(base_url: str | None, path: str) -> dict[str, Any]:
    return _request(base_url, path, None, LIST_TIMEOUT)


def _post(base_url: str | None, path: str, body: dict[str, Any]) -> dict[str, Any]:
    return _request(base_url, path, body, LOAD_TIMEOUT)


def _request(base_url: str | None, path: str, body: Any, timeout: float) -> dict[str, Any]:
    """Her hata boş sözlüğe düşüyor.

    LM Studio olmayan bir sunucuda bu uçlar yok ve olmaması normal: özellik
    kaybolur, program çalışmaya devam eder.
    """
    root = root_of(base_url)
    if not root:
        return {}

    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        root + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Hata gövdesi de bilgi: "Missing required field" gibi mesajlar
        # yutulursa neyin yanlış gittiği hiç görünmüyor.
        try:
            return json.load(exc)
        except Exception:
            return {"error": {"message": f"HTTP {exc.code}"}}
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {}


def _error_of(answer: dict[str, Any]) -> str:
    error = answer.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return str(error or "")
