# -*- coding: utf-8 -*-
"""Etiketleme: her soruya öğretmenden ek arama terimleri.

Toplu istek (20 soru/istek — sistem istemi amortize olur), paralel,
sürdürülebilir: veri/korpus.jsonl'de olan sorular atlanır.

Çıktı satırı: {"girdi": "<bağlam?\\n>soru", "cikti": "terim terim …", "tur": ...}
Susma sınıfının cikti'si her zaman "" — model susmayı da örnekten öğrenir.

Kullanım:  py betikler/02_etiketle.py            (sorular.jsonl'ün tamamı)
           py betikler/02_etiketle.py --en-cok 500   (pilot)
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

from ayarlar import VERI, ButceDoldu, harcama, ogretmen_sor  # noqa: E402

SORULAR = VERI / "sorular.jsonl"     # --dil en → *_en.jsonl (main'de değişir)
KORPUS = VERI / "korpus.jsonl"

SISTEM_EN = (
    "You are a query expander for a memory search engine. You will receive "
    "numbered ENGLISH user messages; some may start with [context: ...].\n"
    "For each number, write on one line AT MOST 8 extra search terms: synonyms "
    "and abbreviations of the key concepts, and resolutions of pronouns using "
    "the context. Do not repeat words already in the message. If the message "
    "refers to no topic (greeting, thanks, short ack), write only '-' for it.\n"
    "Strict format: each line is 'N) terms' — nothing else."
)

SISTEM = (
    "Bir hafıza arama motoru için sorgu genişleticisin. Sana numaralı Türkçe "
    "kullanıcı mesajları verilecek; bazılarının başında [bağlam: ...] olabilir.\n"
    "Her numara için, mesajdaki anahtar kavramların EŞ ANLAMLILARINI, "
    "KISALTMALARINI ve bağlamdaki zamirlerin ÇÖZÜMÜNÜ tek satırda, boşlukla "
    "ayrılmış EN FAZLA 8 ek terim olarak yaz. Mesajda zaten geçen kelimeyi "
    "tekrarlama. Mesaj bir konuya atıf yapmıyorsa (selam, teşekkür, kısa onay) "
    "o numara için yalnız '-' yaz.\n"
    "Biçim kesin: her satır 'N) terimler' — açıklama yok, başka hiçbir şey yok."
)

# Süzgeç: öğretmen çıktısındaki gürültüye karşı (cümle kurmuş, uzun yazmış).
_TEMIZ = re.compile(r"[^\wçğıöşüÇĞİÖŞÜ\- ]", re.UNICODE)


def suz(terimler: str, soru: str) -> str:
    metin = _TEMIZ.sub(" ", terimler).strip()
    if not metin or metin == "-":
        return ""
    varolan = set(soru.casefold().split())
    secilen: list[str] = []
    for kelime in metin.split():
        k = kelime.strip("-").casefold()
        if 2 <= len(k) <= 24 and k not in varolan and k not in secilen:
            secilen.append(k)
        if len(secilen) == 8:
            break
    return " ".join(secilen)


def girdi_metni(row: dict) -> str:
    if row.get("baglam"):
        return f"{row['baglam']}\n{row['soru']}"
    return row["soru"]


def etiketli() -> set[str]:
    var: set[str] = set()
    if KORPUS.exists():
        for line in KORPUS.read_text(encoding="utf-8").splitlines():
            try:
                var.add(json.loads(line)["girdi"])
            except Exception:
                pass
    return var


def paket_etiketle(rows: list[dict]) -> list[dict]:
    numarali = []
    for i, row in enumerate(rows, 1):
        if row.get("baglam"):
            numarali.append(f"{i}) [bağlam: {row['baglam']}] {row['soru']}")
        else:
            numarali.append(f"{i}) {row['soru']}")
    cevap = ogretmen_sor(
        [{"role": "system", "content": SISTEM_EN if DIL == "en" else SISTEM},
         {"role": "user", "content": "\n".join(numarali)}],
        max_tokens=40 * len(rows) + 80)

    cevaplar: dict[int, str] = {}
    for satir in cevap.splitlines():
        m = re.match(r"\s*(\d+)\)\s*(.*)", satir)
        if m:
            cevaplar[int(m.group(1))] = m.group(2)

    cikti = []
    for i, row in enumerate(rows, 1):
        terim = suz(cevaplar.get(i, ""), girdi_metni(row))
        cikti.append({"girdi": girdi_metni(row), "cikti": terim, "tur": row["tur"]})
    return cikti


DIL = "tr"


def main() -> None:
    global DIL, SORULAR, KORPUS
    p = argparse.ArgumentParser()
    p.add_argument("--en-cok", type=int, default=0)
    p.add_argument("--paralel", type=int, default=12)
    p.add_argument("--dil", default="tr", choices=("tr", "en"))
    a = p.parse_args()
    DIL = a.dil
    if a.dil == "en":
        SORULAR = VERI / "sorular_en.jsonl"
        KORPUS = VERI / "korpus_en.jsonl"

    var = etiketli()
    bekleyen: list[dict] = []
    for line in SORULAR.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if girdi_metni(row) in var:
            continue
        if row["tur"] == "susma":
            # Susma etiketi bedava: öğretmene sormaya gerek yok.
            with KORPUS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"girdi": girdi_metni(row), "cikti": "",
                                    "tur": "susma"}, ensure_ascii=False) + "\n")
            var.add(girdi_metni(row))
            continue
        bekleyen.append(row)
        if a.en_cok and len(bekleyen) >= a.en_cok:
            break

    print(f"etiketlenecek: {len(bekleyen)}")
    paketler = [bekleyen[i:i + 20] for i in range(0, len(bekleyen), 20)]
    bitti = 0
    with ThreadPoolExecutor(max_workers=a.paralel) as havuz:
        isler = {havuz.submit(paket_etiketle, pk): pk for pk in paketler}
        for gelen in as_completed(isler):
            try:
                rows = gelen.result()
            except ButceDoldu:
                print("!! bütçe sınırı — etiketleme durdu")
                break
            except Exception as exc:
                print("  paket hatası:", str(exc)[:80])
                continue
            with KORPUS.open("a", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            bitti += len(rows)
            if bitti % 400 < 20:
                h = harcama()
                print(f"  {bitti}/{len(bekleyen)} · ${h['usd']:.2f}")

    h = harcama()
    toplam = sum(1 for _ in KORPUS.open(encoding="utf-8"))
    print(f"korpus: {toplam} örnek · harcama ${h['usd']:.2f} ({h['istek']} istek)")


if __name__ == "__main__":
    main()
