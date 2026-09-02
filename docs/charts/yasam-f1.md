# Yaşam benchmark'ı — `f1`

Senaryo **yasam-90** · 191 soru · 288 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | 0.2553 | **0.2634** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | 0.96 | **0.98** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | 59 | **57** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.45 | **0.45** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | 3.4778 | **3.3333** | <= 0 |
| `taze_ruh` | ↑ | 1 | 1 | **0.8082** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | 324.972 | **329.811** | ≤ taban |
| `prime_token` | ↓ | 84.0668 | 84.0668 | **83.6387** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | 0 | **0** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | 0.5 | **0.625** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | 0 | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | 1 | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | yok | **-0** | > 0 |
| `yakalama` | ↑ | yok | yok | **-0.9809** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | 79.4 | **79.4** | <= 1 |
| `sicak_oran` | · | 1 | 1 | **1** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | yok | **yok** | <= 300 |
| `kesinti_kaybi` | ↓ | yok | yok | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | yok | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | yok | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | yok | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | yok | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | yok | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | yok | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 8.97 | 8.97 | **9.31** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall |
|---|---|---|---|
| A | sabit gerçekler | 0.3659 | 1 |
| B | düzeltme zincirleri | 0.2143 | 0.9375 |
| D | tekrar kullanılan yordamlar | 0.375 | 1 |
| E | bağlam çakışması | 0.2021 | 0.95 |
| H | zaman komşuluğu | 0.4615 | 1 |
| J | dikiş | 0.4286 | 1 |
| K | gömülme | 0.1429 | 1 |

## Ölçekte gecikme

50000 düğüm · p50 **7.24 ms** · p95 **9.31 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/yasam_bench.py --etiket f1`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
