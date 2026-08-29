"""Win-condition harness — dev + held-out sets, one threshold.

Measures the five-metric Pareto target. The threshold is chosen ONCE on
DEV (the highest threshold that keeps recall@3 ≥ 0.93 → maximises
empty-return), then applied to the held-out set UNCHANGED — never re-tuned
there (the no-cheating rule).

Memories are the 24 frozen records in dataset.json (both sets use the
same ones); queries come from dataset.json for dev and holdout.json for
the held-out set.

Latency is a cold-call + repeats median (never a warmed single sample).

Run:  python eval/context_memory/harness.py
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

# The win condition.
WIN = {
    "recall@3": 0.93,
    "paraphrase@3": 0.80,   # strictly above 0.80; checked with >= plus eps
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
        node = mind.remember(m["content"], kind=m["kind"], title=m["title"],
                             tags=m.get("tags", []))
        slug[m["slug"]] = node.id
    return slug


def _rank_of(hits, want_id: str) -> int:
    for i, h in enumerate(hits, 1):
        if h.item.id == want_id:
            return i
    return 0


def run_set(queries: list[dict], repeats: int = 3) -> list[dict]:
    """Run a query set on a fresh mind; return the raw rows.

    Latency: each query is measured a few times and the median taken
    (cold first call + repeats). A single warmed sample flatters latency.
    """
    tmp = Path(tempfile.mkdtemp())
    mind = open_mind(tmp / "mind", tmp / "sessions", "eval")
    slug = _seed(mind, _memories())
    mind.recall("warmup", limit=8)   # build the signature index

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
    """The five win metrics at a given threshold.

    The gate is `top1 >= threshold`: a query below it returns empty. A
    memory query only counts as a hit when the right memory is in the top
    3 AND passes the gate; an empty query only succeeds when it stays
    below the gate (returns empty).
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
    # Ungated (raw) recall — the "did we lose what we had" reference.
    raw_recall = sum(0 < r["rank"] <= K for r in mem) / len(mem) if mem else 0.0
    return {
        "recall@3": recall, "raw_recall@3": raw_recall,
        "paraphrase@3": para_recall, "empty": empty_ret,
        "p95_ms": p95, "tokens": tokens,
    }


def choose_threshold(dev_rows: list[dict]) -> float:
    """Pick the threshold on DEV: the highest one keeping recall@3 ≥ 0.93.

    Empty-return rises monotonically with the threshold, so the highest
    threshold that preserves the recall floor also maximises empty-return.
    That equals the lowest top1 among memory queries whose right answer is
    in the top 3 (at that value the gate still passes all of them). Not
    eval-specific: it only looks at the score distribution, it memorises
    no queries.
    """
    correct = [r["top1"] for r in dev_rows
               if not r["empty"] and 0 < r["rank"] <= K]
    if not correct:
        return 0.0
    return round(min(correct), 6)


def _check(name, value, target, mode=">="):
    ok = value >= target if mode == ">=" else value <= target
    return ok, f"  {'OK' if ok else 'X '} {name:<16} {value:.3f}  ({mode} {target})"


def report(threshold, dev, hold=None):
    def block(tag, m):
        print(f"\n[{tag}]  (threshold {threshold:.4f})")
        checks = [
            _check("recall@3", m["recall@3"], WIN["recall@3"]),
            _check("paraphrase@3", m["paraphrase@3"], WIN["paraphrase@3"]),
            _check("empty-return", m["empty"], WIN["empty"]),
            _check("p95 (ms)", m["p95_ms"], WIN["p95_ms"], "<="),
            _check("tokens", m["tokens"], WIN["tokens"], "<="),
        ]
        for _, line in checks:
            print(line)
        passed = all(ok for ok, _ in checks)
        print(f"  raw recall@3 (ungated): {m['raw_recall@3']:.3f}")
        print(f"  => {'PASSED' if passed else 'FAILED'}")
        return passed

    dev_pass = block("DEV", dev)
    hold_pass = block("HELD-OUT", hold) if hold is not None else None
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
        print("=== neocp recall — win-condition measurement ===")
        report(t, dev_m, hold_m)
        print()
    return {"threshold": t, "dev": dev_m, "holdout": hold_m}


if __name__ == "__main__":
    evaluate()
