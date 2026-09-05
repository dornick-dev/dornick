# Yaşam benchmark'ı — `holdout-taban`

Senaryo **yasam-holdout-30** · 34 soru · 47 düğüm · kaynak `hafiza-eski` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | — | — | **0.3846** | >= 0.85 |
| `prime_recall` | ↑ | — | — | **1** | >= 0.8 |
| `yasak_sizinti` | ↓ | — | — | **12** | <= 0 |
| `tuzak_sessizlik` | ↑ | — | — | **0.75** | >= 0.9 |
| `bayat_ruh` | ↓ | — | — | **1.6333** | <= 0 |
| `taze_ruh` | ↑ | — | — | **1** | >= 0.8 |
| `ruh_token` | ↓ | — | — | **130.025** | ≤ taban |
| `prime_token` | ↓ | — | — | **56.3382** | ≤ taban |
| `geri_donus_recall` | ↑ | — | — | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | — | — | **yok** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | — | — | **yok** | >= 0.85 |
| `dikis_recall` | ↑ | — | — | **yok** | >= 0.6 |
| `gomulme_recall` | ↑ | — | — | **yok** | >= 0.9 |
| `sema_tazeleme` | ↑ | — | — | **yok** | > 0 |
| `yakalama` | ↑ | — | — | **yok** | > 0 |
| `ders_gecikmesi` | ↓ | — | — | **yok** | <= 1 |
| `sicak_oran` | · | — | — | **1** | 0.10–0.30 |
| `gece_suresi` | ↓ | — | — | **yok** | <= 300 |
| `uykusuz_kayip` | ↑ | — | — | **yok** | >= 0.8 |
| `uykusuz_sisme` | ↓ | — | — | **yok** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | — | — | **yok** | <= 0 |
| `tur_bloklama` | ↓ | — | — | **yok** | <= 50 |
| `kesinti_kaybi` | ↓ | — | — | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | — | — | **yok** | <= 500 |
| `yarim_damitma` | ↓ | — | — | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | — | — | **yok** | >= 0.9 |
| `atalet` | ↓ | — | — | **yok** | <= 0 |
| `buyume_p95` | ↓ | — | — | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | — | — | **yok** | <= 2 |
| `gecikme_p95` | ↓ | — | — | **11.75** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.8889 | 1 | 0 |
| B | düzeltme zincirleri | 0.2353 | 1 | 6 |
| D | tekrar kullanılan yordamlar | 0.5 | 1 | 0 |
| E | bağlam çakışması | 0.2727 | 1 | 6 |
| H | zaman komşuluğu | yok | yok | 0 |
| J | dikiş | yok | yok | 0 |
| K | gömülme | yok | yok | 0 |

## Ölçekte gecikme

50000 düğüm · p50 **8.49 ms** · p95 **11.75 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/life_bench.py --label holdout-taban`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
