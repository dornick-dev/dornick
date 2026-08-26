"""Recall eval — Faz 0 baseline'ı kalıcı bir teste bağlar.

İki iş: (1) donmuş eval setinde recall kalitesi hedeflerin üstünde kalsın —
bir değişiklik retrieval'ı bozarsa burada yakalanır; (2) "gerçekten olmuş
gibi" epizodik veriyle (oturum günlükleri) episode aramasının çalıştığını
doğrula.

Ölçümün kendisi `eval/context_memory/baseline.py` içinde; burası eşiklerin
regresyon kapısı. Sayıları görmek için:  python eval/context_memory/baseline.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from neocp.events import EventLog
from neocp.mind import open_mind

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "eval" / "context_memory" / "baseline.py"


def _load_baseline():
    spec = importlib.util.spec_from_file_location("cm_baseline", BASELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="module")
def report() -> dict:
    return _load_baseline().run()


# -- retrieval kalitesi ------------------------------------------------


def test_recall_at_3_beats_target(report: dict) -> None:
    """Blueprint hedefi: doğru parça ilk 3'te ≥ %80. Bunun altına düşmek
    quantization değil, segmentleme/eşleştirme sorununun işareti."""
    assert report["recall@3"] >= 0.80, f"Recall@3 düştü: {report['recall@3']:.2f}"


def test_latency_under_budget(report: dict) -> None:
    """LLM'in ilk token süresinin altında kalmalı."""
    assert report["latency_ms"]["p95"] <= 200


def test_injected_tokens_bounded(report: dict) -> None:
    assert report["avg_injected_tokens"] <= 1200


# -- eşik sinyali (Faz 0'ın asıl bulgusu) ------------------------------


def test_fused_score_now_gates(report: dict) -> None:
    """Birleşik skor (kalibre güven) hafıza/boş'u ARTIK ayırıyor.

    Faz 0'da sıra-tabanlı skor ayırmıyordu (hafıza ve boşun tepe skoru ikisi
    de 1.0'dı, boş-dönüş 0.55'te takılıydı). Araştırma döngüsü bunu düzeltti:
    literal skoru BM25 büyüklüğüne dayandırıp imzayla noisy-or birleştirmek +
    işlev kelimelerini elemek. Artık hafıza ortancası boş-en-yüksekten
    belirgin yüksek ve top1 eşiğiyle boş-dönüş hedefi (≥ %80) tutuyor.
    Bu regresyon kapısı o kazanımı koruyor."""
    sd = report["score_dist"]
    assert sd["mem_top1_median"] > sd["none_top1_max"], (
        f"birleşik skor ayrımı kayboldu: hafıza {sd['mem_top1_median']:.2f} "
        f"vs boş-max {sd['none_top1_max']:.2f}"
    )
    assert report["calibration"]["empty_acc"] >= 0.80, (
        f"top1 eşiğiyle boş-dönüş hedefin altına düştü: "
        f"{report['calibration']['empty_acc']:.2f}"
    )


def test_signature_similarity_separates(report: dict) -> None:
    """İmza benzerliği ise ayırıyor: hafıza ortancası boş-sorgu en
    yükseğinden belirgin yüksek. Gating sinyali olarak kullanılabilir."""
    sd = report["score_dist"]
    assert sd["mem_sim_median"] > sd["none_sim_max"], (
        f"imza ayrımı kayboldu: hafıza {sd['mem_sim_median']:.2f} "
        f"vs boş-max {sd['none_sim_max']:.2f}"
    )


def test_signature_gate_reaches_high_empty_return(report: dict) -> None:
    """SimHash-sim eşiğiyle boş-dönüş ≥ %95 mümkün olmalı — yanlış pozitif
    kontrolünün elde edilebilir olduğunun kanıtı."""
    assert report["calibration_sim"]["empty_acc"] >= 0.95


# -- epizodik: "gerçekten olmuş gibi" oturum günlükleri ----------------


def _write_session(path: Path, turns: list[tuple[str, str]]) -> None:
    """Gerçek bir konuşmayı oturum günlüğü (JSONL) olarak yazar."""
    log = EventLog(path)
    for role, text in turns:
        log.append("message", role=role, content=text)
    log.close()


def test_episode_search_finds_the_right_conversation(tmp_path: Path) -> None:
    """Geçmiş konuşmalar oturum günlükleri olarak duruyor; episode araması
    doğru konuşmayı bulmalı. Bu 'gerçekten olmuş gibi' epizodik katman."""
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)

    _write_session(sessions / "20260610T090000Z.jsonl", [
        ("user", "Çorum terfi istasyonundaki pompanın verimini kontrol eder misin"),
        ("assistant", "Pompa verimi %72 çıktı, tasarım değeri %78'in altında. Debiyi düşüren bir tıkanma olabilir."),
        ("user", "peki güç çekişi normal mi"),
        ("assistant", "Güç 45 kW, nominalin biraz üstünde — verim düşüklüğüyle tutarlı."),
    ])
    _write_session(sessions / "20260612T140000Z.jsonl", [
        ("user", "modbus cihazı bağlantıyı sürekli koparıyor ne yapabilirim"),
        ("assistant", "5.11.239.227:5005 ardışık isteklerde 10054 veriyor; her okumada yeni bağlantı açınca düzeldi."),
    ])
    _write_session(sessions / "20260615T100000Z.jsonl", [
        ("user", "Kayseri kuyu sahasında kaç nokta var"),
        ("assistant", "6 nokta izleniyor, en yüksek debi K-3 kuyusunda."),
    ])

    mind = open_mind(tmp_path / "mind", sessions, "cur")

    hits = mind.episodes("pompa verimi düşük müydü", limit=3)
    assert hits, "episode araması boş döndü"
    top = hits[0].item
    assert "20260610" in top.session_id, "yanlış konuşma ilk sırada"

    other = mind.episodes("cihaz bağlantı koptu", limit=3)
    assert other and "20260612" in other[0].item.session_id
