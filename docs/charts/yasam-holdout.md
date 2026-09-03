# Yaşam benchmark'ı — `holdout`

Senaryo **yasam-holdout-30** · 34 soru · 43 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.3846 | — | **0.475** | >= 0.85 |
| `prime_recall` | ↑ | 1 | — | **0.95** | >= 0.8 |
| `yasak_sizinti` | ↓ | 12 | — | **5** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.75 | — | **0.75** | >= 0.9 |
| `bayat_ruh` | ↓ | 1.6333 | — | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | — | **1** | >= 0.8 |
| `ruh_token` | ↓ | 130.025 | — | **113.783** | ≤ taban |
| `prime_token` | ↓ | 56.3382 | — | **50.4118** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | — | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | yok | — | **yok** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | yok | — | **yok** | >= 0.85 |
| `dikis_recall` | ↑ | yok | — | **yok** | >= 0.6 |
| `gomulme_recall` | ↑ | yok | — | **yok** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | — | **yok** | > 0 |
| `yakalama` | ↑ | yok | — | **yok** | > 0 |
| `ders_gecikmesi` | ↓ | yok | — | **yok** | <= 1 |
| `sicak_oran` | · | 1 | — | **0.8837** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | — | **0.0165** | <= 300 |
| `uykusuz_kayip` | ↑ | yok | — | **yok** | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | — | **yok** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | — | **yok** | <= 0 |
| `tur_bloklama` | ↓ | yok | — | **7.47** | <= 50 |
| `kesinti_kaybi` | ↓ | yok | — | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | — | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | — | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | — | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | — | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | — | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | — | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 11.19 | — | **7.84** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.8889 | 1 | 0 |
| B | düzeltme zincirleri | 0.4444 | 1 | 0 |
| D | tekrar kullanılan yordamlar | 0.5 | 1 | 0 |
| E | bağlam çakışması | 0.2778 | 0.8333 | 5 |
| H | zaman komşuluğu | yok | yok | 0 |
| J | dikiş | yok | yok | 0 |
| K | gömülme | yok | yok | 0 |

## Ölçekte gecikme

50000 düğüm · p50 **4.37 ms** · p95 **7.84 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/yasam_bench.py --etiket holdout`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
