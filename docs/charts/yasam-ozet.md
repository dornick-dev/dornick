# Yaşam benchmark'ı — birikmiş özet

| Metrik | Yön | taban | f1 | f2 | f3 | f312 | f3d | f310 | f311 | f5 | f1-aktivasyonsuz | f2-supersedesiz | f3-orgusuz | buyume | Hedef |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | 0.2634 | 0.2765 | 0.2781 | 0.2781 | 0.4564 | 0.4569 | 0.4237 | 0.4412 | 0.2574 | 0.2634 | 0.2765 | 0.2634 | >= 0.85 |
| `prime_recall` | ↑ | 0.96 | 0.98 | 0.99 | 0.99 | 0.99 | 0.89 | 0.9 | 0.75 | 0.75 | 0.96 | 0.98 | 0.99 | 0.98 | >= 0.8 |
| `yasak_sizinti` | ↓ | 59 | 57 | 29 | 29 | 29 | 26 | 27 | 18 | 1 | 60 | 57 | 29 | 57 | <= 0 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.45 | 0.45 | 0.45 | 0.45 | 0.45 | 0.45 | 0.525 | 0.5 | 0.45 | 0.45 | 0.45 | 0.45 | >= 0.9 |
| `bayat_ruh` | ↓ | 3.4778 | 3.3333 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3.4778 | 3.3333 | 0 | 3.3333 | <= 0 |
| `taze_ruh` | ↑ | 1 | 0.8082 | 0.9415 | 0.7972 | 0.7934 | 0.7865 | 0.8006 | 0.7292 | 0.6943 | 1 | 0.8082 | 0.9415 | 0.8082 | >= 0.8 |
| `ruh_token` | ↓ | 324.972 | 329.811 | 303.95 | 330.433 | 343.917 | 345.986 | 347.519 | 347.047 | 347.903 | 324.972 | 329.811 | 303.95 | 329.811 | ≤ taban |
| `prime_token` | ↓ | 84.0668 | 83.6387 | 81.5131 | 81.2801 | 83.3665 | 91.4254 | 91.4804 | 76.4634 | 74.0183 | 81.8181 | 83.6387 | 81.5131 | 83.6387 | ≤ taban |
| `geri_donus_recall` | ↑ | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | >= 0.7 |
| `komsuluk_recall` | ↑ | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | >= 0.75 |
| `sorumluluk_dogrulugu` | ↑ | 0.5 | 0.625 | 0.625 | 1 | 0.875 | 0.875 | 0.875 | 0.875 | 0.875 | 0.625 | 0.625 | 0.625 | 0.625 | >= 0.85 |
| `dikis_recall` | ↑ | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | >= 0.6 |
| `gomulme_recall` | ↑ | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | >= 0.9 |
| `sema_tazeleme` | ↑ | yok | -0 | -0 | 0.5138 | 0.376 | -0.1054 | -0.0603 | 0.52 | 0.7992 | -0 | -0 | -0 | -0 | > 0 |
| `yakalama` | ↑ | yok | -0.9809 | -0.9809 | -0.1079 | -0.0897 | -0.0981 | -0.0981 | -0.0981 | 0.0059 | -0.9809 | -0.9809 | -0.0007 | -0.9809 | > 0 |
| `ders_gecikmesi` | ↓ | 79.4 | 79.4 | 79.4 | 59.8 | 1 | 1 | 1 | 1 | 1 | 79.4 | 79.4 | 79.4 | 79.4 | <= 1 |
| `sicak_oran` | · | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0.2337 | 0.2215 | 1 | 1 | 1 | 1 | 0.10–0.30 |
| `gece_suresi` | ↓ | yok | yok | yok | 0.0676 | 0.0656 | 0.1121 | 0.1127 | 0.1076 | 0.1227 | yok | yok | 0 | yok | <= 300 |
| `uykusuz_kayip` | ↑ | yok | yok | yok | yok | 1.143 | yok | yok | yok | yok | yok | yok | yok | yok | >= 0.8 |
| `uykusuz_sisme` | ↓ | yok | yok | yok | yok | 0.379 | yok | yok | yok | yok | yok | yok | yok | yok | <= 1.3 |
| `aktif_bolge_ihlali` | ↓ | yok | yok | yok | yok | 0 | yok | yok | yok | yok | yok | yok | yok | yok | <= 0 |
| `tur_bloklama` | ↓ | yok | yok | yok | yok | 9.2 | 9.76 | 9.4 | 8.77 | 10.71 | yok | yok | yok | yok | <= 50 |
| `kesinti_kaybi` | ↓ | yok | yok | yok | yok | yok | yok | 0 | yok | yok | yok | yok | yok | yok | <= 0 |
| `kesinti_gecikmesi` | ↓ | yok | yok | yok | yok | yok | yok | 5.08 | yok | yok | yok | yok | yok | yok | <= 500 |
| `yarim_damitma` | ↓ | yok | yok | yok | yok | yok | yok | 0 | yok | yok | yok | yok | yok | yok | <= 0 |
| `ritim_isabeti` | ↑ | yok | yok | yok | yok | yok | yok | 1 | yok | yok | yok | yok | yok | yok | >= 0.9 |
| `atalet` | ↓ | yok | yok | yok | yok | yok | yok | 0 | yok | yok | yok | yok | yok | yok | <= 0 |
| `buyume_p95` | ↓ | yok | yok | yok | yok | yok | yok | yok | 6.099 | yok | yok | yok | yok | 6.78 | <= 1.5 |
| `buyume_ram` | ↓ | yok | yok | yok | yok | yok | yok | yok | 1 | yok | yok | yok | yok | 10 | <= 2 |
| `gecikme_p95` | ↓ | 8.97 | 9.31 | 9.01 | 9.11 | 16.65 | 8.43 | 7.85 | 8.45 | 5.27 | 5.43 | 2.14 | 2.31 | 2.12 | <= 20 |
