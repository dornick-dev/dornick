# Yaşam benchmark'ı — `f3d`

Senaryo **yasam-90** · 191 soru · 1389 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | 0.2781 | **0.4564** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | 0.99 | **0.89** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | 29 | **26** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.45 | **0.45** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | 0 | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | 0.7934 | **0.7865** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | 343.917 | **345.986** | ≤ taban |
| `prime_token` | ↓ | 84.0668 | 83.3665 | **91.4254** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | 0 | **0** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | 0.875 | **0.875** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | 0 | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | 1 | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | 0.376 | **-0.1054** | > 0 |
| `yakalama` | ↑ | yok | -0.0897 | **-0.0981** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | 1 | **1** | <= 1 |
| `sicak_oran` | · | 1 | 1 | **1** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | 0.0656 | **0.1121** | <= 300 |
| `uykusuz_kayip` | ↑ | yok | 1.143 | **yok** | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | 0.379 | **yok** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | 0 | **yok** | <= 0 |
| `tur_bloklama` | ↓ | yok | 9.2 | **9.76** | <= 50 |
| `kesinti_kaybi` | ↓ | yok | yok | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | yok | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | yok | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | yok | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | yok | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | yok | **yok** | <= 1.5 |
| `buyume_ram` | ↓ | yok | yok | **yok** | <= 2 |
| `gecikme_p95` | ↓ | 8.97 | 16.65 | **8.43** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.4821 | 0.9 | 0 |
| B | düzeltme zincirleri | 0.44 | 0.6875 | 0 |
| D | tekrar kullanılan yordamlar | 0.6 | 1 | 0 |
| E | bağlam çakışması | 0.3617 | 0.85 | 16 |
| H | zaman komşuluğu | 0.6316 | 1 | 0 |
| J | dikiş | 0.6667 | 1 | 0 |
| K | gömülme | 0.3448 | 1 | 10 |

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/yasam_bench.py --etiket f3d`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
