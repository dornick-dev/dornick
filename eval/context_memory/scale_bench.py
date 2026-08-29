"""Ölçek benchmark'ı: 100 anı + 60 episode altında önyükleme kalitesi ve token maliyeti.

Soru üç katlı (Fatih'in isteği):
  1. Yanlış şeyler hatırlıyor muyuz? (hava sorusuna borsa gelmemeli)
  2. Bağlam tasarrufu yapıyor muyuz? (tur başına kaç token enjekte ediliyor)
  3. Daha iyi yöntem var mı? (kapıları tek tek oynatıp Pareto'ya bakmak)

Ölçülen yol ÜRÜNÜN KENDİSİ: `mevcut` yöntemi `neocp.loop.select_prime`'ı
çağırıyor; varyantlar aynı mantığın parametrik kopyası ve `mevcut` ile
varsayılan-parametreli kopyanın her sorguda aynı sonucu verdiği doğrulanıyor
(kopya sessizce ayrışırsa benchmark ürünü ölçmüyor demektir — o an patlar).

Çalıştır:  py eval/context_memory/scale_bench.py
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from neocp.loop import (  # noqa: E402
    RECALL_PRIME_FLOOR,
    RECALL_PRIME_HEADER,
    RECALL_PRIME_LIMIT,
    _one_line,
    _query_stems,
    _without_numbers,
    select_prime,
    worth_recalling,
)
from neocp.mind import open_mind  # noqa: E402

HERE = Path(__file__).resolve().parent

# Türkçe için kaba token kestirimi: ~4 karakter / token. Mutlak değeri
# önemli değil — yöntemler AYNI cetvelle kıyaslanıyor.
CHARS_PER_TOKEN = 4.0


def tokens_of(text: str) -> float:
    return len(text) / CHARS_PER_TOKEN


# -- korpus -------------------------------------------------------------


def load_dataset() -> dict[str, Any]:
    return json.loads((HERE / "scale_dataset.json").read_text(encoding="utf-8"))


def build_mind(data: dict[str, Any], root: Path) -> tuple[Any, dict[str, str]]:
    """Anıları ve episode'ları taze bir zihne yazar. slug → node id haritası döner."""
    mind = open_mind(root / "mind", root / "sessions", "bench")
    allowed = {"fact", "preference", "lesson", "procedure", "user", "voice"}
    ids: dict[str, str] = {}
    for memory in data["memories"]:
        node = mind.remember(
            memory["content"],
            kind=memory["kind"] if memory["kind"] in allowed else "fact",
            title=memory["title"],
            tags=list(memory.get("tags") or []),
        )
        ids[memory["slug"]] = node.id
    for episode in data["episodes"]:
        mind.remember(episode["content"], kind="episode", title=episode["title"])
    return mind, ids


# -- yöntemler ----------------------------------------------------------
#
# Her yöntem (mind, sorgu) → (hits, not-metni). Not metni token cetveline
# giren şeyin ta kendisi; bazı yöntemler yalnızca metni kısaltıyor.


def note_text(hits: list[Any], line_cap: int) -> str:
    """Ürünün prime_note biçimi, satır sınırı ayarlanabilir halde."""
    if not hits:
        return ""
    lines = [RECALL_PRIME_HEADER]
    for hit in hits:
        item = hit.item
        body = " ".join((item.content or "").split())
        title = " ".join((item.title or "").split())
        if title and not body.casefold().startswith(title.casefold()[:40]):
            body = f"{title} — {body}"
        lines.append(f"- [{item.kind}] {_one_line(body, line_cap)}")
    return "\n".join(lines)


def matched_stems(item: Any, stems: set[str]) -> int:
    text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
    return sum(1 for stem in stems if stem in text)


def parametric(
    mind: Any,
    user_input: str,
    *,
    limit: int = RECALL_PRIME_LIMIT,
    floor: float = RECALL_PRIME_FLOOR,
    direct_only: bool = True,
    drop_episodes: bool = True,
    ground_min: int = 1,
    ground_ratio: float = 0.0,
    tiered: bool = False,
    lone_score: float = 0.0,
    weigh: float = 0.0,
    gap: float = 0.0,
) -> list[Any]:
    """select_prime'ın ayarlanabilir kopyası. Varsayılanlar ürünle birebir.

    tiered: ≥2 kanıtlı aday varsa yalnız onlar; yoksa tek-kanıt moduna
    düşülür ama o modda en fazla TOP-1 gösterilir (tek zayıf çakışmayla
    beş satır doldurulmaz) ve `lone_score` verildiyse top'un skoru onu
    aşmak zorundadır.
    """
    query = _without_numbers(user_input)
    hits = mind.recall(query, limit=limit)

    trace = getattr(mind, "last_trace", None) or []
    direct = {step.node for step in trace if step.hop == 0}
    if direct_only and not direct:
        return []
    stems = _query_stems(query)

    # Ürün kuralı (28.08): HAM sorgu ≥5 gövdeliyse tek (önek-tekil)
    # gövdeyle tutunan kayıt önyüklemeye giremez. Kopya birebir taşır.
    zengin = len(_query_stems(query, genislet=False)) >= 5

    def _tekil_vuran(item: Any) -> int:
        text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
        vuranlar = [g for g in stems if g in text]
        tekil = [g for g in vuranlar
                 if not any(g != d and d.startswith(g) for d in vuranlar)]
        return len(tekil)

    def need_for(item: Any) -> bool:
        if not stems:
            return True
        got = matched_stems(item, stems)
        if ground_ratio > 0:
            import math

            return got >= max(1, math.ceil(ground_ratio * len(stems)))
        if ground_min > 1:
            return got >= min(ground_min, max(1, len(stems) - 1))
        if not got:
            return False
        return _tekil_vuran(item) >= 2 if zengin else True

    passed = [
        hit
        for hit in hits
        if (not drop_episodes or hit.item.kind != "episode")
        and (not direct_only or hit.item.id in direct)
        and need_for(hit.item)
    ]
    if weigh > 0 and stems:
        # Skor doyuyor (ölçüldü: altın medyan 0.963, sızıntı 0.874 — ayırmıyor)
        # ama skor × kanıt-oranı ayırıyor (0.477 vs 0.167). Eşik çarpıma
        # konuyor; top muafiyeti yalnız kanıtı güçlü top'a (oran ≥ 0.5) —
        # genç hafızada skor çökse de oran yüksek kalıyor.
        def heft(h: Any) -> float:
            return h.score * (matched_stems(h.item, stems) / len(stems))

        best = max(passed, key=heft, default=None)
        passed = [
            h for h in passed
            if heft(h) >= weigh
            or (h is best and matched_stems(h.item, stems) / len(stems) >= 0.5)
        ]
    if tiered and stems:
        strong = [h for h in passed if matched_stems(h.item, stems) >= 2]
        if strong:
            passed = strong
        elif passed:
            lone = max(passed, key=lambda h: h.score)
            passed = [lone] if (lone_score == 0 or lone.score >= lone_score) else []
    if not passed:
        return []
    top = max(passed, key=lambda h: h.score)
    kept = [h for h in passed if h is top or h.score >= floor]
    if gap > 0:
        kept = [h for h in kept if h is top or h.score >= gap * top.score]
    return kept[:limit]


METHODS: dict[str, tuple[Callable[..., list[Any]], int]] = {
    # ad → (seçici, satır sınırı)
    "mevcut": (lambda m, q: select_prime(m, q), 220),
    # Kapısız hâl: süzgeçlerin ne kurtardığını gösteren ablasyon.
    "ciplak": (lambda m, q: parametric(m, q, direct_only=False,
                                       drop_episodes=False, ground_min=0,
                                       floor=0.0), 220),
    # Kuyruk kesme: en güçlünün %45'inin altındakiler düşer.
    "gap45": (lambda m, q: parametric(m, q, gap=0.45), 220),
    # Çift zemin: çok kelimeli sorguda tek kelimelik tesadüf yetmez.
    "zemin2": (lambda m, q: parametric(m, q, ground_min=2), 220),
    # Kısa satır: aynı seçim, yarı token.
    "kisa120": (lambda m, q: select_prime(m, q), 120),
    # Oransal zemin: sorgu gövdelerinin %40'ı kayıtta geçmeli.
    "oran40": (lambda m, q: parametric(m, q, ground_ratio=0.4), 220),
    # Kademeli kanıt: çift kanıtlılar varsa onlar; yoksa tek-kanıtlı top-1.
    "kademe": (lambda m, q: parametric(m, q, tiered=True), 220),
    # Kademeli + tek-kanıt modunda skor şartı.
    "kademe05": (lambda m, q: parametric(m, q, tiered=True, lone_score=0.5), 220),
    # Skor × kanıt-oranı eşiği (teşhis koşusundan türedi).
    "carpim16": (lambda m, q: parametric(m, q, weigh=0.16), 220),
    "carpim20": (lambda m, q: parametric(m, q, weigh=0.20), 220),
    "carpim24": (lambda m, q: parametric(m, q, weigh=0.24), 220),
    # Ruhta tam gövdesiyle duran kayıt yeniden enjekte edilmez: model onu
    # oturum başından beri bağlamında taşıyor. Bilgi kaybı sıfır.
    "ruhdisi": (lambda m, q: [h for h in select_prime(m, q)
                              if h.item.id not in SOUL_IDS], 220),
    # IDF ağırlıklı kanıt eşiği: yaygın kelime tuzak açmasın.
    "idf16": (lambda m, q: idf_pick(m, q, 0.16), 220),
    "idf24": (lambda m, q: idf_pick(m, q, 0.24), 220),
    "idf32": (lambda m, q: idf_pick(m, q, 0.32), 220),
    # Sayı-ağırlıklı sorguda sayılar atılmaz. (lambda şart: işlev aşağıda
    # tanımlanıyor, sözlük kurulurken adı henüz yok.)
    "sayili": (lambda m, q: keep_numbers_pick(m, q), 220),
    # Cümle-duyarlı olmayan düz 160 kırpma (token ölçümü için).
    "kisa160": (lambda m, q: select_prime(m, q), 160),
}

# Ruhun tam gövdeyle bağlama koyduğu kayıtlar (main'de dolduruluyor).
# procedure girmiyor: ruhta yalnız başlığı var, gövdesi prime'da hâlâ değerli.
SOUL_IDS: set[str] = set()

# Gövde → korpusta kaç anıda geçtiği (IDF deneyi için; main dolduruyor).
STEM_DF: dict[str, int] = {}
CORPUS_N: int = 1


def idf_ratio(item: Any, stems: set[str]) -> float:
    """IDF ağırlıklı kanıt oranı: nadir gövde çok, yaygın gövde az sayılır.

    Düz oran "Konya" gibi korpusun her yerinde geçen bir kelimeyle tuzak
    açıyordu; IDF o kelimenin ağırlığını düşürür. Ağırlık log(1 + N/df).
    """
    import math

    if not stems:
        return 1.0
    text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
    total = got = 0.0
    for stem in stems:
        weight = math.log(1 + CORPUS_N / (STEM_DF.get(stem, 0) + 1))
        total += weight
        if stem in text:
            got += weight
    return got / total if total else 0.0


def idf_pick(mind: Any, user_input: str, threshold: float) -> list[Any]:
    """carpim ailesinin IDF'li hali: eşik skor × IDF-oranına konur."""
    query = _without_numbers(user_input)
    hits = select_prime(mind, user_input)
    stems = _query_stems(query)
    if not stems or not hits:
        return hits

    def heft(h: Any) -> float:
        return h.score * idf_ratio(h.item, stems)

    best = max(hits, key=heft)
    return [h for h in hits
            if heft(h) >= threshold
            or (h is best and idf_ratio(h.item, stems) >= 0.5)]


def keep_numbers_pick(mind: Any, user_input: str) -> list[Any]:
    """Sayı-koruma: sorgu sayı-ağırlıklıysa sayılar atılmaz.

    Sayı atma BTC-fiyat sızıntısına karşı kondu; ama "404195 hangi register"
    gibi sorguda aranan şeyin kendisi sayı — atınca numeric sınıfı 0.75'te
    takılıyor. Kural: sayısız halde <2 içerik gövdesi kalıyorsa sayılar kalır.
    """
    stripped = _without_numbers(user_input)
    if len(_query_stems(stripped)) >= 2:
        return select_prime(mind, user_input)
    # loop.select_prime her zaman sayı atar; sayılı yol için parametrik
    # kopyada sorguyu olduğu gibi kullanıyoruz.
    hits = mind.recall(user_input, limit=RECALL_PRIME_LIMIT)
    trace = getattr(mind, "last_trace", None) or []
    direct = {step.node for step in trace if step.hop == 0}
    if not direct:
        return []
    stems = _query_stems(user_input)
    passed = [h for h in hits
              if h.item.kind != "episode" and h.item.id in direct]
    if not passed:
        return []
    top = max(passed, key=lambda h: h.score)
    return [h for h in passed
            if h is top or h.score >= RECALL_PRIME_FLOOR][:RECALL_PRIME_LIMIT]


# -- ölçüm --------------------------------------------------------------


def run_method(
    name: str,
    data: dict[str, Any],
    mind: Any,
    ids: dict[str, str],
) -> dict[str, Any]:
    select, line_cap = METHODS[name]
    slug_of = {node_id: slug for slug, node_id in ids.items()}

    hit_recall = []       # altınlı sorgular: en az bir altın geldi mi
    coverage = []         # altınların ne kadarı geldi
    precision = []        # gelenlerin ne kadarı altın
    silence_ok = []       # altınsız sorgular: sessiz kalındı mı
    leaks: list[str] = []  # sızıntı örnekleri (rapora)
    wrongs: list[str] = []
    token_costs = []
    times = []
    by_type: dict[str, list[float]] = {}

    for query in data["queries"]:
        gold = {ids[s] for s in query["gold"]}
        started = time.perf_counter()
        # Ürün akışındaki ilk kapı: değmeyecek mesajda zihin hiç açılmıyor.
        hits = select(mind, query["q"]) if worth_recalling(query["q"]) else []
        times.append((time.perf_counter() - started) * 1000)
        note = note_text(hits, line_cap)
        token_costs.append(tokens_of(note))

        got = {hit.item.id for hit in hits}
        kind = query["type"]

        if gold:
            # Ruhta duran altın zaten bağlamda: hiçbir yöntem onu enjekte
            # etmek zorunda değil — hepsine adil sayılıyor.
            satisfied = got | (gold & SOUL_IDS)
            ok = 1.0 if satisfied & gold else 0.0
            hit_recall.append(ok)
            coverage.append(len(satisfied & gold) / len(gold))
            if got:
                precision.append(len(got & gold) / len(got))
                for wrong in got - gold:
                    wrongs.append(f"{kind} «{query['q'][:40]}» → {slug_of.get(wrong, 'EPISODE')}")
            by_type.setdefault(kind, []).append(ok)
        else:
            quiet = 1.0 if not got else 0.0
            silence_ok.append(quiet)
            if got:
                sample = ", ".join(slug_of.get(g, "EPISODE") for g in list(got)[:3])
                leaks.append(f"{kind} «{query['q'][:40]}» → {sample}")
            by_type.setdefault(kind, []).append(quiet)

    mean = lambda xs: statistics.fmean(xs) if xs else 0.0
    tokens_avg = mean(token_costs)
    recall = mean(hit_recall)
    return {
        "name": name,
        "recall": recall,
        "coverage": mean(coverage),
        "precision": mean(precision),
        "silence": mean(silence_ok),
        "tokens": tokens_avg,
        # Verim: 1000 token başına kaç "isabetli sorgu". Amaç min bağlam
        # max isabet; tek sayıya bunu sıkıştırıyor.
        "verim": (recall * 1000 / tokens_avg) if tokens_avg else float("inf"),
        "p95_ms": sorted(times)[int(len(times) * 0.95) - 1],
        "by_type": {k: mean(v) for k, v in sorted(by_type.items())},
        "leaks": leaks[:10],
        "wrongs": wrongs[:10],
    }


def repeat_bench(data: dict[str, Any], mind: Any, ids: dict[str, str]) -> dict[str, float]:
    """Aynı konuda 12 turluk konuşma: aynı anı kaç kez yeniden enjekte oluyor?

    Tur-içi tekrar ayrı bir israf kanalı: model aynı hatırayı 12 kez okuyor.
    """
    talk = [q["q"] for q in data["queries"] if q["type"] in ("exact", "continuation")][:12]
    plain, seen_costs = 0.0, 0.0
    seen: set[str] = set()
    for q in talk:
        hits = select_prime(mind, q)
        plain += tokens_of(note_text(hits, 220))
        fresh = [h for h in hits if h.item.id not in seen]
        seen.update(h.item.id for h in hits)
        seen_costs += tokens_of(note_text(fresh, 220))
    return {"tekrarli": plain, "tekrarsiz": seen_costs,
            "tasarruf": 1 - (seen_costs / plain) if plain else 0.0}


def main() -> None:
    data = load_dataset()
    print(f"korpus: {len(data['memories'])} anı + {len(data['episodes'])} episode, "
          f"{len(data['queries'])} sorgu\n")

    with tempfile.TemporaryDirectory() as tmp:
        mind, ids = build_mind(data, Path(tmp))

        # IDF deneyi için korpus gövde-sıklığı (anılar + episode'lar).
        global CORPUS_N
        texts = [f"{m['title']} {m['content']} {' '.join(m.get('tags') or [])}"
                 for m in data["memories"]]
        texts += [f"{e['title']} {e['content']}" for e in data["episodes"]]
        CORPUS_N = len(texts)
        STEM_DF.clear()
        seen_stems = {s for q in data["queries"]
                      for s in _query_stems(_without_numbers(q["q"]))}
        for stem in seen_stems:
            STEM_DF[stem] = sum(1 for t in texts if stem in t.casefold())

        # Ürünün ruh seçimiyle birebir: tam gövdesi bağlama giren türler.
        soul = mind.soul()
        SOUL_IDS.clear()
        SOUL_IDS.update(m.id for group in
                        (soul.user, soul.preferences, soul.lessons, soul.voice)
                        for m in group)
        print(f"ruhta tam gövdeyle: {len(SOUL_IDS)} kayıt\n")

        # Koruma: parametrik kopya varsayılanlarla ürüne eşit mi?
        for query in data["queries"]:
            a = {h.item.id for h in select_prime(mind, query["q"])}
            b = {h.item.id for h in parametric(mind, query["q"])}
            assert a == b, f"kopya üründen ayrıştı: {query['q']!r} {a} != {b}"
        print("koruma: parametrik kopya == ürün (tüm sorgular)\n")

        rows = [run_method(name, data, mind, ids) for name in METHODS]

        head = f"{'yöntem':<10} {'isabet':>7} {'kapsam':>7} {'kesinlik':>9} {'sessizlik':>10} {'tok/sorgu':>10} {'verim':>7} {'p95ms':>6}"
        print(head)
        print("-" * len(head))
        for r in rows:
            print(f"{r['name']:<10} {r['recall']:>7.2f} {r['coverage']:>7.2f} "
                  f"{r['precision']:>9.2f} {r['silence']:>10.2f} "
                  f"{r['tokens']:>10.1f} {r['verim']:>7.1f} {r['p95_ms']:>6.2f}")

        print("\ntür kırılımı (isabet ya da sessizlik):")
        kinds = sorted({k for r in rows for k in r["by_type"]})
        print(f"{'yöntem':<10} " + " ".join(f"{k:>12}" for k in kinds))
        for r in rows:
            print(f"{r['name']:<10} " + " ".join(
                f"{r['by_type'].get(k, float('nan')):>12.2f}" for k in kinds))

        for r in rows:
            if r["leaks"] or r["wrongs"]:
                print(f"\n{r['name']} sızıntıları:")
                for line in r["leaks"] + r["wrongs"]:
                    print("  !", line)

        echo = repeat_bench(data, mind, ids)
        print(f"\n12 turluk konuşmada tekrar: {echo['tekrarli']:.0f} tok → "
              f"tekrarsız {echo['tekrarsiz']:.0f} tok "
              f"(tasarruf %{echo['tasarruf'] * 100:.0f})")

        # Karşılaştırma çapası: her şeyi göndermek neye mal olurdu?
        everything = sum(tokens_of(m["content"]) + tokens_of(m["title"])
                        for m in data["memories"])
        print(f"\nçapa: TÜM anıları her turda göndermek ≈ {everything:.0f} tok/sorgu")

        # Windows: açık SQLite bağlantısı tmp klasörünün silinmesini engelliyor.
        mind.store.close()


if __name__ == "__main__":
    main()
