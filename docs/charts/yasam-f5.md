# Yaşam benchmark'ı — `f5`

Senaryo **yasam-90** · 191 soru · 1296 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | 0.4237 | **0.4412** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | 0.75 | **0.75** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | 18 | **1** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.525 | **0.5** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | 0 | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | 0.7292 | **0.6943** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | 347.047 | **347.903** | ≤ taban |
| `prime_token` | ↓ | 84.0668 | 76.4634 | **74.0183** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | 0 | **0** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | 0.875 | **0.875** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | 0 | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | 1 | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | 0.52 | **0.7992** | > 0 |
| `yakalama` | ↑ | yok | -0.0981 | **0.0059** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | 1 | **1** | <= 1 |
| `sicak_oran` | · | 1 | 0.2337 | **0.2215** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | 0.1076 | **0.1227** | <= 300 |
| `uykusuz_kayip` | ↑ | yok | yok | **yok** | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | yok | **yok** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | yok | **yok** | <= 0 |
| `tur_bloklama` | ↓ | yok | 8.77 | **10.71** | <= 50 |
| `kesinti_kaybi` | ↓ | yok | yok | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | yok | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | yok | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | yok | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | yok | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | 6.099 | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | 1 | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 8.97 | 8.45 | **5.27** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.3182 | 0.4667 | 0 |
| B | düzeltme zincirleri | 0.375 | 0.75 | 0 |
| D | tekrar kullanılan yordamlar | 0.75 | 1 | 0 |
| E | bağlam çakışması | 0.4359 | 0.85 | 0 |
| H | zaman komşuluğu | 0.6316 | 1 | 0 |
| J | dikiş | 0.75 | 1 | 0 |
| K | gömülme | 0.4 | 0.8 | 1 |

## Ölçekte gecikme

50000 düğüm · p50 **3.42 ms** · p95 **5.27 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/yasam_bench.py --etiket f5`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
