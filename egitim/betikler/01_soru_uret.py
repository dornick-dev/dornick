# -*- coding: utf-8 -*-
"""Soru üretimi: taban korpusunun girdi tarafı.

Üç sınıf üretilir, hepsi veri/sorular.jsonl'e eklenir (devam edilebilir):

  duz    tek satırlık kullanıcı soruları (kategori × üslup matrisi — çeşitlilik)
  zamir  iki satırlık çiftler: bağlam turu + zamirli/eksiltili takip sorusu
  susma  selam/teşekkür/tek kelime — modelin "boş" demeyi öğreneceği sınıf

Kullanım:
  py betikler/01_soru_uret.py --duz 2000 --zamir 300 --susma 300     (pilot)
  py betikler/01_soru_uret.py --duz 70000 --zamir 12000 --susma 3000 (tam)
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

from ayarlar import VERI, ButceDoldu, harcama, ogretmen_sor  # noqa: E402

CIKTI = VERI / "sorular.jsonl"   # --dil en → sorular_en.jsonl (main'de değişir)

KATEGORILER_EN = [
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

USLUPLAR_EN = [
    "short and hurried, lowercase, may contain typos",
    "full polite sentences",
    "like an expert using technical terms and abbreviations",
    "like a novice describing things in everyday words",
    "referring back to earlier work (\"the one we discussed\", \"yesterday's\")",
]

DUZ_ISTEM_EN = (
    "Generate realistic ENGLISH user messages sent to a personal AI assistant.\n"
    "Domain: {kategori}. Style: {uslup}.\n"
    "Write EXACTLY {adet} lines; each line is one standalone message. No numbering, "
    "no dashes, no quotes. Vary them: questions, requests, searching for a past note. "
    "Some should contain proper names, abbreviations, numbers."
)

ZAMIR_ISTEM_EN = (
    "Generate ENGLISH two-line examples from personal-assistant conversations. Each "
    "example is two lines:\n"
    "line 1: a context sentence about some topic (the user's earlier message)\n"
    "line 2: a follow-up that refers back with a PRONOUN or ELLIPSIS "
    "(\"what about its ...\", \"same as that one\", WITHOUT naming the topic)\n"
    "Domain: {kategori}. Write EXACTLY {adet} examples separated by a line "
    "containing only '---'. No numbering or quotes."
)

SUSMA_KALIP_EN = [
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "sure", "great",
    "nice", "good morning", "good night", "see you", "how are you", "yes", "no",
    "sounds good", "perfect", "cool", "alright then",
]

SUSMA_LLM_EN = ("Generate 15 short ENGLISH messages to an assistant that refer to NO "
                "topic at all: greetings, quick thanks, one-word reactions. "
                "No numbering or quotes.")

KATEGORILER = [
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

USLUPLAR = [
    "kısa ve aceleci, küçük harfle, yazım hatalı olabilir",
    "tam cümleli ve kibar",
    "teknik terim ve kısaltma kullanan bir uzman gibi",
    "konuya yabancı, terimleri günlük dille tarif eden biri gibi",
    "önceki bir işe atıf yapan (\"geçen konuştuğumuz\", \"dünkü\") biri gibi",
]

DUZ_ISTEM = (
    "Kişisel yapay zekâ asistanına sorulmuş gerçekçi TÜRKÇE kullanıcı mesajları üret.\n"
    "Alan: {kategori}. Üslup: {uslup}.\n"
    "TAM {adet} satır yaz; her satır tek başına bir mesaj olsun. Numara, tire, "
    "tırnak koyma. Mesajlar çeşitli olsun: soru, istek, hatırlatma arama, kayıt sorma. "
    "Bir kısmında özel adlar/kısaltmalar/sayılar geçsin."
)

ZAMIR_ISTEM = (
    "Kişisel asistan konuşmalarından TÜRKÇE ikili örnekler üret. Her örnek iki satır:\n"
    "1. satır: bir konudan bahseden bağlam cümlesi (kullanıcının önceki mesajı)\n"
    "2. satır: aynı konuya ZAMİRLE ya da EKSİLTİLİ dönen takip mesajı "
    "(\"peki onun ...\", \"aynısından ...\", \"o zaman şunu ...\", konu adı GEÇMEDEN)\n"
    "Alan: {kategori}. TAM {adet} örnek yaz; örnekleri '---' satırıyla ayır. "
    "Numara/tırnak koyma."
)

SUSMA_KALIP = [
    "selam", "merhaba", "naber", "günaydın", "iyi geceler", "teşekkürler", "sağ ol",
    "tamam", "ok", "peki", "olur", "harika", "süper", "eyvallah", "görüşürüz",
    "iyi misin", "nasılsın", "hoş geldin", "aynen", "evet", "yok", "hayır",
    "çok iyi", "vay be", "hadi bakalım", "kolay gelsin", "iyi çalışmalar",
]


def yaz(rows: list[dict]) -> None:
    VERI.mkdir(parents=True, exist_ok=True)
    with CIKTI.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def mevcut() -> dict[str, int]:
    sayilar = {"duz": 0, "zamir": 0, "susma": 0}
    if CIKTI.exists():
        for line in CIKTI.read_text(encoding="utf-8").splitlines():
            try:
                sayilar[json.loads(line)["tur"]] += 1
            except Exception:
                pass
    return sayilar


DIL = "tr"   # main --dil ile değişir


def duz_paket(rng: random.Random) -> list[dict]:
    if DIL == "en":
        kategori = rng.choice(KATEGORILER_EN)
        uslup = rng.choice(USLUPLAR_EN)
        istem = DUZ_ISTEM_EN
    else:
        kategori = rng.choice(KATEGORILER)
        uslup = rng.choice(USLUPLAR)
        istem = DUZ_ISTEM
    metin = ogretmen_sor(
        [{"role": "user",
          "content": istem.format(kategori=kategori, uslup=uslup, adet=25)}],
        max_tokens=900, temperature=0.9)
    rows = []
    for line in metin.splitlines():
        line = line.strip().strip("-•* ").strip()
        if 8 <= len(line) <= 200:
            rows.append({"tur": "duz", "kategori": kategori, "soru": line})
    return rows


def zamir_paket(rng: random.Random) -> list[dict]:
    if DIL == "en":
        kategori = rng.choice(KATEGORILER_EN)
        istem = ZAMIR_ISTEM_EN
    else:
        kategori = rng.choice(KATEGORILER)
        istem = ZAMIR_ISTEM
    metin = ogretmen_sor(
        [{"role": "user", "content": istem.format(kategori=kategori, adet=10)}],
        max_tokens=900, temperature=0.9)
    rows = []
    for blok in metin.split("---"):
        satirlar = [s.strip().strip("-•* ").strip()
                    for s in blok.splitlines() if s.strip()]
        if len(satirlar) >= 2 and 8 <= len(satirlar[0]) <= 200 and 4 <= len(satirlar[1]) <= 160:
            rows.append({"tur": "zamir", "kategori": kategori,
                         "baglam": satirlar[0], "soru": satirlar[1]})
    return rows


def susma_paket(rng: random.Random) -> list[dict]:
    # Yarı şablon yarı LLM: kalıplar bedava, LLM çeşitleme katıyor.
    kaliplar = SUSMA_KALIP_EN if DIL == "en" else SUSMA_KALIP
    rows = [{"tur": "susma", "kategori": "-", "soru": s}
            for s in rng.sample(kaliplar, k=min(8, len(kaliplar)))]
    llm_istem = SUSMA_LLM_EN if DIL == "en" else (
        "Bir asistana yazılmış, HİÇBİR konuya atıf yapmayan kısa Türkçe "
        "mesajlardan 15 satır üret: selam, hâl hatır, kısa onay/teşekkür, "
        "tek kelimelik tepkiler. Numara/tırnak koyma.")
    metin = ogretmen_sor(
        [{"role": "user", "content": llm_istem}],
        max_tokens=300, temperature=1.0)
    for line in metin.splitlines():
        line = line.strip().strip("-•* ").strip()
        if 2 <= len(line) <= 40:
            rows.append({"tur": "susma", "kategori": "-", "soru": line})
    return rows


def uret(tur: str, hedef: int, paket, paralel: int = 12) -> None:
    var = mevcut()[tur]
    if var >= hedef:
        print(f"{tur}: zaten {var} ≥ {hedef}, atlandı")
        return
    print(f"{tur}: {var} → {hedef} üretiliyor…")
    rng = random.Random()
    while var < hedef:
        istek = min(paralel * 2, max(1, (hedef - var) // 18 + 1))
        with ThreadPoolExecutor(max_workers=paralel) as havuz:
            isler = [havuz.submit(paket, rng) for _ in range(istek)]
            for gelen in as_completed(isler):
                try:
                    rows = gelen.result()
                except ButceDoldu:
                    print("!! bütçe sınırı — üretim durdu")
                    return
                except Exception as exc:
                    print("  paket hatası:", str(exc)[:80])
                    continue
                yaz(rows)
                var += len(rows)
        h = harcama()
        print(f"  {tur}: {var}/{hedef} · ${h['usd']:.2f} ({h['istek']} istek)")


def main() -> None:
    global DIL, CIKTI
    p = argparse.ArgumentParser()
    p.add_argument("--duz", type=int, default=0)
    p.add_argument("--zamir", type=int, default=0)
    p.add_argument("--susma", type=int, default=0)
    p.add_argument("--dil", default="tr", choices=("tr", "en"))
    a = p.parse_args()
    DIL = a.dil
    if a.dil == "en":
        CIKTI = VERI / "sorular_en.jsonl"
    if a.duz:
        uret("duz", a.duz, duz_paket)
    if a.zamir:
        uret("zamir", a.zamir, zamir_paket)
    if a.susma:
        uret("susma", a.susma, susma_paket)
    print("durum:", mevcut(), "| harcama:", f"${harcama()['usd']:.2f}")


if __name__ == "__main__":
    main()
