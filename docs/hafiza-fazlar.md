# İnsan benzeri hafıza — faz defteri

Bu dosya yol haritasının koşum defteri: hangi faz bitti, kabul kriterini
geçti mi, geçmediyse ne öğrenildi. Bir faz kabul kriterini geçmeden bir
sonrakine geçilmiyor; negatif sonuç da rapordur ve burada durur.

Ölçüm: `py eval/context_memory/yasam_bench.py --etiket <faz>`
Özet tablo: `py eval/context_memory/yasam_bench.py --tablo`
Gerileme kapısı: `py eval/context_memory/scale_bench.py` (tek-tur kalitesi
bozulmamalı).

---

## Faz 0 — Ölçüm altyapısı ✅ tamam

Hiçbir mekanik değişmedi. Değişen tek şey ölçülebilirlik.

**Ne geldi**

| Dosya | Ne |
|---|---|
| `src/dornick/recall/saat.py` | enjekte edilebilir saat; zamanın okunduğu tek yer |
| `src/dornick/recall/anahtar.py` | mekanik açma/kapama anahtarları (ablation yüzeyi) |
| `eval/context_memory/yasam_dataset.json` | 90 sanal gün, 333 olay, A–G kümeleri (dondurulmuş) |
| `eval/context_memory/yasam_holdout.json` | ayrı 30 günlük senaryo (Faz 3 sınav kapısı için) |
| `eval/context_memory/yasam_bench.py` | senaryoyu sanal saatle oynatan bench |
| `tests/test_saat.py` | saatin her damgaya ulaştığı + doğrudan `datetime.now()` yasağı |
| `tests/test_yasam_bench.py` | bench determinizmi + veri seti tutarlılığı |
| `tests/fixtures/recall-v1.db` + `tests/test_goc.py` | eski şemalı bellek her fazda açılıyor |

`RecallStore`, `Mind`, `open_store`, `open_mind` artık `saat=` alıyor;
verilmezse duvar saati — ürün davranışı birebir aynı.

**Veri setinin kapsamı ve sınırı.** Sorular, beklenen kaydın içerik
kelimelerinden en az birini taşıyacak şekilde yazıldı. Bu bir kolaylaştırma
değil, bilinçli bir kapsam kararı: Türkçe biçimbiliminin (ünsüz yumuşaması,
ekler) sözcüksel aramada açtığı gedik ayrı bir sorundur ve bu yol
haritasının hiçbir fazı onu çözmüyor. Veri seti onunla doldurulsaydı bütün
metrikler o gediğin gürültüsünde boğulur, zaman/pekişme/güncelleme farkı
görünmez olurdu. **Bu benchmark hafızanın zaman davranışını ölçer, Türkçe
morfolojisini değil.**

`G` kümesi (uzun sessizlik) `prime_precision`/`prime_recall` ortalamalarına
girmiyor: unutulmuş bir kaydın kendiliğinden önyüklemeye girmemesi tasarımın
amacı, onu recall'a saymak mekaniği kendi hedefiyle çelişen bir sayıyla
cezalandırmak olurdu. G'nin kendi metriği var (`geri_donus_recall`) ve o,
modelin **açık** araması üzerinden ölçülüyor.

### Taban çizgisi (`docs/charts/yasam-taban.md`)

| Metrik | Yön | Taban | Hedef |
|---|---|---|---|
| `prime_precision` | ↑ | **0.287** | ≥ 0.85 |
| `prime_recall` | ↑ | **0.944** | ≥ 0.80 |
| `yasak_sizinti` | ↓ | **50** | 0 |
| `tuzak_sessizlik` | ↑ | **0.50** | ≥ 0.90 |
| `bayat_ruh` (gün başına) | ↓ | **5.57** | 0 |
| `taze_ruh` | ↑ | **1.00** | ≥ 0.80 |
| `ruh_token` | ↓ | **248.6** | ≤ taban |
| `prime_token` | ↓ | **79.9** | ≤ 0.85 × taban |
| `geri_donus_recall` | ↑ | **1.00** | ≥ 0.70 |
| `gecikme_p95` (50k düğüm) | ↓ | **10.32 ms** | ≤ 20 ms |

Küme kırılımı: A precision 0.47 · B **0.18** · D 0.40 · E **0.22**
(recall her kümede 0.75–1.00).

**Tabanın söylediği.** Hafıza şu an her şeyi buluyor (recall 0.94) ama
neredeyse hiçbir şeyi ayıklamıyor (precision 0.29). İki en düşük küme,
yol haritasının iki ana mekaniğini birebir işaret ediyor:

* **B = 0.18** — düzeltme zincirleri. Aynı konunun dört sürümü de aynı anda
  önyükleniyor; model "PDF mi xlsx mi csv mi" diye dört çelişkiyi birden
  görüyor. Faz 2 (supersede) tam olarak bunu hedefliyor.
* **E = 0.22** — bağlam çakışması. `koru1000` oturumunda sorulan soruya
  `kobyte` kaydı da geliyor; `session`/bağlam alanı arama tarafında hiç
  kullanılmıyor. Faz 5'in konusu.
* **`bayat_ruh` 5.57** — her gün ortalama 5,5 supersede edilmiş kayıt
  sistem promptunda duruyor. Ruh sıralaması `uses`/tazelik bakıyor,
  aktivasyon bilmiyor. Faz 1 + Faz 2.
* **`tuzak_sessizlik` 0.50** — hafızada karşılığı olmayan 40 sorunun
  yarısında yine de bir şey enjekte ediliyor.

`geri_donus_recall` ve `taze_ruh` tabanda zaten tavanda: bunlar hedef değil,
**bozmama** şartı. Faz 1'in aktivasyon çarpanı en çok bu ikisini riske atar.

### Gerileme kapısı — `scale_bench.py` (taban)

| method | recall | coverage | precision | silence | tok/query | p95 ms |
|---|---|---|---|---|---|---|
| `current` | 0.78 | 0.76 | 0.63 | 0.62 | 71.8 | 4.00 |

Her faz bu satırı da koşuyor; tek-tur kalitesi bozulmamalı.

---

## Faz 1 — Zaman bazlı aktivasyon · sırada

Kabul: `bayat_ruh` ≥ %50 azalma (→ ≤ 2.78), `taze_ruh` ≥ 0.8,
`prime_precision` düşmez, `tuzak_sessizlik` düşmez, `gecikme_p95` bütçede.

## Faz 2 — Supersede · bekliyor
## Faz 3 — Gece konsolidasyonu · bekliyor
## Faz 4 — Kodlama gücü · bekliyor
## Faz 5 — Bağlam bonusu · bekliyor
