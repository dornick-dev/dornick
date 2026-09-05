# Yaşam benchmark'ı — `son`

Senaryo **yasam-90** · 191 soru · 275 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | — | **0.6747** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | — | **0.68** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | — | **3** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | — | **0.975** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | — | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | — | **1** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | — | **309.964** | ≤ taban |
| `prime_token` | ↓ | 84.4791 | — | **29.1414** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | — | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | — | **0.0833** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | — | **0.875** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | — | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | — | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | — | **0.4099** | > 0 |
| `yakalama` | ↑ | yok | — | **0.2051** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | — | **1** | <= 1 |
| `sicak_oran` | · | 1 | — | **0.2145** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | — | **0.0469** | <= 300 |
| `uykusuz_kayip` | ↑ | yok | — | **yok** | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | — | **yok** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | — | **yok** | <= 0 |
| `tur_bloklama` | ↓ | yok | — | **7.49** | <= 50 |
| `kesinti_kaybi` | ↓ | yok | — | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | — | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | — | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | — | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | — | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | — | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | — | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 9.32 | — | **4.98** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.5833 | 0.6333 | 0 |
| B | düzeltme zincirleri | 0.7333 | 0.6875 | 0 |
| D | tekrar kullanılan yordamlar | 1 | 0.6667 | 0 |
| E | bağlam çakışması | 0.75 | 0.45 | 0 |
| H | zaman komşuluğu | 1 | 1 | 0 |
| J | dikiş | 1 | 1 | 0 |
| K | gömülme | 0.3182 | 0.7 | 3 |

## Ölçekte gecikme

50000 düğüm · p50 **3.7 ms** · p95 **4.98 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/life_bench.py --label son`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
