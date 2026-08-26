# -*- coding: utf-8 -*-
"""Labeling: extra search terms from the teacher for every question.

Batched requests (20 questions per call — the system prompt amortizes),
parallel, resumable: questions already present in data/corpus.jsonl are
skipped.

Output line: {"girdi": "<context?\\n>question", "cikti": "term term ...", "tur": ...}
The 'susma' (silence) class always gets cikti "" — the model learns to stay
silent from examples, too. Field names are the frozen data schema (README).

Usage:  py scripts/02_label.py               (all of questions.jsonl)
        py scripts/02_label.py --limit 500   (pilot)
        py scripts/02_label.py --lang en     (label the English questions)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from teacher import DATA, BudgetExceeded, ask_teacher, spend  # noqa: E402

QUESTIONS = DATA / "questions.jsonl"     # --lang en → *_en.jsonl (set in main)
CORPUS = DATA / "corpus.jsonl"

SYSTEM_EN = (
    "You are a query expander for a memory search engine. You will receive "
    "numbered ENGLISH user messages; some may start with [context: ...].\n"
    "For each number, write on one line AT MOST 8 extra search terms: synonyms "
    "and abbreviations of the key concepts, and resolutions of pronouns using "
    "the context. Do not repeat words already in the message. If the message "
    "refers to no topic (greeting, thanks, short ack), write only '-' for it.\n"
    "Strict format: each line is 'N) terms' — nothing else."
)

SYSTEM_TR = (
    "Bir hafıza arama motoru için sorgu genişleticisin. Sana numaralı Türkçe "
    "kullanıcı mesajları verilecek; bazılarının başında [bağlam: ...] olabilir.\n"
    "Her numara için, mesajdaki anahtar kavramların EŞ ANLAMLILARINI, "
    "KISALTMALARINI ve bağlamdaki zamirlerin ÇÖZÜMÜNÜ tek satırda, boşlukla "
    "ayrılmış EN FAZLA 8 ek terim olarak yaz. Mesajda zaten geçen kelimeyi "
    "tekrarlama. Mesaj bir konuya atıf yapmıyorsa (selam, teşekkür, kısa onay) "
    "o numara için yalnız '-' yaz.\n"
    "Biçim kesin: her satır 'N) terimler' — açıklama yok, başka hiçbir şey yok."
)

# Filter against teacher-output noise (wrote a sentence, rambled on).
_CLEAN = re.compile(r"[^\wçğıöşüÇĞİÖŞÜ\- ]", re.UNICODE)


def filter_terms(terms: str, question: str) -> str:
    text = _CLEAN.sub(" ", terms).strip()
    if not text or text == "-":
        return ""
    present = set(question.casefold().split())
    picked: list[str] = []
    for word in text.split():
        w = word.strip("-").casefold()
        if 2 <= len(w) <= 24 and w not in present and w not in picked:
            picked.append(w)
        if len(picked) == 8:
            break
    return " ".join(picked)


def input_text(row: dict) -> str:
    if row.get("baglam"):
        return f"{row['baglam']}\n{row['soru']}"
    return row["soru"]


def labeled() -> set[str]:
    have: set[str] = set()
    if CORPUS.exists():
        for line in CORPUS.read_text(encoding="utf-8").splitlines():
            try:
                have.add(json.loads(line)["girdi"])
            except Exception:
                pass
    return have


def label_batch(rows: list[dict]) -> list[dict]:
    numbered = []
    for i, row in enumerate(rows, 1):
        if row.get("baglam"):
            numbered.append(f"{i}) [bağlam: {row['baglam']}] {row['soru']}")
        else:
            numbered.append(f"{i}) {row['soru']}")
    answer = ask_teacher(
        [{"role": "system", "content": SYSTEM_EN if LANG == "en" else SYSTEM_TR},
         {"role": "user", "content": "\n".join(numbered)}],
        max_tokens=40 * len(rows) + 80)

    answers: dict[int, str] = {}
    for line in answer.splitlines():
        m = re.match(r"\s*(\d+)\)\s*(.*)", line)
        if m:
            answers[int(m.group(1))] = m.group(2)

    out = []
    for i, row in enumerate(rows, 1):
        terms = filter_terms(answers.get(i, ""), input_text(row))
        out.append({"girdi": input_text(row), "cikti": terms, "tur": row["tur"]})
    return out


LANG = "tr"


def main() -> None:
    global LANG, QUESTIONS, CORPUS
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--parallel", type=int, default=12)
    p.add_argument("--lang", default="tr", choices=("tr", "en"))
    a = p.parse_args()
    LANG = a.lang
    if a.lang == "en":
        QUESTIONS = DATA / "questions_en.jsonl"
        CORPUS = DATA / "corpus_en.jsonl"

    have = labeled()
    pending: list[dict] = []
    for line in QUESTIONS.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if input_text(row) in have:
            continue
        if row["tur"] == "susma":
            # Silence labels are free: no need to ask the teacher.
            with CORPUS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"girdi": input_text(row), "cikti": "",
                                    "tur": "susma"}, ensure_ascii=False) + "\n")
            have.add(input_text(row))
            continue
        pending.append(row)
        if a.limit and len(pending) >= a.limit:
            break

    print(f"to label: {len(pending)}")
    batches = [pending[i:i + 20] for i in range(0, len(pending), 20)]
    done_count = 0
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        jobs = {pool.submit(label_batch, b): b for b in batches}
        for done in as_completed(jobs):
            try:
                rows = done.result()
            except BudgetExceeded:
                print("!! budget limit — labeling stopped")
                break
            except Exception as exc:
                print("  batch error:", str(exc)[:80])
                continue
            with CORPUS.open("a", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            done_count += len(rows)
            if done_count % 400 < 20:
                s = spend()
                print(f"  {done_count}/{len(pending)} · ${s['usd']:.2f}")

    s = spend()
    total = sum(1 for _ in CORPUS.open(encoding="utf-8"))
    print(f"corpus: {total} examples · spend ${s['usd']:.2f} ({s['istek']} requests)")


if __name__ == "__main__":
    main()
