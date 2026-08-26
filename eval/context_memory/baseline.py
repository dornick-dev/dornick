"""Faz 0 — neocp recall'ının donmuş eval setindeki baseline'ı.

Blueprint'in emri: öğrenen hiçbir katman eklemeden önce mevcut sistemin
sayısını al. Sonraki her katman (entity ipucu, sorgu yeniden yazma, öğrenen
kapı) bu sayıya göre kıyaslanır. Ölçmeden inşa etmek körlemesine.

Ölçülen, neocp'nin bugünkü retrieval motoru: `mind.recall` — FTS5 literal +
256-bit SimHash imza + yayılan aktivasyon. Üretimde bunun üstüne `loop.py`
ayrıca `_worth_recalling` (selamı atlar) ve `_relevant` (yalnız doğrudan
eşleşme) uyguluyor; buradaki sayı çıplak motorun sayısı.

Çalıştır:  python eval/context_memory/baseline.py
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# Windows Türkçe konsolu (cp1254) Unicode'u kaldırmıyor; çıktı UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from neocp.mind import open_mind  # noqa: E402
from neocp.recall import vector  # noqa: E402

HERE = Path(__file__).resolve().parent
K = 3  # Recall@K


def _load() -> dict:
    return json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))


def _seed(mind, memories: list[dict]) -> dict[str, str]:
    slug_to_id: dict[str, str] = {}
    for m in memories:
        node = mind.remember(m["content"], kind=m["kind"], title=m["title"], tags=m.get("tags", []))
        slug_to_id[m["slug"]] = node.id
    return slug_to_id


def _rank_of(hits, want_id: str) -> int:
    """want_id kaçıncı sırada (1-tabanlı); yoksa 0."""
    for i, hit in enumerate(hits, 1):
        if hit.item.id == want_id:
            return i
    return 0


def run() -> dict:
    data = _load()
    tmp = Path(tempfile.mkdtemp())
    mind = open_mind(tmp / "mind", tmp / "sessions", "eval")
    slug_to_id = _seed(mind, data["memories"])

    # Isınma: imza indeksi ilk recall'da kuruluyor, gecikmeye karışmasın.
    mind.recall("ısınma sorgusu", limit=8)

    mem_rows: list[dict] = []   # hafıza gerektiren
    non_rows: list[dict] = []   # boş dönmesi gereken
    latencies: list[float] = []

    sigs = mind.store.index._sigs  # id -> imza (RAM)

    def sig_sim(query: str, hits) -> float:
        """Dönen adaylar içinde en yüksek SimHash benzerliği (0..1).

        `score` sıra-tabanlı aktivasyon; eşik için anlamsız. İmza benzerliği
        normalize bir sinyal — asıl soru bunun ayırıp ayırmadığı.
        """
        q = vector.signature(query)
        best = 0.0
        for h in hits:
            v = sigs.get(h.item.id)
            if v:
                best = max(best, vector.similarity(q, v))
        return best

    for item in data["queries"]:
        q = item["q"]
        t0 = time.perf_counter()
        hits = mind.recall(q, limit=8)
        latencies.append((time.perf_counter() - t0) * 1000)

        top1 = hits[0].score if hits else 0.0
        sim = sig_sim(q, hits)
        if item["expect"] is None:
            non_rows.append({"q": q, "top1": top1, "sim": sim})
        else:
            want = slug_to_id[item["expect"]]
            rank = _rank_of(hits, want)
            tokens = sum(len(h.item.content) // 4 for h in hits[:K])
            mem_rows.append({"q": q, "type": item["type"], "rank": rank,
                             "top1": top1, "sim": sim, "tokens": tokens})

    return _report(mem_rows, non_rows, latencies)


def _report(mem_rows, non_rows, latencies) -> dict:
    n_mem = len(mem_rows)
    recall_at_1 = sum(r["rank"] == 1 for r in mem_rows) / n_mem
    recall_at_k = sum(0 < r["rank"] <= K for r in mem_rows) / n_mem
    mrr = sum(1.0 / r["rank"] for r in mem_rows if r["rank"]) / n_mem

    # Tür kırılımı: hangi sorgu türü tutuyor, hangisi tutmuyor.
    by_type: dict[str, list[int]] = {}
    for r in mem_rows:
        by_type.setdefault(r["type"], []).append(1 if 0 < r["rank"] <= K else 0)

    # Eşik taraması — blueprint'in "en önemli tek satırı". Hangi eşikte
    # hafıza-gerekmeyenlerin %95'i boş döner, o eşikte recall@K ne olur?
    # İki aday sinyal karşılaştırılıyor: sıra-tabanlı aktivasyon (score) ve
    # normalize imza benzerliği (sim). İyi bir eşik, ancak sinyal ikisini
    # ayırıyorsa mümkün.
    def _sweep(field: str):
        out = []
        for i in range(0, 101, 2):
            t = i / 100
            empty_acc = sum(r[field] < t for r in non_rows) / len(non_rows)
            gated = sum(0 < r["rank"] <= K and r[field] >= t for r in mem_rows) / n_mem
            out.append({"t": t, "empty_acc": empty_acc, "recall": gated})
        return out

    sweep = _sweep("top1")
    sweep_sim = _sweep("sim")
    target = next((s for s in sweep if s["empty_acc"] >= 0.95), sweep[-1])
    target_sim = next((s for s in sweep_sim if s["empty_acc"] >= 0.95), sweep_sim[-1])

    return {
        "n_memory": n_mem,
        "n_none": len(non_rows),
        "recall@1": recall_at_1,
        "recall@%d" % K: recall_at_k,
        "mrr": mrr,
        "by_type": {k: sum(v) / len(v) for k, v in by_type.items()},
        "latency_ms": {
            "mean": statistics.mean(latencies),
            "p50": statistics.median(latencies),
            "p95": sorted(latencies)[int(len(latencies) * 0.95)],
            "max": max(latencies),
        },
        "avg_injected_tokens": statistics.mean(r["tokens"] for r in mem_rows),
        "calibration": target,
        "calibration_sim": target_sim,
        "sweep": sweep,
        "sweep_sim": sweep_sim,
        "score_dist": {
            "mem_top1_median": statistics.median(r["top1"] for r in mem_rows),
            "none_top1_median": statistics.median(r["top1"] for r in non_rows),
            "none_top1_max": max(r["top1"] for r in non_rows),
            "mem_sim_median": statistics.median(r["sim"] for r in mem_rows),
            "none_sim_median": statistics.median(r["sim"] for r in non_rows),
            "none_sim_max": max(r["sim"] for r in non_rows),
        },
    }


def _print(m: dict) -> None:
    p = lambda label, val: print(f"  {label:<26} {val}")
    print("\n=== neocp recall — Faz 0 baseline ===")
    print(f"  {m['n_memory']} hafıza sorgusu · {m['n_none']} boş-dönüş sorgusu\n")

    print("Retrieval (eşiksiz, ham motor):")
    p("Recall@1", f"{m['recall@1']:.2f}")
    p(f"Recall@{K}", f"{m['recall@%d' % K]:.2f}   (hedef ≥ 0.80)")
    p("MRR", f"{m['mrr']:.3f}")
    print("\n  tür kırılımı (Recall@%d):" % K)
    for t, v in sorted(m["by_type"].items()):
        print(f"    {t:<12} {v:.2f}")

    print("\nGecikme (ms):")
    lat = m["latency_ms"]
    p("ortalama / p50 / p95", f"{lat['mean']:.2f} / {lat['p50']:.2f} / {lat['p95']:.2f}   (hedef ≤ 200)")
    p("enjekte token / sorgu", f"{m['avg_injected_tokens']:.0f}   (hedef ≤ 1200)")

    sd = m["score_dist"]
    print("\nSinyal ayrımı — iyi eşik ancak sinyal hafıza/boş'u ayırırsa mümkün:")
    print("  (yüksek hafıza-ortancası + düşük boş-en-yüksek = temiz ayrım)")
    p("aktivasyon: hafıza / boş-max", f"{sd['mem_top1_median']:.2f} / {sd['none_top1_max']:.2f}")
    p("imza-benzerlik: hafıza / boş-max", f"{sd['mem_sim_median']:.2f} / {sd['none_sim_max']:.2f}")

    def cal(tag, c, sweep):
        print(f"\nEşik kalibrasyonu — {tag} (blueprint adım 3):")
        p("%95 boş-dönüş eşiği", f"{c['t']:.2f}")
        p("  o eşikte boş-dönüş", f"{c['empty_acc']:.2f}")
        p("  o eşikte Recall@%d" % K, f"{c['recall']:.2f}")
        for s in sweep:
            if abs(s["t"] * 100) % 10 == 0:
                bar = "█" * int(s["recall"] * 18)
                gap = "░" * int(s["empty_acc"] * 18)
                print(f"    {s['t']:.2f}  boş[{gap:<18}]  recall[{bar:<18}]")

    cal("aktivasyon (mevcut score)", m["calibration"], m["sweep"])
    cal("imza-benzerlik (SimHash)", m["calibration_sim"], m["sweep_sim"])
    print()


if __name__ == "__main__":
    _print(run())
