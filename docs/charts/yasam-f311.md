# Yaşam benchmark'ı — `f311`

Senaryo **yasam-90** · 191 soru · 1305 düğüm · kaynak `calisma-agaci` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | 0.4569 | **0.4237** | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | 0.9 | **0.75** | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | 27 | **18** | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.45 | **0.525** | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | 0 | **0** | <= 0 |
| `taze_ruh` | ↑ | 1 | 0.8006 | **0.7292** | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | 347.519 | **347.047** | ≤ taban |
| `prime_token` | ↓ | 84.0668 | 91.4804 | **76.4634** | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | 0 | **0** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | 0.875 | **0.875** | >= 0.85 |
| `dikis_recall` | ↑ | 0 | 0 | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | 1 | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | -0.0603 | **0.52** | > 0 |
| `yakalama` | ↑ | yok | -0.0981 | **-0.0981** | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | 1 | **1** | <= 1 |
| `sicak_oran` | · | 1 | 1 | **0.2337** | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | 0.1127 | **0.1076** | <= 300 |
| `uykusuz_kayip` | ↑ | yok | yok | **yok** | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | yok | **yok** | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | yok | **yok** | <= 0 |
| `tur_bloklama` | ↓ | yok | 9.4 | **8.77** | <= 50 |
| `kesinti_kaybi` | ↓ | yok | 0 | **yok** | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | 5.08 | **yok** | <= 500 |
| `yarim_damitma` | ↓ | yok | 0 | **yok** | <= 0 |
| `ritim_isabeti` | ↑ | yok | 1 | **yok** | >= 0.9 |
| `atalet` | ↓ | yok | 0 | **yok** | <= 0 |
| `buyume_p95` | ↓ | yok | yok | **6.099** | <= 1.5 |
| `buyume_ram` | ↓ | yok | yok | **1** | <= 2 |
| `gecikme_p95` | ↓ | 8.97 | 7.85 | **8.45** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.3023 | 0.4333 | 0 |
| B | düzeltme zincirleri | 0.3929 | 0.6875 | 0 |
| D | tekrar kullanılan yordamlar | 1 | 1 | 0 |
| E | bağlam çakışması | 0.3585 | 0.95 | 18 |
| H | zaman komşuluğu | 0.6667 | 1 | 0 |
| J | dikiş | 0.6667 | 1 | 0 |
| K | gömülme | 0.4 | 0.8 | 0 |

## Büyüme (P kümesi)

200000 / 20000 düğüm · p95 oranı **6.099** (hedef ≤ 1.5) · RAM oranı **1** (hedef ≤ 2)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/yasam_bench.py --etiket f311`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
