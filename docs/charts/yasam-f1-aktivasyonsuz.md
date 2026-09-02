# Yaşam benchmark'ı — `f1-aktivasyonsuz`

Senaryo: **yasam-90** · 117 soru · 156 düğüm · kapalı mekanik: `aktivasyon`

| Metrik | Yön | Değer | Taban | Fark | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2881 | 0.2869 | +0.0012 | >= 0.85 |
| `prime_recall` | ↑ | 0.9444 | 0.9444 | 0 | >= 0.8 |
| `yasak_sizinti` | ↓ | 50 | 50 | 0 | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.5 | 0.5 | 0 | >= 0.9 |
| `bayat_ruh` | ↓ | 5.5667 | 5.5667 | 0 | <= 0 |
| `taze_ruh` | ↑ | 1 | 1 | 0 | >= 0.8 |
| `ruh_token` | ↓ | 248.6 | 248.6 | 0 | ≤ taban |
| `prime_token` | ↓ | 78.5 | 79.9 | -1.4 | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | 0 | >= 0.7 |
| `gecikme_p95` | ↓ | 3.31 | 10.32 | -7.01 | <= 20 |

## Küme kırılımı (precision / recall)

| Küme | Ne ölçer | Precision | Recall |
|---|---|---|---|
| A | sabit gerçekler | 0.4688 | 1 |
| B | düzeltme zincirleri | 0.1846 | 0.75 |
| D | tekrar kullanılan yordamlar | 0.4 | 1 |
| E | bağlam çakışması | 0.2174 | 1 |

---

Üretim: `py eval/context_memory/yasam_bench.py --etiket f1-aktivasyonsuz`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
