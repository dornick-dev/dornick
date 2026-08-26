"""Kazanma koşulu ölçeri — dev + tutulmuş set, tek eşik.

ARASTIRMA.md'deki 5 metrikli Pareto'yu ölçer. Eşik DEV'de bir kez seçilir
(recall@3'ü ≥ 0.93 tutan en yüksek eşik → boş-dönüşü en çoklar), sonra
tutulmuş sete AYNEN uygulanır — orada yeniden oynatılmaz (hile kuralı).

Hafızalar dataset.json'daki 24 kayıt (dondurulmuş, iki set de aynısını
kullanır); sorgular dev için dataset.json, tutulmuş için holdout.json.

Gecikme soğuk + tekrar ortancasıyla ölçülür (ısınmış önbellekle değil).

Çalıştır:  python eval/context_memory/harness.py
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from neocp.mind import open_mind  # noqa: E402

HERE = Path(__file__).resolve().parent
K = 3

# Kazanma koşulu (ARASTIRMA.md).
WIN = {
    "recall@3": 0.93,
    "paraphrase@3": 0.80,   # > 0.80 (kesin büyük); kontrolde >= eps ile
    "empty": 0.80,
    "p95_ms": 5.0,
    "tokens": 200,
}


def _memories() -> list[dict]:
    return json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))["memories"]


def _queries(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["queries"]


def _seed(mind, memories):
    slug = {}
    for m in memories:
        node = mind.remember(m["content"], kind=m["kind"], title=m["title"], tags=m.get("tags", []))
        slug[m["slug"]] = node.id
    return slug


def _rank_of(hits, want_id: str) -> int:
    for i, h in enumerate(hits, 1):
        if h.item.id == want_id:
            return i
    return 0


def run_set(queries: list[dict], repeats: int = 3) -> list[dict]:
    """Bir sorgu kümesini taze bir zihinde koşturur; ham satırları döndürür.

    Gecikme: her sorgu birkaç kez ölçülüp ortancası alınıyor (soğuk ilk
    çağrı + tekrarlar). Isınmış tek ölçüm gecikmeyi olduğundan iyi gösterir.
    """
    tmp = Path(tempfile.mkdtemp())
    mind = open_mind(tmp / "mind", tmp / "sessions", "eval")
    slug = _seed(mind, _memories())
    mind.recall("ısınma", limit=8)   # imza indeksi kurulsun

    rows = []
    for item in queries:
        q = item["q"]
        times = []
        hits = None
        for _ in range(repeats):
            t0 = time.perf_counter()
            hits = mind.recall(q, limit=8)
            times.append((time.perf_counter() - t0) * 1000)
        top1 = hits[0].score if hits else 0.0
        row = {"q": q, "type": item["type"], "top1": top1,
               "latency": statistics.median(times)}
        if item["expect"] is None:
            row["empty"] = True
            row["rank"] = 0
            row["tokens"] = 0
        else:
            row["empty"] = False
            row["rank"] = _rank_of(hits, slug[item["expect"]])
            row["tokens"] = sum(len(h.item.content) // 4 for h in hits[:K])
        rows.append(row)
    return rows


def metrics(rows: list[dict], threshold: float) -> dict:
    """Verili eşikte 5 kazanma metriği.

    Eşik kapısı `top1 >= threshold`: altında kalan sorgu boş döner. Bir
    hafıza sorgusu ancak doğru anı ilk 3'te VE kapıyı geçerse isabet sayılır;
    bir boş sorgu ancak kapının altında kalırsa (boş dönerse) başarı.
    """
    mem = [r for r in rows if not r["empty"]]
    emp = [r for r in rows if r["empty"]]
    para = [r for r in mem if r["type"] == "paraphrase"]

    def gated_hit(r):
        return 0 < r["rank"] <= K and r["top1"] >= threshold

    recall = sum(gated_hit(r) for r in mem) / len(mem) if mem else 0.0
    para_recall = sum(gated_hit(r) for r in para) / len(para) if para else 0.0
    empty_ret = sum(r["top1"] < threshold for r in emp) / len(emp) if emp else 0.0
    lat = [r["latency"] for r in rows]
    p95 = sorted(lat)[min(len(lat) - 1, int(len(lat) * 0.95))]
    tokens = statistics.mean(r["tokens"] for r in mem) if mem else 0.0
    # Eşiksiz (ham) recall — "mevcudu kaybetme" referansı.
    raw_recall = sum(0 < r["rank"] <= K for r in mem) / len(mem) if mem else 0.0
    return {
        "recall@3": recall, "raw_recall@3": raw_recall,
        "paraphrase@3": para_recall, "empty": empty_ret,
        "p95_ms": p95, "tokens": tokens,
    }


def choose_threshold(dev_rows: list[dict]) -> float:
    """Eşiği DEV'de seçer: recall@3'ü ≥ 0.93 tutan en yüksek eşik.

    Boş-dönüş eşikle monoton arttığından, recall tabanını koruyan en yüksek
    eşik boş-dönüşü de en çoklar. Bu = ilk 3'te doğru anıyı getiren hafıza
    sorgularının en düşük top1'i (o değerde kapı hâlâ hepsini geçirir).
    Eval'e özel değil: yalnızca skorların dağılımına bakar, sorgu ezberlemez.
    """
    correct = [r["top1"] for r in dev_rows
               if not r["empty"] and 0 < r["rank"] <= K]
    if not correct:
        return 0.0
    return round(min(correct), 6)


def _check(name, value, target, mode=">="):
    ok = value >= target if mode == ">=" else value <= target
    return ok, f"  {'✓' if ok else '✗'} {name:<16} {value:.3f}  ({mode} {target})"


def report(threshold, dev, hold=None):
    def block(tag, m):
        print(f"\n[{tag}]  (eşik {threshold:.4f})")
        checks = [
            _check("recall@3", m["recall@3"], WIN["recall@3"]),
            _check("paraphrase@3", m["paraphrase@3"], WIN["paraphrase@3"]),
            _check("boş-dönüş", m["empty"], WIN["empty"]),
            _check("p95 (ms)", m["p95_ms"], WIN["p95_ms"], "<="),
            _check("token", m["tokens"], WIN["tokens"], "<="),
        ]
        for _, line in checks:
            print(line)
        passed = all(ok for ok, _ in checks)
        print(f"  ham recall@3 (eşiksiz): {m['raw_recall@3']:.3f}")
        print(f"  => {'GEÇTİ' if passed else 'GEÇMEDİ'}")
        return passed

    dev_pass = block("DEV", dev)
    hold_pass = block("TUTULMUŞ", hold) if hold is not None else None
    return dev_pass, hold_pass


def evaluate(verbose: bool = True):
    dev_rows = run_set(_queries(HERE / "dataset.json"))
    t = choose_threshold(dev_rows)
    dev_m = metrics(dev_rows, t)
    hold_path = HERE / "holdout.json"
    hold_m = None
    if hold_path.is_file():
        hold_rows = run_set(_queries(hold_path))
        hold_m = metrics(hold_rows, t)
    if verbose:
        print("=== neocp recall — kazanma koşulu ölçümü ===")
        dp, hp = report(t, dev_m, hold_m)
        print()
    return {"threshold": t, "dev": dev_m, "holdout": hold_m}


if __name__ == "__main__":
    evaluate()
