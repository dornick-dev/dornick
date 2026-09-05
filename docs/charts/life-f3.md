# Yaşam benchmark'ı — `f3`

Senaryo **yasam-90** · 191 soru · 276 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | 0.2765 | **0.2781** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | 0.99 | **0.99** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | 29 | **29** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.45 | **0.45** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | 0 | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | 0.9415 | **0.7972** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | 303.95 | **330.433** | ≤ taban |
| `prime_token` | ↓ | 84.0668 | 81.5131 | **81.2801** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | 0 | **0** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | 0.625 | **1** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | 0 | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | 1 | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | -0 | **0.5138** | > 0 |
| `yakalama` | ↑ | yok | -0.9809 | **-0.1079** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | 79.4 | **59.8** | <= 1 |
| `sicak_oran` | · | 1 | 1 | **1** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | yok | **0.0676** | <= 300 |
| `kesinti_kaybi` | ↓ | yok | yok | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | yok | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | yok | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | yok | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | yok | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | yok | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | yok | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 8.97 | 9.01 | **9.11** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.375 | 1 | 0 |
| B | düzeltme zincirleri | 0.2807 | 1 | 0 |
| D | tekrar kullanılan yordamlar | 0.4 | 1 | 0 |
| E | bağlam çakışması | 0.2021 | 0.95 | 19 |
| H | zaman komşuluğu | 0.4615 | 1 | 0 |
| J | dikiş | 0.4286 | 1 | 0 |
| K | gömülme | 0.1429 | 1 | 10 |

## Ölçekte gecikme

50000 düğüm · p50 **7.04 ms** · p95 **9.11 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/yasam_bench.py --etiket f3`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
