# Yaşam benchmark'ı — `f312`

Senaryo **yasam-90** · 191 soru · 282 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | 0.2781 | **0.2781** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | 0.99 | **0.99** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | 29 | **29** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.45 | **0.45** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | 0 | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | 0.7972 | **0.7934** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | 330.433 | **343.917** | ≤ taban |
| `prime_token` | ↓ | 84.0668 | 81.2801 | **83.3665** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | 0 | **0** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | 1 | **0.875** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | 0 | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | 1 | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | 0.5138 | **0.376** | > 0 |
| `yakalama` | ↑ | yok | -0.1079 | **-0.0897** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | 59.8 | **1** | <= 1 |
| `sicak_oran` | · | 1 | 1 | **1** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | 0.0676 | **0.0656** | <= 300 |
| `uykusuz_kayip` | ↑ | yok | yok | **1.143** | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | yok | **0.379** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | yok | **0** | <= 0 |
| `tur_bloklama` | ↓ | yok | yok | **9.2** | <= 50 |
| `kesinti_kaybi` | ↓ | yok | yok | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | yok | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | yok | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | yok | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | yok | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | yok | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | yok | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 8.97 | 9.11 | **16.65** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.375 | 1 | 0 |
| B | düzeltme zincirleri | 0.2759 | 1 | 0 |
| D | tekrar kullanılan yordamlar | 0.4 | 1 | 0 |
| E | bağlam çakışması | 0.2021 | 0.95 | 19 |
| H | zaman komşuluğu | 0.4615 | 1 | 0 |
| J | dikiş | 0.4286 | 1 | 0 |
| K | gömülme | 0.1449 | 1 | 10 |

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/yasam_bench.py --etiket f312`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
