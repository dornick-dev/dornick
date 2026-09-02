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

## Faz 1 — Zaman bazlı aktivasyon ⚠️ kısmen kabul (1/5 kriter kaldı)

**Ne geldi**

| Dosya | Ne |
|---|---|
| `src/dornick/recall/aktivasyon.py` | ACT-R taban seviyesi: `B = ln(Σ t_k^-d)` |
| `recall/store.py` | `kullanimlar` sütunu, `Node.aktivasyon`, tohumlama ve yayılma çarpanı, aktivasyona göre `by_kind` |
| `mind/store.py` | `Mind._canli` — ruh artık tazelik değil canlılık sırası kullanıyor |
| `tests/test_aktivasyon.py` | formül + depoya bağlanışı + göç + ablation |

Şema: `ALTER TABLE node ADD COLUMN kullanimlar TEXT NOT NULL DEFAULT '[]'`.
Göç, sütun eklendiği anda `created` + `last_used`×`uses` ile kabaca
dolduruyor; okuma tarafı sütun boş olsa da aynı hesabı yapıyor, yani
`merge_from` ile gelen yabancı satırlar da sıfırdan başlamıyor.

`_seed_literal`'daki `familiarity = min(0.15, 0.03*uses)` **kaldırıldı** —
zamanı bilmeyen, doyan ve yalnızca ekleyen bir aşinalık payıydı. Yerine
`conf × tohum_carpani(B)` geçti; en unutulmuş kayıt bile skorunun yarısını
koruyor (`TOHUM_TABANI = 0.5`), yani geride kalıyor ama aramadan düşmüyor.

### Kalibrasyon (sihirli sayı yok)

`OLCEK` ∈ {0.75, 1.0, 1.5, 2.0, 3.0, 5.0} ve `BOZUNMA` ∈ {0.3, 0.5, 0.7}
yaşam bench'inde tarandı. Sonuç: **metrikler bu aralıkta neredeyse hiç
oynamıyor** (precision 0.295–0.300, recall 0.958–0.972, kalan metrikler
birebir aynı). Uç değerler (0.75 ve 5.0) hafifçe kötü; ortadaki plato
1.0–3.0. Seçim `OLCEK = 2.0`, `BOZUNMA = 0.5` (ACT-R literatürünün standart
bozunma üssü, bu depoya göre ayarlanmadı). Kalibrasyonun kendi bulgusu şu:
**sonuçlar bu iki sabite karşı duyarsız**; mekaniğin faydası sıralamanın
zamanı bilmesinden geliyor, sigmoidin dikliğinden değil.

### Ölçüm (`docs/charts/yasam-f1.md`)

| Metrik | Taban | Faz 1 | Ablation (kapalı) | Kabul | Durum |
|---|---|---|---|---|---|
| `bayat_ruh` | 5.567 | **3.333** | 5.567 | ≤ 2.78 (−%50) | ❌ −%40.1 |
| `taze_ruh` | 1.000 | 0.988 | 1.000 | ≥ 0.80 | ✅ |
| `prime_precision` | 0.287 | **0.300** | 0.288 | düşmez | ✅ |
| `tuzak_sessizlik` | 0.500 | 0.500 | 0.500 | düşmez | ✅ |
| `gecikme_p95` (50k) | 10.32 ms | 10.65 ms | — | ≤ 20 ms | ✅ |
| `prime_recall` | 0.944 | 0.972 | 0.944 | — | ✅ |
| `yasak_sizinti` | 50 | 48 | 50 | — | ✅ |

Ablation sütunu mekaniğin gerçekten iş yaptığını gösteriyor: kapatıldığında
her metrik tabana **birebir** dönüyor.

`scale_bench.py` gerileme kapısı: `current` recall 0.78 → 0.78,
precision 0.63 → **0.64**, silence 0.62 → 0.62, tok/query 71.8 → **71.2**.
Tek-tur kalitesi bozulmadı, hafifçe iyileşti.

### Neden `bayat_ruh` hedefi tutmadı — ve neden bu bir parametre sorunu değil

İki tur ayar harcandı (parametre taraması + ablation'ın sadık hale
getirilmesi). Kalan bayatlığın **tamamı `preference` türünde**:

* `procedure` tarafında bayatlık **sıfıra indi** — D yordamları düzenli
  kullanıldığı için aktivasyonları yüksek, ruhun sekiz yuvasını onlar
  dolduruyor ve zincirlerin ara sürümleri dışarıda kalıyor. Mekanik burada
  tam olarak vaat ettiği işi yapıyor.
* `preference` tarafında hiç pekiştirme sinyali yok: kullanıcı tercihini
  söylüyor, kimse o kaydı açmıyor. Pekiştirme yoksa aktivasyon sırası
  tazelik sırasına eşitleniyor ve bir zincirin 3. sürümü ile geçerli 4.
  sürümü **birbirinden ayırt edilemez hale geliyor** — ikisi de yeni, ikisi
  de kullanılmamış. Aradaki farkı bilen tek şey "bu kayıt şunun yerini
  aldı" bilgisi, yani supersede.

Yani kalan %10, Faz 1'in erişemeyeceği bir yerde duruyor; Faz 2'nin kabul
kriteri zaten `bayat_ruh = 0`. Bu bir başarısızlık değil, iş bölümünün
ölçülmüş hali — ama kriter kriterdir ve **geçilmedi**: kararı kullanıcı
verecek.

## Faz 2 — Supersede · Faz 1 kararı bekleniyor

## Faz 3 — Gece konsolidasyonu · bekliyor
## Faz 4 — Kodlama gücü · bekliyor
## Faz 5 — Bağlam bonusu · bekliyor
