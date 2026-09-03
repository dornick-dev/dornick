# Yaşam benchmark'ı — `son`

Senaryo **yasam-90** · 191 soru · 275 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | — | **0.2741** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | — | **0.88** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | — | **6** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | — | **0.475** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | — | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | — | **1** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | — | **310.756** | ≤ taban |
| `prime_token` | ↓ | 84.4791 | — | **78.3639** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | — | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | — | **0.0833** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | — | **1** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | — | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | — | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | — | **0.6841** | > 0 |
| `yakalama` | ↑ | yok | — | **0.0114** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | — | **1** | <= 1 |
| `sicak_oran` | · | 1 | — | **0.7745** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | — | **0.0598** | <= 300 |
| `uykusuz_kayip` | ↑ | yok | — | **yok** | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | — | **yok** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | — | **yok** | <= 0 |
| `tur_bloklama` | ↓ | yok | — | **6.86** | <= 50 |
| `kesinti_kaybi` | ↓ | yok | — | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | — | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | — | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | — | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | — | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | — | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | — | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 8.43 | — | **5.31** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.2958 | 0.7 | 0 |
| B | düzeltme zincirleri | 0.2759 | 1 | 0 |
| D | tekrar kullanılan yordamlar | 0.4615 | 1 | 0 |
| E | bağlam çakışması | 0.2159 | 0.95 | 3 |
| H | zaman komşuluğu | 0.4583 | 0.9167 | 0 |
| J | dikiş | 0.4286 | 1 | 0 |
| K | gömülme | 0.1698 | 0.9 | 3 |

## Ölçekte gecikme

50000 düğüm · p50 **3.29 ms** · p95 **5.31 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/life_bench.py --label son`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
