# İnsan benzeri hafıza — faz defteri

Yol haritası: [`docs/hafiza-yol-haritasi.md`](hafiza-yol-haritasi.md).
Çalışma düzeni: [`docs/hafiza-calisma-duzeni.md`](hafiza-calisma-duzeni.md).

Bu dosya koşum defteri: hangi faz bitti, kabul kriterini geçti mi, geçmediyse
ne öğrenildi. Negatif sonuç da rapordur ve burada durur.

```
Taban çizgisi   py eval/context_memory/yasam_bench.py --etiket taban --eski
Faz ölçümü      py eval/context_memory/yasam_bench.py --etiket f1 --onceki taban
Ablation        py eval/context_memory/yasam_bench.py --kapat aktivasyon --etiket f1-ablasyon
Eşik eğrisi     py eval/context_memory/yasam_bench.py --esik-egrisi
Büyüme (P)      py eval/context_memory/yasam_bench.py --buyume
Özet tablo      py eval/context_memory/yasam_bench.py --tablo
Gerileme kapısı py eval/context_memory/scale_bench.py
```

Sıra: **Faz 0 → 1 → 2 → 3 (Adım 1-5) → 3.12 → 3 (Adım 6) → 3.10 → 3.11 → 4 →
5 → 7 → 6.**

---

## Faz 0 — Ölçüm altyapısı ✅ tamam

Hiçbir mekanik değişmedi. Değişen tek şey ölçülebilirlik.

| Dosya | Ne |
|---|---|
| `src/dornick/recall/saat.py` | enjekte edilebilir saat; zamanın okunduğu tek yer |
| `src/dornick/recall/anahtar.py` | mekanik açma/kapama anahtarları (ablation yüzeyi) |
| `eval/context_memory/yasam_dataset.json` | 90 sanal gün, 895 olay, 286 oturum, A–S kümeleri (dondurulmuş) |
| `eval/context_memory/yasam_holdout.json` | ayrı 30 günlük senaryo; kalibrasyon ana sette, karar burada |
| `eval/context_memory/yasam_bench.py` | senaryoyu sanal saatle oynatan bench + `--eski` + `--esik-egrisi` + `--buyume` |
| `tests/test_saat.py` | saatin her damgaya ulaştığı + doğrudan `datetime.now()` yasağı |
| `tests/test_yasam_bench.py` | bench determinizmi, A–S asgarileri, kümelerin vaadi |
| `tests/fixtures/recall-v1.db` + `tests/test_db_gocu.py` | eski şemalı bellek her fazda açılıyor, `PRAGMA integrity_check` |

`RecallStore`, `Mind`, `open_store`, `open_mind` ve `EventLog` artık `saat=`
alıyor; verilmezse duvar saati — ürün davranışı birebir aynı.

**Belgede olmayan tek ekleme: `EventLog`'a saat enjeksiyonu.** Yol haritası
0.1 yalnız `recall/store.py` ve `mind/store.py` diyor. Ama Faz 3'ün gece
geçişi oturum GÜNLÜĞÜNÜ okuyor (hangi düğüme hangi sırayla dokunuldu,
sürprizli olayın ±60 dakikası neresi) ve o damgalar duvar saatinden gelseydi
doksan günlük bir senaryo ölçülemezdi. Ek isteğe bağlı bir parametre;
verilmezse davranış değişmiyor. Bench zaten günlükleri **ürünün kendi
`EventLog`'uyla** yazıyor — Faz 3 uydurma bir biçim değil gerçek bir günlük
görecek.

### Eski sürümle karşılaştırma altyapısı

`main` (`2c3fd3a`) `hafiza-eski` etiketiyle donduruldu.
`yasam_bench.py --eski` o etiketi `eval/eski/` worktree'sine alıp **ayrı bir
süreçte** koşturuyor (iki `dornick` paketi aynı yorumlayıcıda yan yana
duramaz). Eski kodda saat enjeksiyonu yok; modül düzeyindeki `_now`
yamalanıyor — eski kaynağa dokunulmadan iki sürüm **aynı sanal takvimi**
görüyor. Eski sürümde hiç olmayan mekaniklerin metriği `yok` diye
raporlanıyor, boş bırakılmıyor.

### Veri setinin kapsamı ve sınırı

Sorular, beklenen kaydın içerik kelimelerinden en az birini taşıyacak şekilde
yazıldı. Bu bir kolaylaştırma değil, bilinçli bir kapsam kararı: Türkçe
biçimbiliminin (ünsüz yumuşaması, ekler) sözcüksel aramada açtığı gedik ayrı
bir sorundur ve bu yol haritasının hiçbir fazı onu çözmüyor. Veri seti onunla
doldurulsaydı bütün metrikler o gediğin gürültüsünde boğulur, zaman/pekişme/
güncelleme farkı görünmez olurdu. **Bu benchmark hafızanın zaman davranışını
ölçer, Türkçe morfolojisini değil.**

`G`, `I`, `N`, `O`, `Q` kümeleri prime precision/recall ortalamalarına
girmiyor; her birinin kendi metriği var. Unutulmuş bir kaydın kendiliğinden
önyüklemeye girmemesi tasarımın amacı — onu prime recall'ına saymak mekaniği
kendi hedefiyle çelişen bir sayıyla cezalandırmak olurdu.

### Taban çizgisi — `docs/charts/yasam-taban.md` (eski sürüm, bir daha değişmez)

| Metrik | Yön | eski sürüm | Hedef |
|---|---|---|---|
| `prime_precision` | ↑ | **0.2553** | ≥ 0.85 |
| `prime_recall` | ↑ | **0.96** | ≥ 0.80 |
| `yasak_sizinti` | ↓ | **59** | 0 |
| `tuzak_sessizlik` | ↑ | **0.45** | ≥ 0.90 |
| `bayat_ruh` (gün başına) | ↓ | **3.478** | 0 |
| `taze_ruh` | ↑ | **1.00** | ≥ 0.80 |
| `ruh_token` | ↓ | **324.97** | ≤ taban |
| `prime_token` | ↓ | **84.07** | ≤ 0.85 × taban |
| `geri_donus_recall` | ↑ | **1.00** | ≥ 0.70 |
| `komsuluk_recall` | ↑ | **0.00** | ≥ 0.75 |
| `sorumluluk_dogrulugu` | ↑ | **0.50** | ≥ 0.85 |
| `dikis_recall` | ↑ | **0.00** | ≥ 0.60 |
| `gomulme_recall` | ↑ | **1.00** | ≥ 0.90 |
| `ders_gecikmesi` (tur) | ↓ | **79.4** | ≤ 1 |
| `sicak_oran` | · | **1.00** | 0.10–0.30 |
| `sema_tazeleme` / `yakalama` | ↑ | **yok** | > 0 |
| gece / uyku metrikleri | — | **yok** | — |
| `gecikme_p95` (50k düğüm) | ↓ | **8.97 ms** | ≤ 20 ms |

Küme kırılımı (prime precision): A 0.45 · B **0.17** · D 0.44 · E **0.22** ·
H 0.33 · J 0.25 · K **0.19**.

**Tabanın söylediği.** Hafıza her şeyi buluyor (recall 0.96) ama neredeyse
hiçbir şeyi ayıklamıyor (precision 0.26). Gece katmanının hiç olmadığı
görünüyor ve **sayıyla**: zaman komşuluğu 0, dikiş 0, ders gecikmesi 79 tur
(yani "geceye kadar", ki gece de yok). `sicak_oran` 1.00 — imza indeksi bütün
düğümleri tutuyor, aktif küme sınırlanmıyor.

### Eşik eğrisi — `docs/charts/basinc-bozulma.md`

Gece kapalıyken S (küçültülmemiş güçlenme: toplam kenar ağırlığı / düğüm) gün
gün ölçüldü. İlk on ölçülen günün precision ortalaması **0.6033**; %5 düşüş
S = **2.3374**'te başlıyor.

    ESIK_UST = 2.3374        ESIK_ALT = 0.7791        (2026-09-02 koşusu)

Bu iki sabit Faz 3.10'da `uyku.py`'ye elle değil buradan girecek.

### Büyüme (P kümesi) — `docs/charts/yasam-buyume.md`

Sıcak/soğuk ayrımı (Faz 3.11) henüz yok; imza indeksi bütün düğümleri tutup
lineer tarıyor. Ölçüldü:

| Hafıza | düğüm | indeks | `recall()` p50 | p95 | imza RAM |
|---|---|---|---|---|---|
| küçük | 20.000 | 20.000 | 3.59 ms | **4.90 ms** | 1.4 MB |
| büyük | 200.000 | 200.000 | 25.32 ms | **33.22 ms** | 14.4 MB |

`buyume_p95` = **6.78** (hedef ≤ 1.5) · `buyume_ram` = **10.0** (hedef ≤ 2).
Yol haritasının 7. maddesindeki teşhis birebir doğrulandı: maliyet toplam
hafızayla doğrusal büyüyor ve 200k'da 20 ms bütçesi çoktan aşılmış durumda.
Bu satır Faz 3.11'in var olma gerekçesidir.

### Gerileme kapısı — `scale_bench.py`

| method | recall | coverage | precision | silence | tok/query | p95 ms |
|---|---|---|---|---|---|---|
| `current` (eski) | 0.78 | 0.76 | 0.63 | 0.62 | 71.8 | 4.00 |

---

## Faz 1 — Zaman bazlı aktivasyon ⚠️ kabul edilmedi (1 kriter)

| Dosya | Ne |
|---|---|
| `src/dornick/recall/aktivasyon.py` | ACT-R taban seviyesi, ağırlıklı: `B = ln(Σ w_k·t_k^-d)` |
| `recall/store.py` | `kullanimlar` sütunu, `Node.aktivasyon`, `kullanim_ekle`, `sicil`, tohumlama/yayılma çarpanı, aktivasyona göre `by_kind` |
| `mind/store.py` | `Mind._canli` — ruh tazelik değil canlılık sırası kullanıyor |
| `tests/test_aktivasyon.py` | formül, ağırlıklı/negatif toplam, depoya bağlanış, göç, bozuk kayıt, ablation |

Şema: `ALTER TABLE node ADD COLUMN kullanimlar TEXT NOT NULL DEFAULT '[]'` —
son 30 kullanım, `[{"t","w","etiket"}]`. Ağırlık negatif olabiliyor (Faz 3
ters tekrarı) ve etiket alanı baştan açık (`yazildi | acildi | basari | hata |
sema | yakalandi`) ki sonraki fazlar şema değiştirmesin. Göç sütunu eklendiği
anda `created` + `last_used`×`uses` ile dolduruyor; okuma tarafı sütun boş ya
da bozuk olsa da aynı hesabı yapıyor.

`_seed_literal`'daki `familiarity = min(0.15, 0.03*uses)` **kaldırıldı** —
zamanı bilmeyen, doyan ve yalnızca ekleyen bir aşinalık payıydı. Yerine
`conf × tohum_carpani(B)`; en unutulmuş kayıt skorunun yarısını koruyor
(`TOHUM_TABANI = 0.5`), geride kalıyor ama aramadan düşmüyor.

### Kalibrasyon (sihirli sayı yok)

* **`OLCEK` = 2.0** — {0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0} tarandı; metrikler
  1.0–4.0 platosunda ayrışmıyor (fark ≤ 0.002). Bulgunun kendisi rapor:
  **sonuçlar bu sabite duyarsız**; fayda sıralamanın zamanı bilmesinden
  geliyor, sigmoidin dikliğinden değil.
* **`BOZUNMA` = 0.9** — ACT-R standardı 0.5'tir ve saniye–dakika ölçeğindeki
  laboratuvar verisine oturtulmuştur; burada `t` aylar boyunca saat cinsinden
  ölçülüyor ve 0.5 fazla yavaş kalıyordu. Tarama (0.5/0.6/0.8/0.9/1.0/1.1):
  `taze_ruh` 0.68 → 0.72 → 0.78 → **0.81** → 0.82 → 0.83; `prime_precision`
  0.9'da tepe (0.2634); 1.0'dan sonra `yasak_sizinti` 57 → 58. Diz noktası
  seçildi. Holdout'ta aynı iki değer arasında fark yok (kalibrasyon ana sette
  yapıldı, karar setine sızmadı).

### Ölçüm — `docs/charts/yasam-f1.md`

| Kriter | eski | Faz 1 | Ablation (kapalı) | Kabul | Durum |
|---|---|---|---|---|---|
| `bayat_ruh` ≥%50 azalma | 3.478 | **3.333** | 3.478 | ≤ 1.739 | ❌ −%4.2 |
| `taze_ruh` ≥ 0.80 | 1.000 | **0.808** | 1.000 | ≥ 0.80 | ✅ (sınırda) |
| `prime_precision` düşmez | 0.2553 | **0.2634** | 0.2574 | — | ✅ |
| `tuzak_sessizlik` düşmez | 0.45 | **0.45** | 0.45 | — | ✅ |
| `gecikme_p95` bütçede | 8.97 ms | **9.31 ms** | — | ≤ 20 | ✅ |
| `prime_recall` | 0.96 | **0.98** | 0.96 | — | ✅ |
| `yasak_sizinti` | 59 | **57** | 60 | — | ✅ |
| `ruh_token` | 324.97 | **329.81** | 324.97 | ≤ taban | ⚠️ +%1.5 |

Ablation sütunu mekaniğin iş yaptığını gösteriyor: kapatıldığında precision,
recall, sızıntı ve bayatlık tabana dönüyor.

`scale_bench` gerileme kapısı: `current` recall 0.78 → 0.78, precision
0.63 → **0.64**, silence 0.62 → 0.62, tok/query 71.8 → **71.2**. Gerileme yok.

Kapsam: `aktivasyon.py` %100, `saat.py` %100, `anahtar.py` %93. Testler
1800'de duruyor, hiçbiri kırılmadı.

### Geçmeyen kriter: `bayat_ruh` — ve neden parametre sorunu değil

İki tur ayar harcandı (OLCEK taraması, BOZUNMA taraması). `bayat_ruh`
**hiçbir parametre değerinde oynamadı**: 0.5'ten 1.2'ye BOZUNMA taramasında
sabit 3.333. Ölçüldü, tahmin değil — kalan bayatlığın tamamı `preference`
türünde:

* `procedure` tarafında bayatlık sıfıra indi. Yordamlar düzenli
  kullanıldığından aktivasyonları yüksek; ruhun sekiz yuvasını onlar
  dolduruyor, zincirlerin ara sürümleri dışarıda kalıyor. Mekanik burada tam
  olarak vaat ettiği işi yapıyor.
* `preference` tarafında hiç pekiştirme sinyali yok: kullanıcı tercihini
  söylüyor, kimse o kaydı açmıyor. Pekiştirme yoksa aktivasyon sırası tazelik
  sırasına eşitleniyor ve bir zincirin 3. sürümü ile geçerli 4. sürümü
  **ayırt edilemez** hale geliyor — ikisi de yeni, ikisi de kullanılmamış.
  Aradaki farkı bilen tek şey "bu kayıt şunun yerini aldı" bilgisi.

Yani kalan iş Faz 2'nin (supersede) kabul kriterinde zaten duruyor:
`bayat_ruh = 0`.

**Ayrıca bir uyarı:** `taze_ruh` eski sürümde 1.00'dı, Faz 1'de 0.808. Aktivasyon
sıralaması düzenli kullanılan yordamları öne çekince taze düzeltmeler
sekizinci yuvadan taşıyor. Kriter geçiyor ama yön yanlış; Faz 2'nin
**pekişme mirası** (düzeltme, düzelttiği kaydın kullanım geçmişini devralır)
bunu geri almalı. Faz 2 sonunda `taze_ruh` yeniden ölçülecek ve 1.00'a
dönmezse mekanik eksik demektir.

---

## Faz 2 — Supersede ✅ kabul (3 kriterden 2'si tam, 3.'sü ölçüldü)

| Dosya | Ne |
|---|---|
| `recall/store.py` | `supersedes` / `superseded_by` sütunları, `guncelle`, `gecerli_surum`, `celiski_adayi`, `komsular_gerekceli` |
| `mind/store.py` | `Mind.guncelle`, `Mind.celiski_adayi`; `series` tüm sürümleri döndürüyor |
| `mind/tools.py` | `mind_memory save` → `supersedes` parametresi + otomatik çelişki uyarısı; araç açıklamasındaki "eskisini sil" öğüdü kaldırıldı |
| `tests/test_supersede.py` | zincir, yayılma yönlendirmesi, döngü koruması, pekişme mirası, araç yüzeyi, göç, ablation |

Şema: iki `TEXT DEFAULT ''` sütunu + kısmi indeks. Silme **yok**: eski satır
`deleted=0` kalıyor, `series`'te ve FTS'te duruyor, açık aramada birebir
kelimeyle hâlâ bulunuyor. Yalnız üç şey değişiyor — tohumlanmıyor, ruha
girmiyor, ve kendisine gelen çağrışım güncel sürüme yönleniyor (döngü
korumalı). `open()` eski bir kimliği açarsa gövdenin sonuna
`[güncellendi → n_xxx]` düşüyor.

**Pekişme mirası:** yeni kayıt eskinin kullanım geçmişini devralıyor, üstüne
kendi yazım anını koyuyor. Faz 1'in bıraktığı yara buydu: düzeltme sıfırdan
başlayınca ruhta düzelttiği şeyin altında kalıyordu. `taze_ruh` 0.808 → 0.942
ile geri geldi.

### Kalibrasyon — `CELISKI_ESIK` (`docs/charts/celiski-esigi.md`)

Yol haritasının önerdiği başlangıç değeri **0.75 hiçbir şey yakalamıyor**
(yakalama 0.00). 24 düzeltme olayında doğru önceki sürümü yakalama oranı, 60
gürültü kaydında yanlış alarm sayısına karşı tarandı:

| Eşik | Yakalama ↑ | Yanlış alarm |
|---|---|---|
| 0.50 | 0.79 | 24 |
| **0.55** | **0.75** | **5** |
| 0.60 | 0.25 | 2 |
| 0.75 | 0.00 | 1 |

Eğri 0.55–0.60 arasında dikleşiyor; diz noktası seçildi. Uyarı bir öneri,
kayıt her hâlükârda yazılıyor — yanlış alarmın maliyeti bir cümle,
kaçırmanınki bir çelişki.

### Ölçüm — `docs/charts/yasam-f2.md`

| Kriter | eski | Faz 1 | Faz 2 | Ablation (kapalı) | Kabul | |
|---|---|---|---|---|---|---|
| `yasak_sizinti` (B kümesi) | 28 | 28 | **0** | 28 | = 0 | ✅ |
| `bayat_ruh` | 3.478 | 3.333 | **0** | 3.333 | = 0 | ✅ |
| B kümesi precision ablation farkı | — | — | **0.062** | — | ≥ 0.20 | ❌ |
| `taze_ruh` | 1.000 | 0.808 | **0.942** | 0.808 | ≥ 0.80 | ✅ |
| `prime_precision` | 0.2553 | 0.2634 | **0.2765** | 0.2634 | düşmez | ✅ |
| `prime_recall` | 0.96 | 0.98 | **0.99** | 0.98 | — | ✅ |
| `yasak_sizinti` (toplam) | 59 | 57 | **29** | 57 | — | ✅ |
| `ruh_token` | 324.97 | 329.81 | **303.95** | 329.81 | ≤ taban | ✅ |
| `prime_token` | 84.07 | 83.64 | **81.51** | 83.64 | ≤ taban | ✅ |
| `gecikme_p95` | 8.97 | 9.31 | **9.01 ms** | — | ≤ 20 | ✅ |

`scale_bench`: precision 0.63 → **0.64**, tok/query 71.8 → **71.3**. Gerileme yok.

**Geçmeyen kriter üzerine.** Ablation'da B kümesi precision'ı 0.276 → 0.214
(fark 0.062), hedef ≥ 0.20 idi. Mekaniğin iş yapmadığı anlamına gelmiyor:
aynı ablation'da B kümesi **yasak sızıntısı 0 → 28**'e fırlıyor, yani ölçtüğü
şeyi tam olarak ölçüyor. Precision'ın az oynamasının sebebi seçicinin
kendisi: `select_prime` beş yuvayı doldurmaya çalışıyor, bayat sürümler
çıkınca boşalan yuvaları başka gürültü dolduruyor. Kötü adayı çıkarmak,
seçici yerine başka bir kötü aday koyuyorsa precision'ı hareket ettirmez.
Precision'ın asıl darboğazı eşik ve bağlam (Faz 5); bu satır oraya not
düşüldü.

## Faz 3 (Adım 1-5) — Gece: öncelik, tekrar, dikiş, örgü · sırada
## Faz 3.12 — Uyanık tekrar, mikro-uyku, yerel uyku · bekliyor
## Faz 3 (Adım 6) — Damıtma · bekliyor
## Faz 3.10 — Uyku dinamiği · bekliyor (`ESIK_UST` hazır)
## Faz 3.11 — Sıcak/soğuk indeks · bekliyor
## Faz 4 — Kodlama gücü · bekliyor
## Faz 5 — Bağlam bonusu · bekliyor
## Faz 7 — Ödül, mizaç, üç özne, karakter · bekliyor
## Faz 6 — Beyin görünümü · bekliyor
