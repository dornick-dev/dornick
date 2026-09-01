"""Yerel GPU kamera analizi.

Asıl oturum (YOLOv8n + CUDA) bu testlerde açılmıyor: indirme ve kart
istiyor. Burada tutulan, modele GİDEN şey — özet biçimi, hareket kapısı,
CPU'ya düşmeme.
"""

from __future__ import annotations

from types import SimpleNamespace

import inspect
import numpy as np
import pytest

from dornick import sight
from dornick.desktop import _hareket_gonder, _yerel_uc
from dornick.watch import Camera, Sighting


def test_paint_jpeg_draws_a_box_without_gpu() -> None:
    """Etiket çizimi YOLO oturumu istemez — sahne kutuyu karede görmeli."""
    cv2 = pytest.importorskip("cv2")
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    painted = sight.paint_jpeg(
        buf.tobytes(),
        [sight.Hit("kupa", 0.9, 0.5, 0.5, 0.4, 0.4)],
    )
    assert len(painted) > 100
    assert painted != buf.tobytes()
    assert sight._ozet([]) == "belirgin nesne yok"


def test_same_class_is_counted_and_placed() -> None:
    hits = [
        sight.Hit("kişi", 0.9, 0.1, 0.5),
        sight.Hit("kişi", 0.8, 0.2, 0.5),
        sight.Hit("kupa", 0.7, 0.8, 0.8),
    ]
    ozet = sight._ozet(hits)
    assert "2 kişi" in ozet
    assert "solda" in ozet
    assert "kupa" in ozet
    assert "altta sağda" in ozet


def test_center_object_has_no_side() -> None:
    assert sight._yan(0.5, 0.5) == ""
    assert sight._yan(0.1, 0.5) == "solda"
    assert sight._yan(0.9, 0.1) == "üstte sağda"


def test_handheld_objects_are_named_not_guessed() -> None:
    """COCO'da sigara ve çakmak yok; nano onları kitaba / diş fırçasına
    yakıştırıyordu. Açık sözlük + Türkçe etiket şart."""
    assert len(sight.COCO_EN) == len(sight.COCO_TR) == 80
    assert "cigarette" in sight.WORLD_EN
    assert "lighter" in sight.WORLD_EN
    assert "cigarette pack" in sight.WORLD_EN
    assert sight.LABEL_TR["cigarette"] == "sigara"
    assert sight.LABEL_TR["lighter"] == "çakmak"
    assert sight.LABEL_TR["cigarette pack"] == "sigara paketi"
    assert sight._etiket(0, {0: "cigarette"}) == "sigara"
    assert sight._etiket(2, {1: "book", 2: "lighter"}) == "çakmak"
    assert sight._etiket(73, {73: "book"}) == "kitap"
    src = inspect.getsource(sight._load_world) + inspect.getsource(sight._open_ultra)
    assert "set_classes" in src
    assert "yolov8n.pt" in inspect.getsource(sight._open_ultra)
    assert "world" in inspect.getsource(sight.Seer.hits_bgr)


def test_nms_drops_the_weaker_overlap() -> None:
    xyxy = np.array([
        [0.0, 0.0, 10.0, 10.0],
        [1.0, 1.0, 11.0, 11.0],  # neredeyse aynı kutu
        [50.0, 50.0, 60.0, 60.0],
    ], dtype=float)
    scores = np.array([0.9, 0.4, 0.8])
    keep = sight._nms(xyxy, scores, iou=0.3)
    assert keep[0] == 0
    assert 2 in keep
    assert 1 not in keep


def test_status_does_not_download_or_load() -> None:
    """/api/cameras her açılışta soruluyor; load() tetiklenirse model
    indirilir ve UI donar."""
    st = sight.status()
    assert st["ready"] is False or st["device"] == "cuda"
    assert "model" in st and "reason" in st


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, ev: dict) -> None:
        self.events.append(ev)


class _Bridge:
    def __init__(self, url: str) -> None:
        self.submitted: list[tuple[str, str]] = []
        model = SimpleNamespace(base_url=url)
        self.agent = SimpleNamespace(config=SimpleNamespace(model=model))

    def submit(self, text: str, image: str = "") -> None:
        self.submitted.append((text, image))


def _sighting() -> Sighting:
    return Sighting(
        camera=Camera(id="c1", name="bahce", source="rtsp://x", kind="rtsp"),
        frame="data:image/jpeg;base64,QUJD",
        change=0.4,
        ask="ne oldu",
    )


def test_gpu_analysis_sends_text_not_the_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kart çalışıyorsa kare makineden çıkmaz — sohbet modeli metni alır."""
    monkeypatch.setattr(sight, "analyze_url", lambda _u: "kişi (solda), kupa")
    hub, bridge = _Hub(), _Bridge("https://api.openai.com/v1")
    config = SimpleNamespace(camera=SimpleNamespace(enabled=True, cloud_ok=False))
    _hareket_gonder(bridge, config, hub, _sighting())
    assert len(bridge.submitted) == 1
    text, image = bridge.submitted[0]
    assert "Yerel GPU analizi: kişi (solda), kupa" in text
    assert image == ""


def test_without_gpu_a_cloud_model_does_not_get_the_frame(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sight, "analyze_url", lambda _u: "")
    hub, bridge = _Hub(), _Bridge("https://api.openai.com/v1")
    config = SimpleNamespace(camera=SimpleNamespace(enabled=True, cloud_ok=False))
    _hareket_gonder(bridge, config, hub, _sighting())
    assert bridge.submitted == []
    assert any("BULUT" in (e.get("text") or "") for e in hub.events)


def test_without_gpu_a_local_model_still_gets_the_frame(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sight, "analyze_url", lambda _u: "")
    hub, bridge = _Hub(), _Bridge("http://127.0.0.1:1234/v1")
    config = SimpleNamespace(camera=SimpleNamespace(enabled=True, cloud_ok=False))
    _hareket_gonder(bridge, config, hub, _sighting())
    assert len(bridge.submitted) == 1
    assert bridge.submitted[0][1].startswith("data:image/")


def test_motion_is_ignored_when_the_camera_is_off(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """HUD kapalıyken izleyici bir kare üretse bile sohbet açılmaz."""
    monkeypatch.setattr(sight, "analyze_url", lambda _u: "kişi (altta)")
    hub, bridge = _Hub(), _Bridge("https://api.openai.com/v1")
    config = SimpleNamespace(camera=SimpleNamespace(enabled=False, cloud_ok=False))
    _hareket_gonder(bridge, config, hub, _sighting())
    assert bridge.submitted == []
    assert hub.events == []


def test_builtin_webcam_motion_is_ignored_when_the_lens_is_off(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Dahili webcam HUD kapalıyken sohbete 'hareket oldu' basmaz.

    İzleyici kendi OpenCV'siyle kare alıyordu; model `look` ile Lens'i
    kapalı görüp 'kamerayı göremiyorum' diyordu — kullanıcı oturdukça
    her dakika aynı mesaj.
    """
    monkeypatch.setattr(sight, "analyze_url", lambda _u: "kişi (altta)")
    hub, bridge = _Hub(), _Bridge("https://api.openai.com/v1")
    config = SimpleNamespace(camera=SimpleNamespace(enabled=True, cloud_ok=False))
    seen = Sighting(
        camera=Camera(id="usb", name="Bilgisayar kamerası", source="0"),
        frame="data:image/jpeg;base64,QUJD",
        change=0.07,
        ask="Bu kamerada bir hareket oldu.",
    )
    _hareket_gonder(bridge, config, hub, seen)
    assert bridge.submitted == []
    assert hub.events == []


def test_sync_camera_stops_the_watcher() -> None:
    """HUD kamerayı kapatınca arka plan izleyici de durur."""
    from dornick.desktop import Bridge

    class Eyes:
        def __init__(self) -> None:
            self.stopped = 0

        def stop(self) -> None:
            self.stopped += 1

        def start(self) -> bool:
            return True

        def load_from(self, cameras: list) -> None:
            pass

        def unsnooze(self) -> None:
            pass

    bridge = Bridge.__new__(Bridge)
    bridge.server = None
    bridge.agent = None
    bridge.lens = None
    bridge.hub = None
    bridge.eyes = Eyes()
    cfg = SimpleNamespace(
        camera=SimpleNamespace(enabled=False),
        state_dir=".",
    )
    Bridge.sync_camera(bridge, cfg)
    assert bridge.eyes.stopped == 1


def test_turning_the_camera_off_stops_the_watcher() -> None:
    from dornick.desktop import Bridge

    src = inspect.getsource(Bridge.sync_camera)
    assert "eyes.stop" in src
    assert "eyes.start" in src


def test_cuda_session_is_not_a_cpu_fallback() -> None:
    """GPU yoksa sessizce CPU'da çalışmak, kesit kipini gizler.
    `_open` CPU provider kullanmaz."""
    import inspect
    source = inspect.getsource(sight._open_ort)
    assert "CUDAExecutionProvider" in source
    assert "CPUExecutionProvider" not in source


def test_local_url_helper_still_matches_the_privacy_gate() -> None:
    assert _yerel_uc("http://127.0.0.1:1234/v1") is True
    assert _yerel_uc("https://openrouter.ai/api/v1") is False


def test_the_camera_is_off_until_asked_for(tmp_path: Path) -> None:
    """Kamerayı kendiliğinden açan bir program kabul edilemez."""
    from dornick.config import Config

    assert not Config.load(tmp_path).camera.enabled


def test_cameras_list_does_not_warmup_when_camera_is_off() -> None:
    """Sayfa yüklenince /api/cameras listeleniyor; kapalı kamerada YOLO
    yüklemek UI'yi ve VRAM'i boşuna dolduruyordu."""
    import inspect
    from dornick.web.server import _Handler
    src = inspect.getsource(_Handler._cameras)
    assert "config.camera.enabled" in src
    assert "ensure_warmup" in src
    # warmup, enabled kontrolünün içinde kalmalı
    assert src.index("config.camera.enabled") < src.index("ensure_warmup")


def test_camera_frame_serves_the_lens_buffer() -> None:
    """Güverte karesi snapshot(warm=2) ile kamerayı yeniden açmasın."""
    import inspect
    from dornick.web.server import _Handler
    src = inspect.getsource(_Handler._camera_frame)
    assert "preview_jpeg" in src
    assert "warm=2" not in src
    assert "annotate_jpeg" in src
    assert "boxes" in src

def test_model_path_prefers_the_packaged_copy(tmp_path, monkeypatch) -> None:
    """Kurulumla gelen ONNX once: kurulu makinede ilk bakis indirme
    beklemez, cevrimdisi calisir. Paket kopyasi yoksa eski yol."""
    import sys
    from dornick import sight
    sahte_exe = tmp_path / 'python' / 'python.exe'
    sahte_exe.parent.mkdir(parents=True)
    sahte_exe.write_bytes(b'x')
    monkeypatch.setattr(sys, 'executable', str(sahte_exe))
    # Paket kopyasi yokken ev dizini yolu
    assert str(sight._model_path()).endswith('yolov8n.onnx')
    assert '.dornick' in str(sight._model_path())
    # Paket kopyasi varsa o kazanir
    m = tmp_path / 'watch' / 'models' / 'yolov8n.onnx'
    m.parent.mkdir(parents=True)
    m.write_bytes(b'onnx')
    assert sight._model_path() == m

