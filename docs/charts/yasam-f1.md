# Yaşam benchmark'ı — `f1`

Senaryo: **yasam-90** · 117 soru · 156 düğüm · kapalı mekanik: `yok`

| Metrik | Yön | Değer | Taban | Fark | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.3004 | 0.2869 | +0.0135 | >= 0.85 |
| `prime_recall` | ↑ | 0.9722 | 0.9444 | +0.0278 | >= 0.8 |
| `yasak_sizinti` | ↓ | 48 | 50 | -2 | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.5 | 0.5 | 0 | >= 0.9 |
| `bayat_ruh` | ↓ | 3.3333 | 5.5667 | -2.233 | <= 0 |
| `taze_ruh` | ↑ | 0.9877 | 1 | -0.0123 | >= 0.8 |
| `ruh_token` | ↓ | 253.8 | 248.6 | +5.2 | ≤ taban |
| `prime_token` | ↓ | 79.5 | 79.9 | -0.4 | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | 0 | >= 0.7 |
| `gecikme_p95` | ↓ | 10.65 | 10.32 | +0.33 | <= 20 |

## Küme kırılımı (precision / recall)

| Küme | Ne ölçer | Precision | Recall |
|---|---|---|---|
| A | sabit gerçekler | 0.4688 | 1 |
| B | düzeltme zincirleri | 0.2273 | 0.9375 |
| D | tekrar kullanılan yordamlar | 0.4286 | 1 |
| E | bağlam çakışması | 0.2135 | 0.95 |

## Ölçekte gecikme

50000 düğüm · p50 **7.48 ms** · p95 **10.65 ms** (bütçe 20 ms)

---

Üretim: `py eval/context_memory/yasam_bench.py --etiket f1`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
