# Yaşam benchmark'ı — `taban`

Senaryo **yasam-90** · 191 soru · 288 düğüm · kaynak `hafiza-eski` · kapalı mekanik `yok`

| Metrik | Yön | eski | önceki | bu faz | Hedef |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | — | — | **0.2553** | >= 0.85 |
| `prime_recall` | ↑ | — | — | **0.96** | >= 0.8 |
| `yasak_sizinti` | ↓ | — | — | **59** | <= 0 |
| `tuzak_sessizlik` | ↑ | — | — | **0.45** | >= 0.9 |
| `bayat_ruh` | ↓ | — | — | **3.4778** | <= 0 |
| `taze_ruh` | ↑ | — | — | **1** | >= 0.8 |
| `ruh_token` | ↓ | — | — | **324.972** | ≤ taban |
| `prime_token` | ↓ | — | — | **84.4791** | ≤ taban |
| `geri_donus_recall` | ↑ | — | — | **1** | >= 0.7 |
| `komsuluk_recall` | ↑ | — | — | **0** | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | — | — | **0.5** | >= 0.85 |
| `dikis_recall` | ↑ | — | — | **0** | >= 0.6 |
| `gomulme_recall` | ↑ | — | — | **1** | >= 0.9 |
| `sema_tazeleme` | ↑ | — | — | **yok** | > 0 |
| `yakalama` | ↑ | — | — | **yok** | > 0 |
| `ders_gecikmesi` | ↓ | — | — | **79.4** | <= 1 |
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
| `gecikme_p95` | ↓ | — | — | **9.32** | <= 20 |

## Küme kırılımı (prime precision / recall)

| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |
|---|---|---|---|---|
| A | sabit gerçekler | 0.3659 | 1 | 0 |
| B | düzeltme zincirleri | 0.1739 | 0.75 | 29 |
| D | tekrar kullanılan yordamlar | 0.3333 | 1 | 0 |
| E | bağlam çakışması | 0.2083 | 1 | 20 |
| H | zaman komşuluğu | 0.4444 | 1 | 0 |
| J | dikiş | 0.4286 | 1 | 0 |
| K | gömülme | 0.1429 | 1 | 10 |

## Ölçekte gecikme

50000 düğüm · p50 **6.81 ms** · p95 **9.32 ms** (bütçe 20 ms)

---

`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.

Üretim: `py eval/context_memory/life_bench.py --label taban`. Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, aynı sonuç.
