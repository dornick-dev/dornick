# training — the base rewriter and how to train your own

This directory is the complete training rig for neo's **base rewriter**
(`QueryExpander`): a 10.8M-parameter byte-level model that looks at a user
message and emits the extra search terms the memory engine will need —
synonyms, abbreviations, pronoun resolutions — or nothing at all when the
message has no topic. The product ships a trained copy as
`src/neocp/assets/taban.npz` and runs it in pure numpy on CPU, in
milliseconds, fully offline.

Everything needed to reproduce or improve the model is here, **including
the data**:

| path | what it is | in git |
|---|---|---|
| `data/corpus.jsonl` | 82.3k labeled Turkish examples (synthetic, teacher-generated) | yes (13 MB) |
| `data/corpus_en.jsonl` | 82.2k labeled English examples | yes (13 MB) |
| `checkpoints/base.pt` | the trained base checkpoint — seed of the personal loop | yes (41 MB) |
| `data/questions*.jsonl`, `data/spend.json` | intermediate generation artifacts | no |
| `data/personal_*` | **the user's personal data** — never committed | no |
| `checkpoints/{last,best,personal,blend}*` | training outputs | no |

## Pipeline

![Training pipeline](../docs/training-pipeline.svg)

```
scripts/01_generate_questions.py  teacher LLM writes user questions (3 classes)
scripts/02_label.py               teacher labels each question with search terms
scripts/03_train.py               train from scratch (GPU, bf16, ~20k steps)
scripts/04_export.py              checkpoint → fp16 npz + torch↔numpy parity gate
scripts/05_exam.py                acceptance exam on neo's scale benchmark
scripts/06_en_probe.py            hand-labeled English probe (no API needed)
scripts/try_it.py                 interactive demo: type a question, see terms
scripts/personal_loop.py          the nightly on-device personal loop (see below)
teacher.py                        teacher client + hard budget guard
model/architecture.py             the model (torch)  ·  model/inference.py  (numpy)
```

### 1. Teacher–student distillation

The corpus is synthetic, produced by a cheap hosted teacher
(Gemini flash-lite via OpenRouter; `teacher.py` counts every request and
hard-stops at a budget limit). Three example classes, stored under the
frozen schema field `tur`:

* **`duz`** (plain) — single-turn questions over a 40-category ×
  5-style matrix (expert jargon, hurried lowercase, novice paraphrase, …)
* **`zamir`** (pronoun) — a context turn plus a follow-up that refers back
  only with a pronoun or ellipsis; the model must resolve the reference
* **`susma`** (silence) — greetings, thanks, one-word reactions; the
  labeled output is the **empty string**, so the model learns silence
  from examples instead of a bolted-on threshold

`02_label.py` then asks the teacher for at most 8 extra search terms per
question (batched 20 per request). Together the two committed corpora hold
**~164.5k bilingual examples**.

### 2. The model

A deliberately small decoder-only GPT (`model/architecture.py`):
6 layers, d=384, 6 heads, context 224 → **10.8M parameters**. It is
**byte-level** — vocabulary 260 (256 bytes + BOS/SEP/EOS/PAD) — for two
reasons: Turkish is agglutinative, so a tokenizer-free model sees stems
inside suffixed words for free; and one vocabulary covers both languages.
Sequence: `[BOS] input bytes [SEP] term bytes [EOS]`, loss only after SEP.

### 3. Train, export, parity

```bash
py scripts/03_train.py --steps 20000 --extra corpus_en.jsonl
py scripts/04_export.py            # → checkpoints/base.npz
```

Export packs the weights as fp16 into a single `.npz` whose key names
(`gomme`, `konum`, `b0.att.in_w`, …) are a **frozen wire format** — the
product's own numpy decoder (`src/neocp/recall/taban.py`) and every
deployed model read them. Export refuses to finish unless torch and numpy
produce the same logits (max diff < 0.25, fp16 packing margin).

### 4. Acceptance exams

```bash
py scripts/05_exam.py              # Turkish: the product's scale benchmark
py scripts/06_en_probe.py          # English: hand-labeled probe
```

`05_exam.py` runs the *product's own* retrieval benchmark
(`eval/context_memory/scale_bench.py`: 100 memories, 60 episodes, 70
gold-labeled queries) with and without the rewriter in front. The shipped
model's measured effect: **retrieval accuracy 0.87 → 0.93**, and questions
rephrased with synonyms **0.50 → 1.00**, with no regression on trap-query
silence. Full expansion costs ~300 ms on CPU once per message; deciding to
stay silent costs under 50 ms.

### 5. The nightly personal loop

`scripts/personal_loop.py` is what the product schedules when the user
switches on "Learn me" (`src/neocp/tanima.py` finds it at
`<root>/training/scripts/personal_loop.py` and runs it low-priority):

1. **harvest** — new memories since the watermark, read-only, episodes excluded
2. **label** — neo's own configured model writes 4 question styles + topic
   terms per memory (falls back to the hosted teacher if configured)
3. **fine-tune** — from `checkpoints/base.pt`, on CPU, with a replay
   buffer of base-corpus examples (6:1, silence share protected) against
   catastrophic forgetting
4. **Wise-FT blends** — the fine-tune is blended with the base weights at
   α ∈ {0.35, 0.55, 0.75}; every blend is a candidate
5. **exam gate** — all candidates race the deployed model in the same run
   (TR bench + EN probe + a product-truth personal probe over a copy of
   the user's own mind); a candidate must not regress anywhere and must
   find strictly more of the user's memories
6. **hot deploy** — the winner is copied to `.neocp/taban.npz`; the product
   prefers that file over the stock model, no restart needed

A regressing candidate is discarded; a bad night cannot break the product.
The personal gate scores on memories HELD OUT of fine-tuning (a ~20%
split by source memory, fixed seed) — a small model memorises its
training pairs, so an in-sample score would measure memorisation, not
generalisation. An absolute floor against the STOCK model bounds
cumulative drift across nights.

Personal artifacts (`data/personal_*`) never leave the machine and are
git-ignored. The labeling step sends memory text to the model you
selected in neo: with a local endpoint (LM Studio, Ollama) nothing
leaves the machine; a hosted endpoint is refused unless you opt in
via the "Allow labeling with a hosted model" switch in settings
(`learn_cloud_ok` in `.neocp/tanima.json`).

## Setup

```bash
pip install torch numpy            # torch only for training; inference is numpy-only
cp .env.example .env               # add your OpenRouter key (corpus generation only)
```

You do NOT need an API key to: run inference (`try_it.py`), retrain on the
committed corpora (`03_train.py`), export, or run the exams.

## Training a better one

Knobs that matter, roughly in order of expected payoff:

* **More/better data** — `01_generate_questions.py --plain N --pronoun N
  --silence N [--lang en]` extends the corpus for cents; new categories and
  styles are one list entry away. The English corpus is currently weaker
  than the Turkish one — the cheapest win available.
* **Model size** — `Config` in `model/architecture.py` (d, layers, heads,
  ctx). Remember the product budget: pure-numpy CPU inference, p95 < 500 ms
  full expansion.
* **Personal-loop constants** — in `scripts/personal_loop.py`:
  `ALPHAS` (blend ratios), `REPLAY_RATIO`, `EPOCHS`, `THRESHOLD`, and the
  gate margins in `gate_and_deploy`. The margins are sized to the probes'
  resolution; tighten them only with bigger probes.
* **Silence quality** — the `susma` class and `REPLAY_SILENCE_SHARE` guard
  the model's most fragile skill: knowing when to say nothing.

Gates a new model must clear before it ships with the product:

* scale-bench recall ≥ the current system, no trap-silence regression
* actually silent on held-out `susma` examples
* CPU: full expansion p95 < 500 ms, early silence < 50 ms
* English probe not below the previous model
* torch↔numpy parity within the fp16 margin

## Data format (frozen schema)

`data/corpus*.jsonl`, one JSON object per line:

```json
{"girdi": "context?\n question", "cikti": "term term ...", "tur": "duz|zamir|susma"}
```

Field names are Turkish (`girdi`=input, `cikti`=output, `tur`=class) and
are kept as-is: they are the wire format of every existing corpus,
checkpoint and deployed model. The same applies to the npz keys and the
checkpoint dict keys (`ayar`, `adim`, `eniyi`). English code, frozen
Turkish wire format — the boundary is documented where it appears.
