# -*- coding: utf-8 -*-
"""Personal fine-tuning loop — the fully local, overnight learning cycle.

Flow (every stage is safe on its own; an interrupted run continues the
next night):

  1. HARVEST — memories added since the last run are pulled from neo's
     mind (recall.db, READ-ONLY; episodes excluded: those are transcripts).
  2. LABEL — neo's own main model (config.json model + keys.json key)
     produces 3 question styles + topic terms per memory. The "night
     teacher": brain by day, labeler by night.
  3. FINE-TUNE — once enough untrained personal pairs accumulate, training
     continues from the base checkpoint at a low learning rate. Against
     forgetting, base-corpus examples are mixed in (a replay buffer).
  4. EXAM GATE — candidates race the deployed model in the SAME run:
     TR scale bench + EN probe + personal probe. A regressing candidate is
     DISCARDED; the deployed model stays.
  5. DEPLOY — a passing candidate is written to .neocp/taban.npz; the
     product prefers that file over the stock model (src/neocp/recall/taban.py).

Why nightly and not hourly: an hour of new data is a handful of examples —
weak signal, real forgetting risk, and fan noise. Accumulation threshold
plus the overnight gap is the right balance.

Called by the product (src/neocp/tanima.py) as:
  personal_loop.py --neocp <product-root> [--aygit cpu|cuda]
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Product root: .neocp state, src and eval are derived from it. The rig
# normally lives inside the product tree (training/ next to src/); the
# product passes its own root explicitly with `--neocp <path>`.
PRODUCT = ROOT.parent
if "--neocp" in sys.argv:
    PRODUCT = Path(sys.argv[sys.argv.index("--neocp") + 1]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import common  # noqa: E402
from model.inference import QueryExpander  # noqa: E402

# common's exam wrapper also derives paths from the product root; hand it
# the root we resolved — there must not be two separate truths.
common.PRODUCT = PRODUCT

DATA = ROOT / "data"
CHECKPOINTS = ROOT / "checkpoints"
STATE = DATA / "personal_state.json"
PERSONAL_CORPUS = DATA / "personal_corpus.jsonl"
LOG = DATA / "personal_log.md"
DB = PRODUCT / ".neocp" / "mind" / "recall.db"
DEPLOYED = PRODUCT / ".neocp" / "taban.npz"       # the personal model goes here
STOCK = PRODUCT / "src" / "neocp" / "assets" / "taban.npz"


def _base_checkpoint() -> Path:
    """The seed for fine-tuning: a locally trained best.pt wins over the
    distributed base.pt."""
    best = CHECKPOINTS / "best.pt"
    return best if best.exists() else CHECKPOINTS / "base.pt"


THRESHOLD = 150     # fine-tune once this many untrained personal pairs exist
RUN_CAP = 400       # at most this many memories labeled per night
# Lessons from three runs: (a) 3e-5 + 23 epochs -> personal 0.82 but the
# general model was crushed; (b) 1e-5 + 4 epochs -> general preserved, zero
# learning; (c) freezing the lower half froze the tied output layer too and
# learning stalled. The fix is not lr/epoch tuning but WISE-FT: train once
# aggressively, then BLEND with the base weights at several ratios and send
# every blend through the gate — the retention/learning trade-off is chosen
# at blend time, not at training time.
LEARNING_RATE = 3e-5
REPLAY_RATIO = 6            # base examples mixed in per personal example
REPLAY_SILENCE_SHARE = 0.25  # at least this share of the replay buffer is 'susma'
EPOCHS = 15                 # passes over the mixture
PERSONAL_WEIGHT = 2         # how many times each personal example enters the mix
ALPHAS = (0.35, 0.55, 0.75)  # blend candidates: the fine-tune's share


# -- state --------------------------------------------------------------------

def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"son_created": "", "egitilen": 0}


def write_state(d: dict) -> None:
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def log(line: str) -> None:
    stamp = datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"- {stamp} — {line}\n")
    print(line)


# -- 1) harvest ---------------------------------------------------------------

def harvest(last_created: str) -> list[dict]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id, kind, title, body, created FROM node "
            "WHERE kind != 'episode' AND deleted = 0 AND created > ? "
            "ORDER BY created LIMIT ?",
            (last_created, RUN_CAP),
        ).fetchall()
    finally:
        con.close()
    return [{"id": i, "kind": k, "title": t or "", "body": b or "", "created": c}
            for i, k, t, b, c in rows]


# -- 2) labeling (the main model as teacher) ----------------------------------

# The prompt is Turkish on purpose: it labels a Turkish-first user's
# memories and asks for one English paraphrase (S4) per record.
PROMPT = """Aşağıda bir kişisel hafıza kaydı var. Bu kayda dair kullanıcının \
sorabileceği 4 FARKLI soru yaz: S1 doğrudan, S2 eşanlamlı kelimelerle \
(kayıttaki anahtar kelimeleri kullanMA), S3 kısa/belirsiz, S4 İNGİLİZCE \
(kullanıcı aynı şeyi İngilizce soruyor). Sonra kaydın konu terimlerini ver \
(T: 2-6 kelime, küçük harf, kayıt dilinde). BAŞKA HİÇBİR ŞEY yazma.

Biçim:
S1: ...
S2: ...
S3: ...
S4: ...
T: terim1 terim2 ...

Kayıt: {title}
{body}"""


def parse_labels(text: str) -> list[tuple[str, str]]:
    """Unpacks S1..S4 + T lines into (question, terms) pairs."""
    questions, terms = [], ""
    for line in text.splitlines():
        line = line.strip()
        if line[:3] in ("S1:", "S2:", "S3:", "S4:"):
            questions.append(line[3:].strip())
        elif line[:2] == "T:":
            terms = " ".join(line[2:].split()[:6]).casefold()
    if not terms or not questions:
        return []
    return [(q, terms) for q in questions if len(q) > 8]


def _product_teacher() -> tuple[str, str, str] | None:
    """neo's SELECTED model: (model name, base_url, key).

    Whatever model the product talks to, the night teacher is the same one:
    when the user switches models the loop follows automatically, and no
    second model setting rots here. A key is only needed for OpenRouter;
    local endpoints like LM Studio are keyless (no Authorization sent).
    """
    try:
        cfg = json.loads((PRODUCT / ".neocp" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    model = cfg.get("model") or {}
    name = str(model.get("name") or "").strip()
    url = str(model.get("base_url") or "").strip()
    if not name or not url:
        return None
    key = ""
    if "openrouter" in url:
        try:
            keys = json.loads((PRODUCT / ".neocp" / "keys.json").read_text(encoding="utf-8"))
            key = str(keys.get("OPENROUTER_API_KEY") or "")
        except (OSError, ValueError):
            return None
        if not key:
            return None
    return name, url, key


def _ask_selected(name: str, url: str, key: str, prompt: str) -> str:
    """One request to the selected model — OpenAI-compatible chat endpoint."""
    body = json.dumps({
        "model": name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.6,
        # Live test: qwen in thinking mode spends the token budget on hidden
        # reasoning and the CONTENT comes back EMPTY. With reasoning off the
        # S1..S4/T lines arrive clean (~25 s/request).
        "reasoning": {"enabled": False},
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.load(r)
    return (out["choices"][0]["message"]["content"] or "").strip()


def label(memories: list[dict]) -> list[dict]:
    """Teacher = neo's selected model; falls back to the hosted teacher
    (teacher.py) if that fails.

    If the selected model returns empty/unparseable content or errors 3
    times in a row, we fall back. If there is no fallback either, the
    harvest is abandoned — the watermark does not advance, so no memory is
    lost; next night it is retried.
    """
    selected = _product_teacher()
    fallback = None
    try:
        import teacher
        fallback = teacher.ask_teacher
    except ImportError:
        pass
    if selected is None and fallback is None:
        log("labeling skipped: no selected model and no teacher.py "
            "(data will be labeled later)")
        return []

    pairs: list[dict] = []
    streak = 0   # consecutive empty/error responses from the selected model
    errors = 0   # fallback teacher errors
    for memory in memories:
        prompt = PROMPT.format(title=memory["title"], body=memory["body"][:600])
        fresh: list[tuple[str, str]] = []
        if selected is not None:
            try:
                fresh = parse_labels(_ask_selected(*selected, prompt))
            except Exception:
                fresh = []
            if fresh:
                streak = 0
            else:
                streak += 1
                if streak >= 3:
                    if fallback is not None:
                        log("selected model empty/unreachable 3x — "
                            "falling back to the hosted teacher")
                        selected = None
                    else:
                        log("labeling abandoned: selected model empty 3x, "
                            "no fallback — harvest deferred to next night")
                        return []
        if selected is None and not fresh and fallback is not None:
            try:
                fresh = parse_labels(fallback([{"role": "user", "content": prompt}],
                                              max_tokens=400, temperature=0.6))
            except Exception:
                errors += 1
                if errors >= 3:
                    log(f"labeling cut short: teacher unreachable {errors}x")
                    break
                continue
        for question, terms in fresh:
            pairs.append({"girdi": question, "cikti": terms,
                          "tur": "kisisel", "kaynak": memory["id"]})
    return pairs


# -- 3) fine-tuning -----------------------------------------------------------

def fine_tune(personal: list[dict]) -> Path | None:
    try:
        import torch
    except ImportError:
        log("fine-tune skipped: no torch (data keeps accumulating)")
        return None
    from model.architecture import BaseModel, Config, encode

    ck = torch.load(_base_checkpoint(), map_location="cpu")
    cfg = Config(**ck["ayar"])
    model = BaseModel(cfg)
    model.load_state_dict(ck["model"])

    # Personal fine-tuning ALWAYS runs on CPU: the user's GPU may be
    # holding a local language model, and VRAM contention reads as "my
    # computer froze". Measured ~5 min on CPU, and the process is already
    # low priority — imperceptible. A developer can force `--aygit cuda`.
    device = "cpu"
    for flag in ("--aygit", "--device"):
        if flag in sys.argv:
            device = sys.argv[sys.argv.index(flag) + 1]
    model.to(device).train()

    # Replay buffer: base-corpus examples brake forgetting. Silence
    # examples are protected separately — silence bled worst in run one.
    base, silences = [], []
    for name in ("corpus.jsonl", "corpus_en.jsonl"):
        path = DATA / name
        if path.exists():
            for l in path.read_text(encoding="utf-8").splitlines():
                r = json.loads(l)
                (silences if r.get("tur") == "susma" else base).append(r)
    rng = random.Random(41)
    replay_n = min(len(base), len(personal) * REPLAY_RATIO)
    silence_n = min(len(silences), int(replay_n * REPLAY_SILENCE_SHARE))
    mix = [(r["girdi"], r["cikti"]) for r in personal] * PERSONAL_WEIGHT
    mix += [(r["girdi"], r["cikti"]) for r in rng.sample(base, replay_n - silence_n)]
    mix += [(r["girdi"], r["cikti"]) for r in rng.sample(silences, silence_n)]
    rng.shuffle(mix)
    encoded = [encode(g, c, cfg.ctx) for g, c in mix]

    # Batch layout mirrors 03_train.batch exactly: PAD-filled X/Y, the loss
    # in the model's own `loss` method (input part masked there).
    steps = max(100, EPOCHS * len(encoded) // 16)
    opt = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    PAD = 259
    for _ in range(steps):
        batch = [encoded[rng.randrange(len(encoded))] for _ in range(16)]
        width = max(len(g) for g, _ in batch)
        x = torch.full((len(batch), width), PAD, dtype=torch.long)
        y = torch.full((len(batch), width), PAD, dtype=torch.long)
        for j, (g, t) in enumerate(batch):
            x[j, :len(g)] = torch.tensor(g)
            y[j, :len(t)] = torch.tensor(t)
        loss = model.loss(x.to(device), y.to(device))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

    model.cpu().eval()
    target = CHECKPOINTS / "personal.pt"
    torch.save({"ayar": ck["ayar"], "model": model.state_dict()}, target)
    log(f"fine-tune done: {len(personal)} personal + {len(mix)-len(personal)} "
        f"replay, {steps} steps ({device})")
    return target


# -- 4) blend + exam gate + 5) deploy ----------------------------------------

def blend_npz(ft_ck: Path, alpha: float, target: Path) -> None:
    """Wise-FT: theta = alpha * fine_tune + (1 - alpha) * base, exported to npz."""
    import torch
    base = torch.load(_base_checkpoint(), map_location="cpu")
    ft = torch.load(ft_ck, map_location="cpu")
    sd = {k: ((1 - alpha) * base["model"][k].float()
              + alpha * ft["model"][k].float())
          for k in base["model"]}
    mid = CHECKPOINTS / f"blend_{int(alpha * 100)}.pt"
    import copy
    torch.save({"ayar": copy.deepcopy(base["ayar"]), "model": sd}, mid)
    common.export_npz(mid, target)


def product_personal_score(expanders: dict, personal: list[dict]) -> dict[str, float]:
    """The PRODUCT-TRUTH personal metric: search the user's own mind copy.

    Word-stem matching was a proxy and it misled: an expansion can miss the
    label yet still find the right memory (or the reverse). Here every
    personal question is searched with select_prime over the user's REAL
    memories, and we count whether the source memory comes back — the very
    thing the product will live. The database is a copy, opened read-only
    in spirit.
    """
    import shutil
    import tempfile

    sys.path.insert(0, str(PRODUCT / "src"))
    from neocp.loop import select_prime
    from neocp.mind.store import Mind

    samples = random.Random(7).sample(personal, min(60, len(personal)))
    result: dict[str, float] = {}
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for suffix in ("", "-wal", "-shm"):
            source = DB.parent / f"recall.db{suffix}"
            if source.exists():
                shutil.copy2(source, t / f"recall.db{suffix}")
        mind = Mind(t, t)
        try:
            for name, x in expanders.items():
                hit = 0
                for r in samples:
                    extra = x.expand(r["girdi"])
                    q = f"{r['girdi']} {extra}".strip() if extra else r["girdi"]
                    try:
                        hits = select_prime(mind, q)
                    except Exception:
                        hits = []
                    hit += any(h.item.id == r.get("kaynak") for h in hits)
                result[name] = hit / max(1, len(samples))
        finally:
            mind.store.close()
    return result


def gate_and_deploy(ft_ck: Path, personal: list[dict]) -> bool:
    """Every blend ratio is a candidate; all race the deployed model in the
    SAME run.

    Of those that pass, the one that learned the personal data best is
    deployed. If none passes, the deployed model stays — a bad night cannot
    break the product.
    """
    deployed_path = DEPLOYED if DEPLOYED.exists() else STOCK
    candidates: dict[str, QueryExpander] = {}
    for alpha in ALPHAS:
        npz = CHECKPOINTS / f"personal_a{int(alpha * 100)}.npz"
        blend_npz(ft_ck, alpha, npz)
        candidates[f"a{int(alpha * 100)}"] = QueryExpander(npz)

    expanders: dict = {"deployed": QueryExpander(deployed_path), **candidates}
    tr = common.tr_exam(expanders)
    en = {name: common.en_probe(x) for name, x in expanders.items()}

    personal_score = product_personal_score(expanders, personal)

    d = "deployed"
    for name in expanders:
        log(f"  {name:<8} TR {tr[name]['recall']:.2f} · silence {tr[name]['silence']:.2f} "
            f"· EN topic {en[name]['topic']:.2f} · EN silence {en[name]['silence']:.2f} "
            f"· personal {personal_score[name]:.2f}")

    # Margins follow probe resolution: the EN probe is 16/6 questions — a
    # margin narrower than half a question mistakes measurement noise for
    # regression. Margin ~= 2 questions.
    passing = [
        name for name in candidates
        if tr[name]["recall"] >= tr[d]["recall"] - 0.03
        and tr[name]["silence"] >= tr[d]["silence"] - 0.07
        and en[name]["topic"] >= en[d]["topic"] - 0.13
        and en[name]["silence"] >= en[d]["silence"] - 0.17
        # Product truth: the candidate must find STRICTLY more correct
        # memories in the user's mind than the deployed model — a tie is
        # not worth a change.
        and personal_score[name] > personal_score[d]
    ]
    if not passing:
        log("GATE REJECTED: no blend passed, deployed model stays")
        return False
    chosen = max(passing, key=lambda name: personal_score[name])
    DEPLOYED.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(CHECKPOINTS / f"personal_{chosen}.npz", DEPLOYED)
    log(f"DEPLOYED: {chosen} (personal {personal_score[chosen]:.2f}) -> {DEPLOYED}")
    return True


# -- main flow ----------------------------------------------------------------

def main() -> None:
    state = read_state()
    memories = harvest(state.get("son_created", ""))
    if memories:
        pairs = label(memories)
        if pairs:
            PERSONAL_CORPUS.parent.mkdir(parents=True, exist_ok=True)
            with PERSONAL_CORPUS.open("a", encoding="utf-8") as f:
                for r in pairs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            state["son_created"] = memories[-1]["created"]
            write_state(state)
            log(f"harvest: {len(memories)} memories -> {len(pairs)} pairs "
                f"(total {sum(1 for _ in PERSONAL_CORPUS.open(encoding='utf-8'))})")
    else:
        print("no new memories")

    if not PERSONAL_CORPUS.exists():
        return
    all_pairs = [json.loads(l)
                 for l in PERSONAL_CORPUS.read_text(encoding="utf-8").splitlines()]
    pending = len(all_pairs) - state.get("egitilen", 0)
    if pending < THRESHOLD:
        print(f"threshold not met: {pending}/{THRESHOLD} pending pairs")
        return
    # Retrying a gate-rejected attempt on the same data every night burns
    # GPU/CPU for nothing: a retry requires meaningfully new data (>=50
    # pairs) since the last attempt.
    if len(all_pairs) - state.get("denenen", 0) < 50 and state.get("denenen"):
        print(f"too little new data: {len(all_pairs) - state.get('denenen', 0)}/50 "
              "— attempt deferred")
        return

    ck = fine_tune(all_pairs)
    if ck is None:
        return
    state["denenen"] = len(all_pairs)
    if gate_and_deploy(ck, all_pairs):
        state["egitilen"] = len(all_pairs)
    write_state(state)


if __name__ == "__main__":
    main()
