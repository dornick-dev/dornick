# Yaşam benchmark'ı — `taban`

Senaryo: **yasam-90** · 117 soru · 156 düğüm · kapalı mekanik: `yok`

| Metrik | Yön | Değer | Taban | Fark | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2869 | — | — | >= 0.85 |
| `prime_recall` | ↑ | 0.9444 | — | — | >= 0.8 |
| `yasak_sizinti` | ↓ | 50 | — | — | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.5 | — | — | >= 0.9 |
| `bayat_ruh` | ↓ | 5.5667 | — | — | <= 0 |
| `taze_ruh` | ↑ | 1 | — | — | >= 0.8 |
| `ruh_token` | ↓ | 248.6 | — | — | ≤ taban |
| `prime_token` | ↓ | 79.9 | — | — | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | — | — | >= 0.7 |
| `gecikme_p95` | ↓ | 10.32 | — | — | <= 20 |

## Küme kırılımı (precision / recall)

| Küme | Ne ölçer | Precision | Recall |
|---|---|---|---|
| A | sabit gerçekler | 0.4688 | 1 |
| B | düzeltme zincirleri | 0.1818 | 0.75 |
| D | tekrar kullanılan yordamlar | 0.4 | 1 |
| E | bağlam çakışması | 0.2174 | 1 |

## Ölçekte gecikme

50000 düğüm · p50 **7.12 ms** · p95 **10.32 ms** (bütçe 20 ms)

---

Üretim: `py eval/context_memory/yasam_bench.py --etiket taban`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
