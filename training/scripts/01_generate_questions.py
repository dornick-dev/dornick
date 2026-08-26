# -*- coding: utf-8 -*-
"""Question generation: the input side of the base corpus.

Three classes are produced, all appended to data/questions.jsonl (resumable):

  duz     ("plain")   one-line user questions (category x style matrix — variety)
  zamir   ("pronoun") two-line pairs: a context turn + a pronoun/ellipsis follow-up
  susma   ("silence") greetings/thanks/one-word — the class that teaches "empty"

The class names (duz/zamir/susma) are part of the frozen data schema; see
training/README.md.

Usage:
  py scripts/01_generate_questions.py --plain 2000 --pronoun 300 --silence 300   (pilot)
  py scripts/01_generate_questions.py --plain 70000 --pronoun 12000 --silence 3000 (full)
  py scripts/01_generate_questions.py --lang en ...                             (English)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from teacher import DATA, BudgetExceeded, ask_teacher, spend  # noqa: E402

OUTPUT = DATA / "questions.jsonl"   # --lang en → questions_en.jsonl (set in main)

CATEGORIES_EN = [
    "industrial automation and SCADA", "software development", "servers and networking",
    "databases", "AI tools", "crypto trading", "personal finance and banking",
    "car maintenance", "home repair", "appliance faults", "health and medication",
    "fitness and training", "nutrition", "cooking and recipes", "gardening", "pets",
    "travel planning", "legal paperwork", "government procedures", "education and exams",
    "childcare and school", "shopping and returns", "phone and computer issues",
    "photo and video editing", "music", "books and learning", "meetings and management",
    "project tracking and reporting", "HR and leave", "real estate and renting",
    "insurance", "weather and farming", "construction", "logistics and shipping",
    "security cameras and alarms", "smart home devices", "gaming and hardware",
    "taxes and invoices", "email and calendars", "water utilities",
]

STYLES_EN = [
    "short and hurried, lowercase, may contain typos",
    "full polite sentences",
    "like an expert using technical terms and abbreviations",
    "like a novice describing things in everyday words",
    "referring back to earlier work (\"the one we discussed\", \"yesterday's\")",
]

PLAIN_PROMPT_EN = (
    "Generate realistic ENGLISH user messages sent to a personal AI assistant.\n"
    "Domain: {category}. Style: {style}.\n"
    "Write EXACTLY {count} lines; each line is one standalone message. No numbering, "
    "no dashes, no quotes. Vary them: questions, requests, searching for a past note. "
    "Some should contain proper names, abbreviations, numbers."
)

PRONOUN_PROMPT_EN = (
    "Generate ENGLISH two-line examples from personal-assistant conversations. Each "
    "example is two lines:\n"
    "line 1: a context sentence about some topic (the user's earlier message)\n"
    "line 2: a follow-up that refers back with a PRONOUN or ELLIPSIS "
    "(\"what about its ...\", \"same as that one\", WITHOUT naming the topic)\n"
    "Domain: {category}. Write EXACTLY {count} examples separated by a line "
    "containing only '---'. No numbering or quotes."
)

SILENCE_TEMPLATES_EN = [
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "sure", "great",
    "nice", "good morning", "good night", "see you", "how are you", "yes", "no",
    "sounds good", "perfect", "cool", "alright then",
]

SILENCE_LLM_EN = ("Generate 15 short ENGLISH messages to an assistant that refer to NO "
                  "topic at all: greetings, quick thanks, one-word reactions. "
                  "No numbering or quotes.")

CATEGORIES_TR = [
    "endüstriyel otomasyon ve SCADA", "su ve atıksu tesisleri", "elektrik-elektronik",
    "yazılım geliştirme", "sunucu ve ağ yönetimi", "veritabanları", "yapay zekâ araçları",
    "kripto para ve borsa", "kişisel finans ve bankacılık", "vergi ve fatura işleri",
    "araba bakımı ve trafik", "ev tamiratı ve tadilat", "beyaz eşya arızaları",
    "sağlık ve ilaçlar", "spor ve antrenman", "beslenme ve diyet",
    "yemek tarifleri ve mutfak", "bahçe ve bitki bakımı", "evcil hayvanlar",
    "seyahat ve tatil planı", "hukuk ve dilekçe işleri", "resmi kurum işlemleri",
    "eğitim ve sınavlar", "çocuk bakımı ve okul", "alışveriş ve iade",
    "telefon ve bilgisayar sorunları", "fotoğraf ve video işleme", "müzik ve enstrüman",
    "kitap ve öğrenme", "iş yönetimi ve toplantılar", "proje takibi ve raporlama",
    "insan kaynakları ve izinler", "emlak ve kiralama", "sigorta işlemleri",
    "hava durumu ve tarım", "inşaat ve malzeme", "lojistik ve kargo",
    "güvenlik kameraları ve alarm", "akıllı ev cihazları", "oyun ve donanım",
]

STYLES_TR = [
    "kısa ve aceleci, küçük harfle, yazım hatalı olabilir",
    "tam cümleli ve kibar",
    "teknik terim ve kısaltma kullanan bir uzman gibi",
    "konuya yabancı, terimleri günlük dille tarif eden biri gibi",
    "önceki bir işe atıf yapan (\"geçen konuştuğumuz\", \"dünkü\") biri gibi",
]

PLAIN_PROMPT_TR = (
    "Kişisel yapay zekâ asistanına sorulmuş gerçekçi TÜRKÇE kullanıcı mesajları üret.\n"
    "Alan: {category}. Üslup: {style}.\n"
    "TAM {count} satır yaz; her satır tek başına bir mesaj olsun. Numara, tire, "
    "tırnak koyma. Mesajlar çeşitli olsun: soru, istek, hatırlatma arama, kayıt sorma. "
    "Bir kısmında özel adlar/kısaltmalar/sayılar geçsin."
)

PRONOUN_PROMPT_TR = (
    "Kişisel asistan konuşmalarından TÜRKÇE ikili örnekler üret. Her örnek iki satır:\n"
    "1. satır: bir konudan bahseden bağlam cümlesi (kullanıcının önceki mesajı)\n"
    "2. satır: aynı konuya ZAMİRLE ya da EKSİLTİLİ dönen takip mesajı "
    "(\"peki onun ...\", \"aynısından ...\", \"o zaman şunu ...\", konu adı GEÇMEDEN)\n"
    "Alan: {category}. TAM {count} örnek yaz; örnekleri '---' satırıyla ayır. "
    "Numara/tırnak koyma."
)

SILENCE_TEMPLATES_TR = [
    "selam", "merhaba", "naber", "günaydın", "iyi geceler", "teşekkürler", "sağ ol",
    "tamam", "ok", "peki", "olur", "harika", "süper", "eyvallah", "görüşürüz",
    "iyi misin", "nasılsın", "hoş geldin", "aynen", "evet", "yok", "hayır",
    "çok iyi", "vay be", "hadi bakalım", "kolay gelsin", "iyi çalışmalar",
]

SILENCE_LLM_TR = (
    "Bir asistana yazılmış, HİÇBİR konuya atıf yapmayan kısa Türkçe "
    "mesajlardan 15 satır üret: selam, hâl hatır, kısa onay/teşekkür, "
    "tek kelimelik tepkiler. Numara/tırnak koyma.")


def write_rows(rows: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def existing_counts() -> dict[str, int]:
    counts = {"duz": 0, "zamir": 0, "susma": 0}
    if OUTPUT.exists():
        for line in OUTPUT.read_text(encoding="utf-8").splitlines():
            try:
                counts[json.loads(line)["tur"]] += 1
            except Exception:
                pass
    return counts


LANG = "tr"   # set by --lang in main


def plain_batch(rng: random.Random) -> list[dict]:
    if LANG == "en":
        category = rng.choice(CATEGORIES_EN)
        style = rng.choice(STYLES_EN)
        prompt = PLAIN_PROMPT_EN
    else:
        category = rng.choice(CATEGORIES_TR)
        style = rng.choice(STYLES_TR)
        prompt = PLAIN_PROMPT_TR
    text = ask_teacher(
        [{"role": "user",
          "content": prompt.format(category=category, style=style, count=25)}],
        max_tokens=900, temperature=0.9)
    rows = []
    for line in text.splitlines():
        line = line.strip().strip("-•* ").strip()
        if 8 <= len(line) <= 200:
            rows.append({"tur": "duz", "kategori": category, "soru": line})
    return rows


def pronoun_batch(rng: random.Random) -> list[dict]:
    if LANG == "en":
        category = rng.choice(CATEGORIES_EN)
        prompt = PRONOUN_PROMPT_EN
    else:
        category = rng.choice(CATEGORIES_TR)
        prompt = PRONOUN_PROMPT_TR
    text = ask_teacher(
        [{"role": "user", "content": prompt.format(category=category, count=10)}],
        max_tokens=900, temperature=0.9)
    rows = []
    for block in text.split("---"):
        lines = [s.strip().strip("-•* ").strip()
                 for s in block.splitlines() if s.strip()]
        if len(lines) >= 2 and 8 <= len(lines[0]) <= 200 and 4 <= len(lines[1]) <= 160:
            rows.append({"tur": "zamir", "kategori": category,
                         "baglam": lines[0], "soru": lines[1]})
    return rows


def silence_batch(rng: random.Random) -> list[dict]:
    # Half templates, half LLM: templates are free, the LLM adds variety.
    templates = SILENCE_TEMPLATES_EN if LANG == "en" else SILENCE_TEMPLATES_TR
    rows = [{"tur": "susma", "kategori": "-", "soru": s}
            for s in rng.sample(templates, k=min(8, len(templates)))]
    llm_prompt = SILENCE_LLM_EN if LANG == "en" else SILENCE_LLM_TR
    text = ask_teacher(
        [{"role": "user", "content": llm_prompt}],
        max_tokens=300, temperature=1.0)
    for line in text.splitlines():
        line = line.strip().strip("-•* ").strip()
        if 2 <= len(line) <= 40:
            rows.append({"tur": "susma", "kategori": "-", "soru": line})
    return rows


def generate(cls: str, goal: int, batch, parallel: int = 12) -> None:
    have = existing_counts()[cls]
    if have >= goal:
        print(f"{cls}: already {have} >= {goal}, skipped")
        return
    print(f"{cls}: generating {have} -> {goal} ...")
    rng = random.Random()
    while have < goal:
        requests = min(parallel * 2, max(1, (goal - have) // 18 + 1))
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            jobs = [pool.submit(batch, rng) for _ in range(requests)]
            for done in as_completed(jobs):
                try:
                    rows = done.result()
                except BudgetExceeded:
                    print("!! budget limit — generation stopped")
                    return
                except Exception as exc:
                    print("  batch error:", str(exc)[:80])
                    continue
                write_rows(rows)
                have += len(rows)
        s = spend()
        print(f"  {cls}: {have}/{goal} · ${s['usd']:.2f} ({s['istek']} requests)")


def main() -> None:
    global LANG, OUTPUT
    p = argparse.ArgumentParser()
    p.add_argument("--plain", type=int, default=0, help="target count for class 'duz'")
    p.add_argument("--pronoun", type=int, default=0, help="target count for class 'zamir'")
    p.add_argument("--silence", type=int, default=0, help="target count for class 'susma'")
    p.add_argument("--lang", default="tr", choices=("tr", "en"))
    a = p.parse_args()
    LANG = a.lang
    if a.lang == "en":
        OUTPUT = DATA / "questions_en.jsonl"
    if a.plain:
        generate("duz", a.plain, plain_batch)
    if a.pronoun:
        generate("zamir", a.pronoun, pronoun_batch)
    if a.silence:
        generate("susma", a.silence, silence_batch)
    print("status:", existing_counts(), "| spend:", f"${spend()['usd']:.2f}")


if __name__ == "__main__":
    main()
