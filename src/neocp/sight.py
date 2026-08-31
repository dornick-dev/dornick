"""Yerel GPU görüntü analizi — Whisper'ın kamera kardeşi.

Sohbet modeli her kareye bakmıyor: saniyede yirmi kare, karesi 1.5–4.8k
token. Bunun yerine NVIDIA kartı varsa küçük bir nesne modeli kareyi
**metne** çeviriyor; sohbet modeli o metni alıyor. Görüntü makineden
çıkmıyor.

Kapalı sözlüklü YOLOv8n (COCO-80) sigara ve çakmağı tanımıyor — en yakın
sınıfa yakıştırıyor (kitap, diş fırçası, kişi). CUDA yolunda önce
YOLO-World (açık sözlük) deneniyor; olmazsa nano COCO yedeğe düşer.

GPU yoksa / CUDA oturumu açılamazsa bu katman sessizce durur — o zaman
eski kesit kipi: kare, görüntü kabul eden modele gider.

Model ilk kullanımda indirilir ve `~/.neocp/models` altında kalır.
Whisper gibi süreç boyunca bellekte durur.
"""

from __future__ import annotations

import base64
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INSTALL_HINT = "Yerel GPU kamera analizi için: pip install 'neocp[watch]'"

# Ultralytics'in resmî nano ONNX'i. İlk kullanımda bir kez.
MODEL_URL = (
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.onnx"
)
MODEL_NAME = "yolov8n.onnx"
INPUT = 640
CONF = 0.35
IOU = 0.45
# Nano model ~200–400 MB VRAM. Bunun altı: yerel LLM kartı doldurmuş,
# ikinci oturum OOM olur — kesit kipine düş.
MIN_FREE_MB = 400
# YOLO-World s bir kademe daha yer ister; yetmezse nano COCO.
MIN_FREE_MB_WORLD = 650
CONF_WORLD = 0.25

COCO_EN = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
)
COCO_TR = (
    "kişi", "bisiklet", "araba", "motosiklet", "uçak", "otobüs", "tren",
    "kamyon", "tekne", "trafik ışığı", "yangın musluğu", "dur işareti",
    "parkmetre", "bank", "kuş", "kedi", "köpek", "at", "koyun", "inek",
    "fil", "ayı", "zebra", "zürafa", "sırt çantası", "şemsiye", "el çantası",
    "kravat", "bavul", "frizbi", "kayak", "snowboard", "top", "uçurtma",
    "beyzbol sopası", "beyzbol eldiveni", "kaykay", "sörf tahtası",
    "tenis raketi", "şişe", "kadeh", "kupa", "çatal", "bıçak", "kaşık",
    "kase", "muz", "elma", "sandviç", "portakal", "brokoli", "havuç",
    "sosisli", "pizza", "donut", "pasta", "sandalye", "kanepe", "saksı",
    "yatak", "yemek masası", "tuvalet", "ekran", "laptop", "fare", "kumanda",
    "klavye", "telefon", "mikro dalga", "fırın", "tost makinesi", "lavabo",
    "buzdolabı", "kitap", "saat", "vazo", "makas", "oyuncak ayı",
    "saç kurutma", "diş fırçası",
)
# World'e 80 COCO sınıfı vermek sigara/çakmağı yine kitaba gömüyor.
# Oda + el nesnesi: CLIP'in ayırt etmesi için kısa sözlük.
WORLD_EN = (
    "person",
    "chair", "couch", "bed", "dining table",
    "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "cup", "bottle", "wine glass", "bowl",
    "book", "clock", "vase", "scissors", "potted plant",
    "backpack", "handbag",
    "cat", "dog", "bird",
    "refrigerator", "microwave", "oven", "sink",
    "toothbrush",
    "cigarette",
    "cigarette pack",
    "lighter",
)
WORLD_EXTRA = (
    ("cigarette", "sigara"),
    ("cigarette pack", "sigara paketi"),
    ("lighter", "çakmak"),
)
LABEL_TR = {en: tr for en, tr in zip(COCO_EN, COCO_TR)}
LABEL_TR.update({en: tr for en, tr in WORLD_EXTRA})
LABEL_TR["pack of cigarettes"] = "sigara paketi"
LABEL_TR["cell phone"] = "telefon"
LABEL_TR["couch"] = "kanepe"
LABEL_TR["tv"] = "ekran"
LABEL_TR["potted plant"] = "saksı"
LABEL_TR["hair drier"] = "saç kurutma"

WORLD_WEIGHTS = ("yolov8s-worldv2.pt", "yolov8s-world.pt")


def hint() -> str:
    from . import ortam

    if ortam.kurulu_mu():
        return ("Yerel GPU kamera analizi bu kuruluma dahil edilmemiş. "
                "Kurulum sihirbazını yeniden çalıştırıp 'Kamera izleme' "
                "bileşenini işaretleyerek ekleyebilirsin.")
    return INSTALL_HINT


def available() -> bool:
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return False
    return _ultra_ok() or _ort_importable()


def _ultra_ok() -> bool:
    try:
        import torch
        import ultralytics  # noqa: F401
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _ort_importable() -> bool:
    try:
        _onnxruntime()
        return True
    except ImportError:
        return False


def _onnxruntime() -> Any:
    """Kurulu düzende watch/site GPU tekerleğini dinleme CPU tekerleğinin
    önüne alır. İki bileşen de onnxruntime adlı paketi koyuyor; ._pth'te
    listen önce geldiği için CPU kopyası CUDA EP'siz yüklenebiliyordu."""
    exe = Path(sys.executable).resolve()
    aday = exe.parent.parent / "watch" / "site"
    if aday.is_dir():
        yol = str(aday)
        if yol in sys.path:
            sys.path.remove(yol)
        sys.path.insert(0, yol)
    import onnxruntime as ort
    return ort


def _retryable(reason: str) -> bool:
    r = (reason or "").casefold()
    return r in ("", "yükleniyor") or "indirilemedi" in r


def _etiket(idx: int, names: Any = None) -> str:
    """Sınıf adı: modelin İngilizce ismi → Türkçe etiket."""
    en = ""
    if isinstance(names, dict):
        en = str(names.get(idx, names.get(str(idx), "")) or "")
    elif isinstance(names, (list, tuple)) and 0 <= idx < len(names):
        en = str(names[idx])
    key = en.strip().lower()
    if key in LABEL_TR:
        return LABEL_TR[key]
    if 0 <= idx < len(COCO_TR):
        return COCO_TR[idx]
    return en or f"sınıf {idx}"


def _vram_free() -> int | None:
    try:
        from . import gpu as gpu_module

        return gpu_module.primary_free_mb()
    except Exception:
        return None


def _load_world() -> tuple[Any, str]:
    """Açık sözlük: sigara / çakmak COCO'da yok, World metinle arar."""
    free = _vram_free()
    if free is not None and free < MIN_FREE_MB_WORLD:
        return None, ""
    try:
        from ultralytics import YOLO
    except Exception:
        return None, ""
    root = Path.home() / ".neocp" / "models"
    root.mkdir(parents=True, exist_ok=True)
    for name in WORLD_WEIGHTS:
        try:
            cached = root / name
            model = YOLO(str(cached) if cached.is_file() else name)
            if not hasattr(model, "set_classes"):
                continue
            model.set_classes(list(WORLD_EN))
            return model, "world"
        except Exception:
            continue
    return None, ""


def _open_ultra() -> tuple[Any, str, str, str]:
    """YOLO-World (açık sözlük) ya da YOLOv8n — torch CUDA."""
    if not _ultra_ok():
        return None, "", "", ""
    try:
        from ultralytics import YOLO
        import numpy as np

        dummy = np.zeros((160, 160, 3), dtype=np.uint8)
        model, kind = _load_world()
        if model is not None:
            try:
                model.predict(dummy, verbose=False, device=0)
                return model, "cuda", "", kind
            except Exception:
                pass
        weights = _model_path().with_suffix(".pt")
        model = YOLO(str(weights) if weights.is_file() else "yolov8n.pt")
        model.predict(dummy, verbose=False, device=0)
        return model, "cuda", "", "ultra"
    except Exception as exc:
        return None, "", f"ultralytics CUDA açılamadı: {exc}", ""


def _open_ort() -> tuple[Any, str, str, str]:
    try:
        ort = _onnxruntime()
    except ImportError:
        return None, "", hint(), ""
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        return None, "", "onnxruntime CUDA tekerleği yok", ""
    path = _ensure_model()
    if path is None:
        return None, "", "model indirilemedi (yolov8n.onnx)", ""
    try:
        session = ort.InferenceSession(
            str(path), providers=["CUDAExecutionProvider"])
    except Exception as exc:
        return None, "", f"ORT CUDA oturumu açılamadı: {exc}", ""
    if "CUDAExecutionProvider" not in session.get_providers():
        return None, "", (
            "ORT CUDA DLL yüklenemedi (CUDA 13 gerekir; bu makinede "
            "CUDA 12 var — ultralytics yolu kullanılır)"), ""
    return session, "cuda", "", "onnx"


def _model_path() -> Path:
    """Model ağırlığının yeri: önce KURULUMLA GELEN kopya.

    Kurulum sihirbazı ONNX'i kamera bileşeniyle birlikte paketliyor
    (watch/models) — kurulu makinede ilk bakış indirme beklemez ve
    çevrimdışı da çalışır ("kullanıcı sonradan hiçbir şey kurmasın",
    31.08). Paket kopyası yoksa (kaynaktan koşan geliştirici) eski yol:
    ~/.neocp/models altına bir kez indirilir.
    """
    paketli = Path(sys.executable).resolve().parent.parent / "watch" / "models" / MODEL_NAME
    if paketli.is_file():
        return paketli
    return Path.home() / ".neocp" / "models" / MODEL_NAME


@dataclass(slots=True, frozen=True)
class Hit:
    name: str
    conf: float
    x: float  # 0..1, kutu merkezi
    y: float
    w: float = 0.0  # 0..1, kutu eni (çizim)
    h: float = 0.0  # 0..1, kutu boyu


class Seer:
    """Tek GPU oturumu. Whisper Listener gibi bir kez yüklenir."""

    def __init__(self) -> None:
        self._session: Any = None
        self._kind = ""
        self._tried = False
        self._lock = threading.Lock()
        self.device = ""
        self.reason = ""

    @property
    def ready(self) -> bool:
        return self._session is not None and self.device == "cuda"

    def load(self) -> bool:
        """CUDA oturumunu açar. CPU'ya düşmez — o kesit kipinin işi."""
        with self._lock:
            if self.ready:
                return True
            if self._tried and not _retryable(self.reason):
                return False
            self._tried = True
            self.reason = "yükleniyor"
            self._session, self.device, self.reason, self._kind = self._open()
            return self.device == "cuda"

    def _open(self) -> tuple[Any, str, str, str]:
        try:
            from . import gpu as gpu_module

            free = gpu_module.primary_free_mb()
            if free is not None and free < MIN_FREE_MB:
                return None, "", f"VRAM yetersiz ({free} MB boş)", ""
            gpu_module.cuda_libs_on_path()
        except Exception:
            pass

        ultra = _open_ultra()
        if ultra[1] == "cuda":
            return ultra
        ort = _open_ort()
        if ort[1] == "cuda":
            return ort
        return None, "", (ultra[2] or ort[2] or hint()), ""

    def hits_bgr(self, frame: Any) -> list[Hit]:
        """OpenCV BGR kare → kutulu tespit. GPU yoksa boş."""
        if not self.load():
            return []
        try:
            import numpy as np

            arr = np.asarray(frame)
            if self._kind in ("ultra", "world"):
                conf = CONF_WORLD if self._kind == "world" else CONF
                return _detect_ultra(self._session, arr, conf=conf)
            return _detect(self._session, arr)
        except Exception:
            return []

    def analyze_bgr(self, frame: Any) -> str:
        """OpenCV BGR kare → Türkçe nesne özeti. Boş string = bakılamadı."""
        hits = self.hits_bgr(frame)
        if not self.ready:
            return ""
        return _ozet(hits)

    def analyze_url(self, data_url: str) -> str:
        frame = _decode(data_url)
        if frame is None:
            return ""
        return self.analyze_bgr(frame)


_seer: Seer | None = None
_seer_lock = threading.Lock()


def seer() -> Seer:
    global _seer
    with _seer_lock:
        if _seer is None:
            _seer = Seer()
        return _seer


def status() -> dict[str, Any]:
    """UI/API için ucuz özet. load() tetiklemez."""
    s = seer()
    return {
        "ready": s.ready,
        "device": s.device,
        "model": (
            "yolov8s-world" if s._kind == "world"
            else ("yolov8n" if s.ready else "")
        ),
        "kind": s._kind,
        "tried": s._tried,
        "reason": s.reason,
    }


_warmup_lock = threading.Lock()
_warmup_started = False


def ensure_warmup() -> None:
    """Deck/API açılınca bir kez arka planda yükle. Çift thread yok."""
    global _warmup_started
    with _warmup_lock:
        if _warmup_started:
            return
        _warmup_started = True
    threading.Thread(target=warmup, daemon=True, name="neo-sight").start()


def warmup() -> dict[str, Any]:
    """Açılışta arka planda: ilk bakış indirme beklemesin."""
    ok = seer().load()
    st = status()
    if ok:
        print(f"[neo] kamera analizi CUDA'da ({st['model']})", flush=True)
    elif st["reason"]:
        print(f"[neo] kamera analizi yok: {st['reason']}", flush=True)
    return st


def analyze_url(data_url: str) -> str:
    return seer().analyze_url(data_url)


def analyze_bgr(frame: Any) -> str:
    return seer().analyze_bgr(frame)


def hits_bgr(frame: Any) -> list[Hit]:
    return seer().hits_bgr(frame)


def satir(data_url: str) -> str:
    """Araç metnine eklenecek satır. Analiz yoksa boş."""
    ozet = analyze_url(data_url)
    return f"Yerel GPU analizi: {ozet}" if ozet else ""


def _ensure_model() -> Path | None:
    path = _model_path()
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    for url in (
        MODEL_URL,
        "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.onnx",
    ):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 neo/sight"})
            with urllib.request.urlopen(req, timeout=60) as cevap, open(tmp, "wb") as out:
                while chunk := cevap.read(1 << 16):
                    out.write(chunk)
            if tmp.is_file() and tmp.stat().st_size > 1_000_000:
                tmp.replace(path)
                return path
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            tmp.unlink(missing_ok=True)
    return None


def _decode(data_url: str) -> Any:
    if not data_url or "," not in data_url:
        return None
    try:
        import cv2
        import numpy as np

        raw = base64.b64decode(data_url.partition(",")[2])
        return cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def _letterbox(bgr: Any, size: int = INPUT) -> tuple[Any, float, int, int]:
    import cv2
    import numpy as np

    h, w = bgr.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    top = (size - nh) // 2
    left = (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas, scale, left, top


def _detect_ultra(model: Any, bgr: Any, *, conf: float = CONF) -> list[Hit]:
    results = model.predict(bgr, verbose=False, device=0, conf=conf)
    if not results:
        return []
    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return []
    hits: list[Hit] = []
    names = results[0].names or {}
    xywhn = boxes.xywhn.tolist()
    cls = boxes.cls.tolist()
    confs = boxes.conf.tolist()
    for (x, y, bw, bh), c, p in zip(xywhn, cls, confs):
        idx = int(c)
        hits.append(Hit(name=_etiket(idx, names), conf=float(p),
                        x=float(x), y=float(y), w=float(bw), h=float(bh)))
    return hits


def _detect(session: Any, bgr: Any) -> list[Hit]:
    import cv2
    import numpy as np

    canvas, scale, pad_x, pad_y = _letterbox(bgr)
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))[None]

    inp = session.get_inputs()[0].name
    out = session.run(None, {inp: tensor})[0]
    return _parse(out, scale, pad_x, pad_y, bgr.shape[1], bgr.shape[0])


def _parse(out: Any, scale: float, pad_x: int, pad_y: int,
           width: int, height: int) -> list[Hit]:
    import numpy as np

    arr = np.asarray(out)
    # (1, 84, 8400) ya da (1, 8400, 84)
    if arr.ndim == 3:
        arr = arr[0]
    if arr.shape[0] in (84, 85) and arr.shape[0] < arr.shape[1]:
        arr = arr.T
    if arr.shape[1] < 6:
        return []

    boxes = arr[:, :4]
    scores = arr[:, 4:]
    cls = scores.argmax(axis=1)
    conf = scores.max(axis=1)
    keep = conf >= CONF
    if not keep.any():
        return []
    boxes, conf, cls = boxes[keep], conf[keep], cls[keep]

    # xywh (letterbox px) → xyxy orijinal
    xyxy = np.empty_like(boxes)
    xyxy[:, 0] = (boxes[:, 0] - boxes[:, 2] / 2 - pad_x) / scale
    xyxy[:, 1] = (boxes[:, 1] - boxes[:, 3] / 2 - pad_y) / scale
    xyxy[:, 2] = (boxes[:, 0] + boxes[:, 2] / 2 - pad_x) / scale
    xyxy[:, 3] = (boxes[:, 1] + boxes[:, 3] / 2 - pad_y) / scale

    order = _nms(xyxy, conf)
    hits: list[Hit] = []
    for i in order:
        name = _etiket(int(cls[i]))
        cx = float(((xyxy[i, 0] + xyxy[i, 2]) / 2) / max(1, width))
        cy = float(((xyxy[i, 1] + xyxy[i, 3]) / 2) / max(1, height))
        bw = float((xyxy[i, 2] - xyxy[i, 0]) / max(1, width))
        bh = float((xyxy[i, 3] - xyxy[i, 1]) / max(1, height))
        hits.append(Hit(name=name, conf=float(conf[i]), x=cx, y=cy, w=bw, h=bh))
    return hits


def _nms(xyxy: Any, scores: Any, iou: float = IOU) -> list[int]:
    import numpy as np

    x1, y1, x2, y2 = xyxy[:, 0], xyxy[:, 1], xyxy[:, 2], xyxy[:, 3]
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = list(np.argsort(scores)[::-1])
    keep: list[int] = []
    while order:
        i = order.pop(0)
        keep.append(int(i))
        if not order:
            break
        rest = np.array(order, dtype=int)
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        union = areas[i] + areas[rest] - inter + 1e-6
        drop = set(rest[inter / union > iou].tolist())
        order = [j for j in order if j not in drop]
    return keep


def _yan(x: float, y: float) -> str:
    """Kutu merkezi: yalnız kenardaysa yer söylenir."""
    lr = "sol" if x < 0.33 else ("sağ" if x > 0.67 else "")
    tb = "üstte" if y < 0.33 else ("altta" if y > 0.67 else "")
    if lr and tb:
        return f"{tb} {lr}da"
    if lr:
        return f"{lr}da"
    if tb:
        return tb
    return ""


def _ozet(hits: list[Hit]) -> str:
    """Nesne listesini tek cümleye indirir. Boş sahne de bir cevaptır."""
    if not hits:
        return "belirgin nesne yok"
    # Aynı sınıfı say, en güvenilir konumu tut.
    groups: dict[str, list[Hit]] = {}
    for h in hits:
        groups.setdefault(h.name, []).append(h)
    parts: list[str] = []
    for name, bunch in sorted(groups.items(), key=lambda kv: -max(h.conf for h in kv[1])):
        n = len(bunch)
        best = max(bunch, key=lambda h: h.conf)
        yer = _yan(best.x, best.y)
        if n > 1:
            parca = f"{n} {name}"
        else:
            parca = name
        if yer:
            parca += f" ({yer})"
        parts.append(parca)
    return ", ".join(parts)


def _font(size: int) -> Any:
    from pathlib import Path

    try:
        from PIL import ImageFont
    except ImportError:
        return None
    windir = Path(__import__("os").environ.get("WINDIR", r"C:\Windows"))
    for candidate in (
        windir / "Fonts" / "segoeui.ttf",
        windir / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def paint_jpeg(jpeg: bytes, hits: list[Hit]) -> bytes:
    """Kutulari ve Turkce etiketleri JPEG uzerine cizer. GPU gerekmez."""
    if not jpeg or not hits:
        return jpeg
    try:
        import cv2
        import numpy as np
    except ImportError:
        return jpeg
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg
    h, w = frame.shape[:2]
    try:
        from PIL import Image, ImageDraw

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        im = Image.fromarray(rgb)
        draw = ImageDraw.Draw(im)
        font = _font(max(14, min(h, w) // 26))
        color = (240, 160, 32)
        for hit in hits:
            bw = hit.w if hit.w > 0 else 0.18
            bh = hit.h if hit.h > 0 else 0.18
            x1 = int((hit.x - bw / 2) * w)
            y1 = int((hit.y - bh / 2) * h)
            x2 = int((hit.x + bw / 2) * w)
            y2 = int((hit.y + bh / 2) * h)
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            etiket = f"{hit.name} {int(hit.conf * 100)}"
            if font is not None:
                box = draw.textbbox((x1, y1), etiket, font=font)
                ty = max(0, y1 - (box[3] - box[1]) - 2)
                draw.rectangle([x1, ty, box[2] - box[0] + x1 + 6, y1], fill=color)
                draw.text((x1 + 3, ty), etiket, fill=(20, 16, 12), font=font)
            else:
                draw.text((x1 + 3, max(0, y1 - 14)), etiket, fill=color)
        bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    except Exception:
        bgr = frame
        for hit in hits:
            bw = hit.w if hit.w > 0 else 0.18
            bh = hit.h if hit.h > 0 else 0.18
            x1 = int((hit.x - bw / 2) * w)
            y1 = int((hit.y - bh / 2) * h)
            x2 = int((hit.x + bw / 2) * w)
            y2 = int((hit.y + bh / 2) * h)
            cv2.rectangle(bgr, (x1, y1), (x2, y2), (32, 160, 240), 2)
            cv2.putText(bgr, hit.name.encode("ascii", "ignore").decode() or "?",
                        (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (32, 160, 240), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
    return buf.tobytes() if ok else jpeg


_annot_lock = threading.Lock()
_annot_cache: dict[str, tuple[float, bytes, str]] = {}
_ANNOT_TTL = 0.35


def annotate_jpeg(jpeg: bytes, *, key: str = "") -> tuple[bytes, str]:
    """YOLO + boyama. Hazir degilse ham kare. Ayni kamera 0.35 sn onbellegi."""
    import time

    if not jpeg:
        return jpeg, ""
    now = time.monotonic()
    if key:
        with _annot_lock:
            prev = _annot_cache.get(key)
            if prev and now - prev[0] < _ANNOT_TTL:
                return prev[1], prev[2]
    if not status().get("ready"):
        return jpeg, ""
    try:
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return jpeg, ""
    if frame is None:
        return jpeg, ""
    hits = hits_bgr(frame)
    ozet = _ozet(hits)
    painted = paint_jpeg(jpeg, hits) if hits else jpeg
    if key:
        with _annot_lock:
            _annot_cache[key] = (now, painted, ozet)
    return painted, ozet
