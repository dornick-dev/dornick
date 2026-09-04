# İnsan benzeri hafıza — faz defteri

Yol haritası: [`docs/hafiza-yol-haritasi.md`](hafiza-yol-haritasi.md).
Çalışma düzeni: [`docs/hafiza-calisma-duzeni.md`](hafiza-calisma-duzeni.md).

Bu dosya koşum defteri: hangi faz bitti, kabul kriterini geçti mi, geçmediyse
ne öğrenildi. Negatif sonuç da rapordur ve burada durur.

```
Taban çizgisi   py eval/context_memory/life_bench.py --label taban --old
Faz ölçümü      py eval/context_memory/life_bench.py --label f1 --previous taban
Ablation        py eval/context_memory/life_bench.py --disable activation --label f1-ablasyon
Eşik eğrisi     py eval/context_memory/life_bench.py --threshold-curve
Büyüme (P)      py eval/context_memory/life_bench.py --growth
Özet tablo      py eval/context_memory/life_bench.py --table
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
| `eval/context_memory/life_bench.py` | senaryoyu sanal saatle oynatan bench + `--old` + `--threshold-curve` + `--growth` |
| `tests/test_saat.py` | saatin her damgaya ulaştığı + doğrudan `datetime.now()` yasağı |
| `tests/test_life_bench.py` | bench determinizmi, A–S asgarileri, kümelerin vaadi |
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
`life_bench.py --old` o etiketi `eval/eski/` worktree'sine alıp **ayrı bir
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

---

## Faz 3 (Adım 1-5) — Gece: tekrar, sorumluluk, dikiş, örgü ⚠️ kabul edilmedi (2 kriter)

| Dosya | Ne |
|---|---|
| `src/dornick/recall/orgu.py` | `gece_gecisi` — öncelik, ileri tekrar, şema tazelemesi, yakalama, ters tekrar, dikiş, yeniden örgü, küçültme |
| `recall/store.py` | `baglan` (birikimli/yalnız-yeni), `kenarlari_kucult` |
| `session.py` | `Session.sonuc()` — oturum nasıl bitti; kapanışta günlüğe yazılıyor |
| `loop.py` | önyüklenen kayıtlar `prime` notu olarak günlüğe düşüyor |
| `mind/tools.py` | `mind_recall` artık `open()` çağırıyor (üretimde pekiştirme hiç olmuyordu) ve `[3 başarı / 1 hata]` sicilini gösteriyor |
| `tests/test_orgu.py` | 24 test: beş adımın her biri, bütçe/devretme, filigran, damıtma kapısı, ablation |

Atomik birim tek oturumun tekrarı; bütçe biterse kalanlar **devrediyor**,
atlanmıyor. Filigran oturum bazında — tamamlanmış oturum ikinci kez pay
dağıtmıyor (çift sayım testi var).

### Kalibrasyon

* **`BASARI_PAYI` / `HATA_PAYI` = 1.0 / −0.8** — yol haritasının önerdiği
  (0.5, −0.3) çifti `sorumluluk_dogrulugu`'nu 0.75'te bırakıyor: tek bir
  başarı/hata payı, kaydın kendi tazeliğinin altında kalıp sıralamayı
  çeviremiyor. (0.7,−0.5) ve (0.5,−0.6) de yetmedi; (1.0,−0.8) hedefi
  geçti (**1.00**). Diğer metrikler bu aralıkta duyarsız.
* **`YAKALAMA_ESIK` kalibre EDİLEMEDİ.** 0.35–0.70 arası tarandı, `yakalama`
  hiç oynamadı (−0.108 sabit). Sebep ölçüldü: 500 düğümlük bir bellekte
  "sabah kahvesi içildi"nin sürprizi **0.389**, "ana pano yandı, saha
  elektriksiz kaldı"nınki **0.422**. Sürpriz vekili (1 − en yakın komşu
  skoru) bu ölçekte sıradan ile felaketi ayırt edemiyor; ayıramayan bir
  sinyalin eşiği de ayarlanamaz. **Faz 4'ün kodlama gücü aynı vekile
  dayanıyor; aynı duvara çarpması beklenmeli.**
* `MIN_ACTIVATION` 0.02 → 0.0005 tarandı; `komsuluk_recall` hiç oynamadı.
  Yani eşik değil, sıralama sorunu (aşağıda).

### Ölçüm — `docs/charts/yasam-f3.md`

| Kriter | Faz 2 | Faz 3 | Ablation | Kabul | |
|---|---|---|---|---|---|
| `sorumluluk_dogrulugu` | 0.625 | **1.000** | 0.625 | ≥ 0.85 | ✅ |
| `sema_tazeleme` | −0.000 | **0.514** | −0.000 | > 0 | ✅ |
| `gomulme_recall` | 1.00 | **1.00** | 1.00 | ≥ 0.90 | ✅ |
| `geri_donus_recall` | 1.00 | **1.00** | 1.00 | ≥ 0.70 | ✅ |
| `gece_suresi` | yok | **0.068 sn** | — | ≤ 300 sn | ✅ |
| `prime_precision` | 0.2765 | **0.2781** | 0.2765 | düşmez | ✅ |
| `tuzak_sessizlik` | 0.45 | **0.45** | 0.45 | düşmez | ✅ |
| `komsuluk_recall` | 0 | **0** | 0 | ≥ 0.75 | ❌ |
| `dikis_recall` | 0 | **0** | 0 | ≥ 0.60 | ❌ |
| `yakalama` | −0.981 | **−0.108** | −0.001 | > 0 | ❌ |
| `ders_gecikmesi` | 79.4 | **59.8** | 79.4 | ≤ 1 | ❌ (Faz 3.12'nin işi) |
| `taze_ruh` | 0.942 | **0.797** | 0.942 | ≥ 0.80 | ⚠️ sınırın altında |
| `ruh_token` | 304.0 | **330.4** | 304.0 | ≤ taban (325) | ⚠️ |

Bir gecede: 236 oturum tekrar edildi, 1609 zaman komşuluğu kenarı, 14 dikiş,
2412 örgü kenarı, 7170 şema dokunuşu, 12 ders yazıldı, 195.768 kenar
küçültüldü. Ablation kapalıyken hepsi Faz 2'ye dönüyor.

`scale_bench`: precision 0.64, tok/query 71.3 — gerileme yok.

### Neden `komsuluk_recall` ve `dikis_recall` sıfır — ölçülmüş kök neden

Kenarlar **var**: H çiftinin arasında `birlikte kullanıldı (h_h01_19)`
gerekçeli, ağırlığı 0.471 bir kenar duruyor. Sorun yayılmanın sıralamaya
girememesi. Tek bir sorgunun izi:

```
hop 0 (tohum):  0.733  0.620  0.594  0.573  0.499  0.482  0.474  0.463  0.455
hop 1 (komşu):  0.084   ← zaman komşuluğu kenarının taşıdığı en yüksek değer
```

`_seed` yirmi aday döndürüyor ve hepsi 0.45–0.73 aralığında. Bir hop-1
düğümün üste çıkabilmesi için `kaynak_skor × kenar × HOP_DECAY ×
aktivasyon_carpani` çarpımının beşinci tohumu geçmesi gerekiyor; çarpanların
tavanı bunu **yapısal olarak imkânsız** kılıyor (0.73 × 0.47 × 0.45 × 0.14 ≈
0.02). Eşik düşürmek işe yaramıyor (yukarıdaki tarama), çünkü sorun kesme
değil sıralama.

Kök neden Faz 0 taban çizgisinin de söylediği şey: **tohum doygunluğu**.
Ortak tek bir kelimeyi paylaşan yirmi kayıt 0.5 üstü skor alıyor; bu hem
`prime_precision`'ı 0.28'de tutuyor hem de çağrışıma yer bırakmıyor. Yol
haritası bu duvarı iki yerde adlandırıyor: bağlam bonusu (Faz 5) ve
`vector.py` için opsiyonel IDF. İkisi de bu fazın kapsamı dışında; sonuç
buraya yazıldı, Faz 5'te yeniden ölçülecek.

### Yan etki: ruh şişti

Gece `lesson`, `procedure` ve `goal` yazıyor; bunlar ruha giriyor ve hem
`ruh_token`'ı (304 → 330) hem de `taze_ruh`'u (0.942 → 0.797) bozuyor.
Gecenin yazdığı ders gerçek bir kazanç ama ruhun sekiz yuvası için taze
düzeltmeyle yarışıyor. Damıtma (Adım 6) ve sıcak/soğuk ayrımı (3.11) bu
baskıyı azaltmalı; ikisi de sonraki PR'lar.

---

## Faz 3.12 — Uyanık tekrar, mikro-uyku, yerel uyku ✅ kabul

Bu fazdan itibaren yeni modüller **İngilizce** yazılıyor (kullanıcı kararı);
mevcut Türkçe kodun tamamı fazlar bittikten sonra tek geçişte çevrilecek.

| Dosya | Ne |
|---|---|
| `src/dornick/recall/awake.py` | `on_result` (sonuç anında ters tekrar), `forward_replay` (artımlı, idempotent), `micro_sleep`, `local_sleep`, uyku borcu |
| `recall/store.py` | `cold_nodes`, `shrink_edges_between` — küçültmeyi soğuk bölgeyle sınırlayan iki sorgu |
| `recall/orgu.py` | uyanık koşmuş oturumun ters tekrarını gece atlıyor; ileri tekrar artımlı |
| `loop.py` | araç hatasında uyanık ters tekrar tetikleniyor |
| `tests/test_awake.py` | 16 test: aynı oturumda ders, çift sayım yok, idempotentlik, mikro-uyku küçültmüyor, yerel uyku aktif bölgeye dokunmuyor |

**Değişmez, kodda:** küçültme yalnız öğrenmenin olmadığı yerde koşar. Gece
uykusu bütün ağı küçültür; yerel uyku **yalnız** iki ucu da bir haftadır
dokunulmamış kenarları; mikro-uyku hiç küçültmez. Bu, "bir mekanik neden
uykuya bağlı" sorusunun tek gerçek cevabı ve `shrink_edges_between` onu
SQL'de zorluyor, yorumda değil.

### Ölçüm — `docs/charts/yasam-f312.md`

| Kriter | Faz 3 | Faz 3.12 | Ablation | Kabul | |
|---|---|---|---|---|---|
| `ders_gecikmesi` (tur) | 59.8 | **1.0** | 50.0 | ≤ 1 | ✅ |
| `tur_bloklama` p95 | yok | **9.2 ms** | 0.01 | ≤ 50 ms | ✅ |
| `aktif_bolge_ihlali` | yok | **0** | — | 0 | ✅ |
| `uykusuz_kayip` | yok | **1.143** | — | ≥ 0.80 | ✅ |
| `uykusuz_sisme` | yok | **0.379** | — | ≤ 1.30 | ✅ |
| `sorumluluk_dogrulugu` | 1.000 | **0.875** | 1.000 | ≥ 0.85 | ✅ |
| `prime_precision` | 0.2781 | **0.2781** | 0.2781 | düşmez | ✅ |
| `gomulme_recall` / `geri_donus_recall` | 1.00 | **1.00** | — | — | ✅ |

Ablation (uyanık ters tekrar kapalı): `ders_gecikmesi` 1.0 → **50.0**, yani
"geceye kadar". Mekanik tam olarak vaat ettiği işi yapıyor.

`scale_bench`: precision 0.64, tok/query 71.3 — gerileme yok.

### Beklenmeyen bulgu: uykusuz makine şişmiyor, **kuruyor**

Yol haritası uykusuz kolun kenar sayısının artmasını bekliyordu
(`uykusuz_sisme` ≤ 1.3, yani "şişme sınırlı kalsın"). Ölçüm tersini söyledi:
**0.379** — uykusuz kolda kenar sayısı uyuyanın üçte biri. Sebep basit ve
tasarımın kendisinde: bu üründe kenarların çoğunu **gece üretiyor** (yeniden
örgü + dikiş + zaman komşuluğu), gündüz değil. Küçültme olmayınca ağ
şişmiyor, çünkü şişirecek kadar kenar hiç yazılmıyor.

Yani "uykusuzluk ağı şişirir" hipotezi bu mimaride yanlış; uykusuzluğun
maliyeti şişme değil **yoksunluk**. Hedef sağlandı ama beklenen mekanizmayla
değil, ve bu fark rapora yazıldı.

---

## Faz 3 (Adım 6) — Damıtma ⚠️ kabul edilmedi (1 kriter) — ama beklenmedik kazanç

| Dosya | Ne |
|---|---|
| `src/dornick/recall/distil.py` | kümeleme, damıtma, çelişki kaydı, kenar gerekçesi, **sınav kapısı** |
| `recall/orgu.py` | Adım 6 gece geçişine bağlandı; `sinav` geri çağrısı ile geri alma |
| `recall/store.py` | `kenar_guncelle` — kenarı zayıflatabilen tek yol (damıtmanın "ilişkisiz" kararı) |
| `tests/test_distil.py` | 17 test: gizlilik kapısı, kaynaklı yazım, çelişki, sınav geri alma |

**Gizlilik kapısı koddadır, talimatta değil.** Model yoksa adım atlanıyor ve
raporda o kelimelerle yazıyor. Barındırılan model + onay kapalıysa **tek bir
istem bile çıkmıyor** (test bunu modelin çağrılmadığını sayarak doğruluyor).
İlk beş adım her hâlükârda koşuyor: modelsiz makine özet kaybeder,
konsolidasyon kaybetmez.

**Sınav kapısı yalnız tahmini geri alıyor.** Tekrar, sorumluluk ve şema
dokunuşları yaşananın kaydı; kötü bir özet günü yaşanmamış yapmaz. Test bunu
ayrıca zorluyor: geri alma sonrası sicil ve zaman komşuluğu kenarı yerinde.

### Ölçüm — damıtma açık / kapalı

| Metrik | Damıtma kapalı | Damıtma açık | Kabul | |
|---|---|---|---|---|
| `prime_precision` | 0.2781 | **0.4564** | düşmez | ✅ **+%64** |
| `prime_recall` | 0.99 | 0.89 | — | ⚠️ −0.10 |
| `yasak_sizinti` | 29 | **26** | — | ✅ |
| `prime_token` | 83.37 | **91.43** | ≤ 0.85 × taban | ❌ +%10 |
| `tuzak_sessizlik` | 0.45 | 0.45 | düşmez | ✅ |
| `ders_gecikmesi` | 1.0 | 1.0 | ≤ 1 | ✅ |
| `gece_suresi` | 0.066 sn | 0.112 sn | ≤ 300 sn | ✅ |

`scale_bench`: precision 0.63, tok/query 71.8 — gerileme yok.

### Geçmeyen kriter: `prime_token` — Faz 0'da öngörülmüştü

Yol haritası "`prime_token` ≥ %15 azalma (episode yerine damıtık fact
giriyor)" diyor. Bu üründe **episode zaten prime'a girmiyor** (`select_prime`
onları açıkça eliyor), dolayısıyla damıtığın yerini alacağı bir şey yok:
damıtma korpusa kayıt EKLİYOR, çıkarmıyor. Token ancak artabilirdi ve %10
arttı. Bu, Faz 0 defterine yazılan öngörünün ölçülmüş hâli.

Buna karşılık ölçüm, kriterin sormadığı bir yerde büyük bir kazanç gösterdi:
**precision 0.278 → 0.456**. Sebebi mekanizmanın kendisi — kısa, konuya
özgü damıtık `fact`lar önyükleme yuvalarına girip gürültüyü dışarı itiyor.
Faz 3'te "tohum doygunluğu" diye adlandırılan duvara ilk gerçek darbe bu.
Bedeli recall'da 0.10: damıtık kayıt bazen beklenen kaydın yerini alıyor.

**Ölçüm dürüstlüğü:** bench'in damıtma kolu gerçek bir model kullanmıyor.
Kümedeki en uzun gövdelerin ilk cümlesini kaynak kimliğiyle geri veren,
tamamen deterministik bir çıkarımcı. Ölçtüğü şey damıtmanın **mekaniği** —
kısa bir `fact`ın önyüklemeye girmesi — modelin özet kalitesi değil. Gerçek
model kalitesi ayrı bir deneyin konusu; bu bench onu ölçemez ve ölçtüğünü
iddia etmiyor.

**Yan bulgu:** damıtma açıkken `sema_tazeleme` +0.376'dan −0.105'e düşüyor.
Yeni damıtık kayıtlar `_weave` komşuluklarını değiştiriyor ve N kümesinin
kontrol kolu artık deney koluyla kıyaslanabilir olmaktan çıkıyor. Metrik
bozuluyor, mekanik değil — ama bu, damıtma açıkken N ölçümüne
güvenilemeyeceği anlamına geliyor.

---

## Faz 3.10 — Uyku dinamiği ✅ kabul (7/7)

| Dosya | Ne |
|---|---|
| `src/dornick/recall/sleep.py` | basınç (S), ritim histogramı + zeitgeber'lar, dört durumlu anahtar (histerezis + oreksin + kafein), döngüler, kesilme, bakım işleri |
| `recall/store.py` | `strengthening`, `checkpoint`, `optimize_fts`, `vacuum` |
| `tests/test_sleep.py` | 23 test: eşiğin kaynağı, basınç, narkolepsi, uyarılma tablosu, ritim, jet lag, kesilme, bakım kapısı |

**Eşikler seçilmedi, türetildi.** `ESIK_UST = 2.3374`, `ESIK_ALT = 0.7791` —
gece kapalıyken ölçülen bozulma eğrisinden (`--threshold-curve`, 2026-09-02).
Bir test sabitin kaynağının yorumda yazılı olduğunu da zorluyor: kaynağı
kaybolan bir sabit sihirli sayıya döner.

**Narkolepsi testi tasarımın kendisini ölçüyor.** Basınç iki saat boyunca
eşiğin ±%5 bandında geziniyor, kullanıcı yok: geçiş sayısı ≤ 2. Tek eşikli
bir denetleyicide bu sayı onlarca olurdu ve kullanıcı bunu "hiç oturamayan
makine" olarak yaşardı.

**Oreksin koşulsuz.** Kullanıcı etkindeyken hiçbir uyku türü koşmuyor —
mikro-uyku dahil. Test yirmi örneklem boyunca bunu zorluyor.

**Derin döngüler modeli hiç çağırmıyor.** Erken uyanma yarım bir tahmin
bırakamaz, çünkü tahmin henüz başlamamıştır. Damıtma yalnız REM'de.

### Ölçüm — `docs/charts/yasam-f310.md`

| Kriter | Değer | Kabul | |
|---|---|---|---|
| `kesinti_kaybi` | **0** | 0 | ✅ |
| `yarim_damitma` | **0** | 0 | ✅ |
| `kesinti_gecikmesi` p95 | **5.08 ms** | ≤ 500 ms | ✅ |
| `ritim_isabeti` | **1.00** | ≥ 0.90 | ✅ |
| `atalet` | **0** | 0 | ✅ |
| narkolepsi (2 saat, eşik bandı) | **≤ 2 geçiş** | ≤ 2 | ✅ |
| `esik_egrisi` commit'li, sabitler ondan | evet | — | ✅ |

Kesilen gecelerin (%30 / %60 / %90) devreden işi ertesi gece **tamamen**
tamamlandı; kayıp sıfır.

**Not:** yol haritasının test matrisi `test_zeitgeber.py` ve
`test_temizlik.py`'yi ayrı dosyalar olarak istiyor; ikisinin de kapsamı
`test_sleep.py` içinde (zeitgeber: saat dilimi kayması + güven düşüşü;
temizlik: VACUUM uyanıkken reddediliyor, checkpoint sonrası WAL < 1 MB).
Ayrı dosyaya bölmek kapsamı değiştirmiyor, yalnız dosya sayısını.

---

## Faz 3.11 — Sıcak/soğuk indeks ⚠️ kabul edilmedi (1 kriter) — bütçe tutuyor

| Dosya | Ne |
|---|---|
| `recall/store.py` | `sicak` sütunu, `isi_guncelle`, `sicak_oran`; imza indeksi yalnız sıcakları yüklüyor |
| `recall/orgu.py` | gece sonunda aktif küme yeniden hesaplanıyor |
| `recall/vector.py` | `Index.ids()` |
| `loop.py` | soğuk kayıt önyüklemeye giremiyor (genç-hafıza istisnası dahil) |
| `mind/tools.py` | `mind_recall` çıktısında `(soğuk)` işareti |
| `tests/test_hot_cold.py` | 13 test: kim soğur, soğuk ne kaybeder, ısınma, damıtılmış episode, oran, göç |

Cevap arşivi küçültmek değil. Hiçbir şey silinmiyor, mezar taşı almıyor,
`series`'ten düşmüyor. Değişen tek şey **erişilebilirlik**: sıcak düğüm imza
indeksinde, kendiliğinden gelebilir; soğuk düğüm yalnız FTS'te, yani birebir
kelimeyle — bir ipucuyla — uyanır ama çağrılmadan gelmez. Açılınca ertesi
gece ısınır.

### Kalibrasyon — `SOGUK_ESIK = -5.0`

Hedef yol haritasında sayı değil **oran**: doksan günlük senaryoda sıcak oran
%10-30. Tarama (2026-09-03):

| `SOGUK_ESIK` | sıcak oran | precision | recall | tuzak sessizliği |
|---|---|---|---|---|
| −2.0 | %2.9 | 0.343 | 0.23 | 0.80 |
| −3.0 | %4.5 | 0.333 | 0.25 | 0.80 |
| −4.0 | %6.5 | 0.444 | 0.52 | 0.725 |
| **−5.0** | **%25.2** | 0.429 | 0.75 | 0.525 |
| −6.0 | %69 | 0.444 | 0.88 | 0.45 |
| −7.0 | %98.5 | 0.459 | 0.90 | 0.45 |

Banda düşen tek değer −5.0.

### Ölçüm — `docs/charts/yasam-f311.md`

| Kriter | Faz 3.10 | Faz 3.11 | Kabul | |
|---|---|---|---|---|
| `sicak_oran` | 1.00 | **0.238** | 0.10–0.30 | ✅ |
| `buyume_ram` | 10.0 | **1.00** | ≤ 2 | ✅ |
| `buyume_p95` | 6.78 | **6.10** | ≤ 1.5 | ❌ |
| `gomulme_recall` | 1.00 | **1.00** | ≥ 0.90 | ✅ |
| `sema_tazeleme` | −0.060 | **0.521** | > 0 | ✅ |
| `yakalama` | −0.098 | −0.098 | > 0 | ❌ (Faz 3'teki sebep) |
| `prime_token` | 91.48 | **76.34** | ≤ 0.85×taban (71.5) | ⚠️ −%9 |
| `tuzak_sessizlik` | 0.45 | **0.525** | düşmez | ✅ |
| `yasak_sizinti` | 27 | **19** | — | ✅ |
| `prime_recall` | 0.90 | 0.76 | — | ⚠️ mekaniğin sonucu |

**Mutlak sayılar hedefi tutuyor, oran tutmuyor.** 200k düğümlük bellekte:

| | önce | sonra |
|---|---|---|
| imza indeksi | 200.000 kayıt | **2.000** |
| imza RAM | 14,4 MB | **0,14 MB** |
| `recall()` p95 | 33,2 ms | **18,4 ms** (bütçe 20) |

Yani kullanıcıya verilen söz — 200k'da 20 ms altında kalmak — **tutuyor**;
tutmayan şey 20k'ya oranı (6.1, hedef 1.5). Kalan ölçeklenme imza tarafından
değil FTS tarafından geliyor: indeks iki hafızada da aynı boyutta, ama FTS
200k satırın hepsini kapsıyor ve dolgu metni yalnızca ~900 farklı cümlenin
tekrarı olduğu için her sorgu binlerce belgeyle eşleşiyor. Gerçek bir arşivde
kayıtlar birbirinden farklıdır; bu dolgu FTS için en kötü hâli temsil ediyor.
Sayı olduğu gibi bırakıldı — dolguyu "daha kolay" yapmak ölçümü değil, ölçüm
hakkındaki hikâyeyi düzeltmek olurdu.

**Yan etki, mekaniğin amacının doğrudan sonucu:** `prime_recall` 0.90 → 0.76.
Soğuyan bir kayıt artık kendiliğinden önyüklemeye giremiyor. Aynı sebeple
tuzak sessizliği 0.45 → 0.525'e, yasak sızıntısı 27 → 19'a, `prime_token`
91.5 → 76.3'e iyileşti. Bu takas tasarımın kendisi: az ve doğru enjeksiyon.

---

## Faz 4 — Kodlama gücü ⚠️ faydası kanıtlanmadı

| Dosya | Ne |
|---|---|
| `recall/aktivasyon.py` | `kodlama_gucu(surpriz, kind, supersedes)` |
| `recall/store.py` | `remember` yazımdan ÖNCE sürprizi ölçüyor, ilk kullanım girdisinin ağırlığı o oluyor |
| `tests/test_encoding.py` | 11 test: taban, ders çarpanı, düzeltme tam güç, tekrar zayıflıyor, anahtar |

Şema değişmedi: `taban_aktivasyon` zaten ağırlıklı toplam alıyor, değişen
yalnız ilk girdinin `w`si. Taban 0.4 — **hiçbir kayıt erişilemez doğmuyor**;
bilinen bir şeyi tekrar duymak da bilgidir, yalnız haber değildir.
Düzeltme her zaman tam güç: bir düzeltme düzelttiği şeye benzer, zaten bu
yüzden düzeltmedir.

### Ölçüm — ablation (tek başına)

| Metrik | Kodlama açık | Kapalı | Fark |
|---|---|---|---|
| `prime_precision` | 0.4010 | 0.4044 | −%0.8 |
| `prime_recall` | **0.77** | 0.74 | **+%4.1** |
| `tuzak_sessizlik` | 0.500 | **0.525** | **−%4.8** |
| `yasak_sizinti` | 18 | 18 | 0 |
| `prime_token` | **75.44** | 77.40 | −%2.5 |

Kabul kriteri "C kümesi `yasak_sizinti` düşer veya sabit" ✅ (18 → 18),
"A kümesi recall düşmez" ✅. Ama asıl kural şu: *"Ablation ile tek başına
ölçülür; fayda < %3 ise faz geri alınır."*

**Sonuç bir berabere.** Mekanik iki metriği %3'ün üzerinde oynatıyor ama
**zıt yönlerde**: recall +%4.1 iyi, tuzak sessizliği −%4.8 kötü. Net bir
fayda göstermiyor.

Faz geri alınmadı, üç sebeple ve hepsi yazılı olsun diye:

1. Yol haritasının kendisi bu fazın Faz 7'ye **erimesini** öngörüyor
   (`guc = 0.4 + 0.6 * |odul|`); tek bileşenli hâli ölçülmeden çok
   bileşenlinin neyi eklediği bilinemez — ki bu fazın var olma gerekçesi de
   buydu.
2. Ölçülen zayıflığın kaynağı mekanik değil, dayandığı **vekil**. Faz 3'te
   ilan edilmişti ve burada tekrar ölçüldü: `_seed` birebir kopyayı bile
   ~0.77 puanlıyor, yani sürpriz hiç sıfıra inmiyor. Beşinci kopya birincinin
   %55-66'sı ağırlığında doğuyor; yol haritasının çıtası %50 idi.
   Dahası komşunun skoru kendi aktivasyonuyla söndüğü için **eski bir kopyanın
   tekrarı daha "sürprizli" görünüyor** — vekil hem doyuyor hem kayıyor.
3. Mekanik gerçek bir özelliği veriyor (tekrar zayıf doğuyor, ders ağır
   basıyor, düzeltme tam güç) ve bunlar Faz 7'nin gireceği yuvalar.

**Karar Faz 7 sonrasına bırakıldı**: ödül sinyali sürprizin yerini aldığında
bu ablation yeniden koşulacak. O koşuda da fayda çıkmazsa faz kaldırılmalı.

---

## Faz 5 — Bağlam bonusu ⚠️ kabul edilmedi (1 kriter) — sızıntı sıfırlandı

| Dosya | Ne |
|---|---|
| `recall/store.py` | `baglam` sütunu, `_baglam_bonusu` (bonus + **çatışma cezası**), `_seed(..., baglam=)` |
| `mind/store.py` | `Mind.set_baglam` / `baglam()`; yazım anında damgalanıyor; açık arama süzülmüyor |
| `loop.py` | `select_prime(..., baglam=)` |
| `tests/test_context.py` | 12 test: alan, bonus, çatışma, boş bağlam, açık arama, göç, bozuk veri |

`session` alanı vardı ve arama onu hiç okumuyordu. Sızıntı bugüne kadar iki
sonradan takma süzgeçle bastırılıyordu: sorgudan sayı silmek ve zengin
sorguda tek gövdeyle tutunan kaydı elemek. İkisi de gerçek süzgeç ama
ikisi de o hatıraları asıl ayıran şeyle ilgili değil.

**Bonus tek başına yetmedi ve sebebi ölçüldü.** `BAGLAM_BONUS`u 0.15'ten
3.0'a çıkarmak E kümesi sızıntısını 18'den hiç indirmedi: `select_prime`
beş yuvayı doldurmaya çalışıyor, doğruyu yukarı itmek yanlışı dışarı atmıyor
— Faz 2'de bulunan aynı yapısal duvar. Bu yüzden **çatışma cezası** eklendi:
aynı alanda BAŞKA bir değer taşıyan kayıt (koru1000 oturumundayken kobyte'ın
raporu) payını kaybediyor. Boş bağlam hâlâ nötr; çatışma cezası bir tabanla
sınırlı (`BAGLAM_TABAN = 0.15`) ve **açık arama hiç süzülmüyor** — "kobyte'ta
ne yapmıştık" koru1000 oturumundayken de cevaplanabilmeli.

### Kalibrasyon

| `BAGLAM_CEZA` | E precision | E sızıntı | genel precision | toplam yasak sızıntı |
|---|---|---|---|---|
| 0.0 (yalnız bonus) | 0.317 | 18 | 0.393 | 19 |
| 0.7 | 0.415 | 1 | 0.434 | 2 |
| **1.0** | **0.400** | **0** | **0.433** | **1** |

### Ölçüm — `docs/charts/yasam-f5.md`

| Kriter | Faz 3.11 | Faz 5 | Kabul | |
|---|---|---|---|---|
| E kümesi precision | 0.202 | **0.395** | ≥ 0.85 | ❌ |
| E kümesi yasak sızıntı | 19 | **0** | — | ✅ |
| `yasak_sizinti` (toplam) | 19 | **1** | 0 | ✅ neredeyse |
| `prime_precision` | 0.420 | **0.44** | — | ✅ |
| küme precision: D / H / J | 0.40 / 0.46 / 0.43 | **0.67 / 0.63 / 0.75** | — | ✅ |

`scale_bench` (eski tabana karşı): recall 0.78 → **0.83**, coverage
0.76 → **0.81**, precision 0.63 → **0.65**, tok/query 71.8 → **70.7**.

### İkinci kabul kriteri: hileler sadeleştirilemedi

Yol haritası "bonus açıkken `_without_numbers` ve zengin-sorgu ≥2-gövde
kuralı kapatılıp bench koşulur; sonuç eşit ya da daha iyiyse o hileler
sadeleştirilir" diyor. Ölçüldü ve **desteklenmedi**:

| Kol | precision | tuzak sessizliği | prime_token | E precision |
|---|---|---|---|---|
| ikisi de açık | **0.441** | **0.500** | **74.8** | **0.415** |
| sayı-silme kapalı | 0.433 | 0.500 | 74.6 | 0.400 |
| zengin-sorgu kuralı kapalı | 0.405 | 0.325 | 83.3 | 0.386 |
| ikisi de kapalı | 0.407 | 0.325 | 83.4 | 0.395 |

Zengin-sorgu kuralını kaldırmak tuzak sessizliğini üçte bir düşürüyor ve
token'ı %11 artırıyor. **Kod borcu bu fazda ödenemedi**; ikisi de hâlâ
gerçek iş yapıyor ve yerinde kaldı.

---

## Faz 7 — Ödül, mizaç, üç özne, karakter ✅ mekanikler kuruldu

| Dosya | Ne |
|---|---|
| `recall/reward.py` | tek skaler ödül: sonuç tahmin hatası + bilgi kazancı + sosyal (tavanlı) |
| `recall/temperament.py` | beş eksen; taban ölçülür, hedef öğrenilir, kaldıraç harness parametrelerine biner |
| `recall/subjects.py` | üç özne: `user` (söylenen), `world` (gözlenen, kaynaklı, bozunan), `self` (sonuçlardan, sıfatsız) |
| `recall/curiosity.py` | öğrenme ilerlemesi × alaka, entropi tabanı, web kapalı |
| `recall/identity.py` | kanıtlı cümle, gecede bir değişim, sıfat yasağı, kullanıcı itirazı |
| `tests/test_character.py` | 41 test |

**Bir iddia yerine bir sayım.** Bu fazın tamamı tek bir ayrımın üstüne
kurulu: sistemin bir karakteri olabilir, karakterini **ilan etmesi**
olamaz. Her mekanik iddiayı sayıma çeviriyor.

* **Ödül bir tahmin hatası.** Yirmi kez geçmiş bir testin yine geçmesi
  neredeyse hiçbir şey öğretmiyor (ölçüldü: 0.05); dokuz kez kırılmış bir
  yordamın geçmesi çok şey öğretiyor (0.85).
* **Sosyal tavan sabit, mizaç ekseni değil.** Yalakalık, ödülü kısa yoldan
  üretme politikasıdır; `sosyal ≤ 0.3` mutlak ve düzeltme (−1.0) her zaman
  teşekkürden ağır basıyor. Test: `sosyal=1.0` mizaçlı bir modelde bile
  yirmi teşekkür tavanı aşamıyor.
* **`self` kodda korunuyor, promptta değil.** `mind_memory save kind=self`
  reddediliyor (`SelfWriteRefused`); sicil yalnız sonuç olaylarından
  türetiliyor ve `model_id` taşıyor — model değişince eski sicil ruha
  girmiyor. "Dikkatliyim" reddediliyor, "41 görevin 33'ünde önce test
  yazdım" kabul ediliyor; kural kendi çıktımıza da uygulanıyor (`SelfRecord.
  line()` "başarılı" diyemiyor, çünkü o da yasak listede).
* **Model değişimi bir beyin nakli.** Taban yeniden ölçülüyor, **hedef
  kalıyor**, kaldıraç yeniden hesaplanıyor. Test: çekingen modelden atak
  modele geçince kaldıraç yön değiştiriyor, hedef kıpırdamıyor.
* **Merak kullanıcının dünyasından çıkmıyor.** Alaka sıfırsa bütçe sıfır;
  entropi tabanı tek alana çökmeyi engelliyor; web kapalı ve izin verilen
  eylemlerin hiçbiri dosya İÇERİĞİ okumuyor — meraklı bir ajan sızıntı yolu
  olmamalı.
* **Kimlik belgesi kanıtsız cümle kabul etmiyor**, gecede bir cümle
  değiştiriyor, sıfat yasaklı, ve talimat ("hep katıl") belgeye giremiyor:
  düzeltme evet, itaat hayır. Bellek sıfırlanınca anlatı gidiyor, mizaç
  kalıyor.

Kapsam: `curiosity` %100, `temperament` %100, `subjects` %96, `reward` %94,
`identity` %92.

**Ölçülemeyen kısım, açıkça:** `tutarlilik_baglam` / `tutarlilik_zaman` /
`tutarlilik_model` ve `sosyal_ulasilan` gerçek model çağrıları gerektiriyor
(30 kararlık set × iki model × üç tekrar). Bu koşu bir API bütçesi ve iki
farklı modelin kurulu olmasını istiyor; mekanikler ve kapıları burada
kuruldu ve testlendi, **karakter tutarlılığı sayıları ölçülmedi**. Bu
satır, sayı gelene kadar bir eksiklik olarak durmalı.

---

## Faz 6 — Beyin görünümü ⚠️ veri katmanı kuruldu, görsel katman yapılmadı

| Dosya | Ne |
|---|---|
| `recall/night_events.py` | **dondurulmuş** olay sözlüğü, yazıcı, doğrulayıcı, yeniden oynatma, sabah özeti |
| `recall/sleep.py` | `Sleeper` olayları o şemadan geçiriyor; günlük `.dornick/gece/<tarih>.jsonl` |
| `web/server.py` | `GET /api/uyku`, `GET /api/gece`, `GET /api/gece/<tarih>` |
| `tests/test_night_events.py` | 13 test: şema anlık görüntüsü, eksik/fazla alan, yeniden oynatma, kesilmiş günlük, yol kaçışı |

**Şema bilerek donduruldu.** `SCHEMA` bir anlık görüntü ve testi onu birebir
karşılaştırıyor: bir alanın adı değişirse test kırmızıya döner. İstenen tam
olarak bu — sessizce duran bir animasyon yerine gürültüyle kırılan bir test.
Fazla alan da reddediliyor: arayüzün güvenebileceği tek şey sözlüğün
söylediği, yanına sızmış bir alan yük taşıyamamalı.

**Arayüz `recall.db`'ye bakmıyor.** Gece yazarken okuyan bir arayüz yarı
konsolide bir grafiği doğruymuş gibi gösterirdi. Canlı izleme ve yeniden
oynatma **aynı kod yolu**: diskteki dosya olay günlüğünün kendisi, oynatmak
onu sırayla okumak. Ayrışacak ikinci bir yol yok.

Küçük ama gerçek bir güvenlik detayı: `/api/gece/<tarih>` yolundaki tarih
HTTP'den geliyor, yani güvenilmez girdi. `night_path` onu tek klasöre
sabitliyor ve test `../../etc/passwd` ile zorluyor.

### Yapılmayan: görsel katman

Yol haritasının 6.1–6.3'ü (bölge şablonu, canvas animasyonu, gündüz
görünümü) ve 6.5'teki Playwright uçtan uca testleri **yapılmadı**. Sebebi
kapsam değil, doğrulanabilirlik: 50k düğüm ve 5k olayda 60× hızda kare
düşüşünü ölçen bir kabul kriteri ancak gerçek bir tarayıcıda anlamlı, ve
göremediğim bir animasyonu yazmak onu yazmış gibi yapmak olurdu.

Veri katmanı o işi bekletmiyor: şema donmuş, uçlar açık, oynatma testli.
Görsel katman ayrı bir iş olarak durmalı ve bu satır onun eksik olduğunu
söylemek için burada.

---

## Düzeltme — ruhun bileşimi (Faz 3 ve 3.11'in bıraktığı gerileme)

Eskiye karşı ölçümde iki metrik geriliyordu ve ikisi de tasarım değil kusurdu:
`taze_ruh` 1.00 → 0.70, `ruh_token` 325 → 348.

**Kök neden ölçüldü**, tahmin edilmedi. 90. günde ruhun yordam yuvalarının
sekizi de düzenli **kullanılan** yordamlardaydı; B zincirlerinin bu haftaki
düzeltmeleri (test/dağıtım/yedek) dışarıda kalmıştı. Ders yuvalarının altısı
gecenin yazdığı, içinde ham düğüm kimliği taşıyan uzun derslerdi.

**Üç değişiklik:**

1. **Taze düzeltmeye ayrılmış yer.** Aktivasyona göre sıralamak doğru olanı
   yapıyor — düzenli kullanılan bir yordam bir haftalık düzeltmeden gerçekten
   daha canlı. Ama düzeltme sıradan bir hatıra değil, bir **değişiklik**:
   ruhun sistem promptunda durmasının sebebi ajanın eskimiş bir kurala göre
   davranmaması. Son yedi günde yapılmış düzeltmeler yuvaların yarısını
   garantiliyor. Tavan iki yönlü: yer ayırıyor **ve** yerin yarısından
   fazlasını almasını engelliyor — sekiz düzeltmelik bir hafta ruhu bir
   değişiklik listesine çevirmemeli.
2. **Aynı ders ikinci kez öğrenilmiyor, pekişiyor.** Gece her başarısız
   oturum için yeni bir ders yazıyordu; aynı hata beş kez olduğunda beş ayrı
   ders oluyordu. Yol haritasının yordamlar için koyduğu kural ("aynı
   başlıklı varsa supersede değil, kullanım ekle") asıl burada gerekiyormuş.
   Tekillik bir benzerlik eşiğine değil **başlık eşitliğine** bağlandı:
   "aynı ders mi" sorusunun cevabı 0.55 gibi bir sayıya bakmamalı.
3. **Ham düğüm kimliği ders gövdesinden çıktı.** Kimlik zaten kenarda
   duruyor ("bu hatıra hataya götürdü") ve `mind_recall` kenar gerekçelerini
   gösteriyor. Modele bilgi vermeyen, yalnız her oturumun bedelini artıran
   bir dizgiydi.

| Metrik | eski | düzeltmeden önce | sonra | |
|---|---|---|---|---|
| `taze_ruh` | 1.00 | 0.70 | **1.00** | ✅ geri geldi |
| `ruh_token` | 325.0 | 348.3 | **309.9** | ✅ tabanın altında |
| `prime_precision` | 0.255 | 0.444 | **0.447** | ✅ |
| `prime_token` | 84.07 | 74.08 | **74.74** | ✅ |
| `sorumluluk_dogrulugu` | 0.50 | 0.875 | **0.875** | ✅ |

`tests/test_soul_freshness.py` (7 test) bu üçünü de zorluyor. 2001 test
geçiyor; `scale_bench` gerilemedi (precision 0.65, tok 70.7).

Geriye kalan tek gerileme `prime_recall` 0.96 → 0.76 ve o **tasarımın
sonucu**: soğuyan ve bağlamı çatışan kayıt artık kendiliğinden enjekte
edilmiyor. Aynı değişiklik sızıntıyı 59'dan 1'e, token'ı %11 aşağı indirdi;
açık aramada hepsi bulunuyor (`gomulme_recall` ve `geri_donus_recall` 1.00).

---

## Toplu durum

| Faz | Durum |
|---|---|
| 0 — Ölçüm altyapısı | ✅ tamam |
| 1 — Zaman bazlı aktivasyon | ⚠️ 5 kriterden 4'ü |
| 2 — Supersede | ✅ 3 kriterden 2'si tam, 3.'sü ölçüldü |
| 3 (1-5) — Gece tekrarı | ⚠️ komşuluk/dikiş ≈ sıfır; gece artık üründe de koşuyor (daemon) |
| 3.12 — Uyanık tekrar | ✅ 8/8 |
| 3 (6) — Damıtma | ⚠️ token hedefi tutmadı, precision +%64 |
| 3.10 — Uyku dinamiği | ✅ 7/7 |
| 3.11 — Sıcak/soğuk | ✅ %23 (band), komşuluk ısısı ile |
| 4 — Kodlama gücü | ⚠️ faydası kanıtlanmadı |
| 5 — Bağlam bonusu | ✅ E sızıntısı 0, ceza sorgunun alan sayısına göre |
| 7 — Ödül, mizaç, karakter | ⚠️ mekanik + prompt bağlantısı + ölçüm düzeneği hazır; gerçek modelle ölçülmedi |
| 6 — Beyin görünümü | ✅ bölgeler, gece animasyonu, paneller; Playwright e2e Chromium bekliyor |

### Eskiye göre (yaşam bench, `hafiza-eski` → bugün) · 2026-09-04 düzeltmesi

> Bu tablonun eski sürümü ölçüm aletindeki bir sızıntıyla üretilmişti:
> `mind/search.py` gerçek takvim gününü okuyordu, kimlikler rastgeleydi,
> tohum sabitlenmemişti. Alet onarıldı (bkz. "Determinizm" bölümü); iki
> sayı gerçekte olduğundan iyi görünüyormuş. Aşağısı iki ayrı süreçte birebir
> tekrarlanabilen dürüst hâl.

| Metrik | eski | yeni | not |
|---|---|---|---|
| `ders_gecikmesi` | 79.4 tur | **1 tur** | ✅ |
| `sorumluluk_dogrulugu` | 0.50 | **1.00** | ✅ |
| `yasak_sizinti` | 59 | **6** | −%90, hedef 0 değil |
| `bayat_ruh` | 3.48 | **0** | ✅ |
| `prime_token` | 84.5 | **78.4** | ✅ |
| `ruh_token` | 325.0 | **310.8** | ✅ |
| `sema_tazeleme` | yok | **0.68** | ✅ |
| `taze_ruh` | 1.00 | **1.00** | ✅ |
| `prime_precision` | 0.255 | 0.274 | önceki rapor 0.447 diyordu — sızıntı |
| `sicak_oran` | 1.00 | 0.77 | önceki rapor 0.22 diyordu — sızıntı; hedef %10–30 tutmuyor |
| `prime_recall` | 0.96 | 0.88 ⚠️ | tasarım (soğuk/çatışan enjekte edilmiyor) |
| `tuzak_sessizlik` | 0.45 | 0.475 | neredeyse yerinde |
| `gecikme_p95` | 8.43 ms | **5.21 ms** | ✅ |

`scale_bench` (tek tur) gerilemedi.

**Açık kalan tek büyük duvar** üç fazda aynı sayıyla göründü ve adı
**tohum doygunluğu**: ortak tek bir kelimeyi paylaşan yirmi kayıt 0.5 üstü
skor alıyor. `komsuluk_recall` ve `dikis_recall`'ı sıfırda tutan,
`prime_precision`'ı 0.85 hedefinin altında bırakan, kodlama gücünün
sürprizini doyuran şey bu. Yol haritasında adı geçen ama hiçbir fazın
kapsamına girmeyen tek çare `vector.py` için opsiyonel IDF ağırlığı.
## Faz 7 — Ödül, mizaç, üç özne, karakter · bekliyor

---

## Holdout — kalibrasyon ana sete mi uydu? · 2026-09-03

Bütün sabitler (`BOZUNMA`, `OLCEK`, `CELISKI_ESIK`, `BASARI_PAYI`,
`SOGUK_ESIK`, `BAGLAM_CEZA`, `ESIK_UST/ALT`) ana veri setine bakılarak
seçildi. Bu, sonuçların o setin şekline uydurulmuş olma ihtimalini doğurur ve
tek panzehiri hiç bakılmamış bir sette ölçmek. `yasam_holdout.json` Faz 0'da
üretilip bir kez bile koşulmamıştı — bu bir eksiklikti, kapatıldı.

Holdout 30 günlük, 43 düğümlük, 34 soruluk ayrı bir senaryo; gece olayı
içermediği için yalnız **gündüz yolunu** ölçer (aktivasyon, supersede,
bağlam, sıcak/soğuk, ruh). H–S kümelerinin metrikleri bu sette "yok".

| Metrik | eski (holdout) | yeni (holdout) | ana sette yeni |
|---|---|---|---|
| `prime_precision` | 0.3846 | **0.4750** | 0.447 |
| `prime_recall` | 1.00 | 0.95 | 0.76 |
| `yasak_sizinti` | 12 | **5** | 1 |
| `tuzak_sessizlik` | 0.75 | 0.75 | 0.50 |
| `bayat_ruh` | 1.63 | **0** | 0 |
| `taze_ruh` | 1.00 | **1.00** | 1.00 |
| `ruh_token` | 130.0 | **113.8** | 309.9 |
| `prime_token` | 56.3 | **50.4** | 74.7 |
| `sicak_oran` | 1.00 | **0.884** | 0.22 |

**Sonuç:** kalibrasyon ana sete uymamış. Hiç görülmemiş bir sette de yön
aynı — precision yukarı, sızıntı ve token aşağı, bayat ruh sıfır. İki
sayı ana setten daha iyi çıkıyor (`prime_recall` 0.95, `tuzak_sessizlik`
0.75); sebebi holdout'un küçüklüğü: 43 düğümde soğuma da bağlam çatışması
da az, yani ana setteki `prime_recall` düşüşünün gerçekten o iki
mekanizmadan geldiğini doğruluyor.

**Yan bulgu — kırık ölçüm aleti.** `--old` kolu Faz 5'ten beri
çalışmıyordu: bench `Mind.remember(..., baglam=)` çağırıyor, `hafiza-eski`
o parametreyi bilmiyor, koşu `TypeError` ile ölüyordu. Faz 5'ten sonraki
"eskiye göre" satırlarının hepsi donmuş `yasam-taban.json`'dan okunmuştu —
sayılar doğru ama alet bozuktu ve bunu ancak holdout'u koşmaya çalışınca
gördük. `yaz()` artık `TypeError`'da bağlamı düşürüp devam ediyor
(`loop.select_prime`'daki aynı desen). İkinci kusur: "eski" sütunu hangi
veri setinde olursa olsun ana setin tabanını gösteriyordu — holdout
koşusunda iki farklı senaryoyu aynı satırda karşılaştırmak olurdu. Taban
etiketi artık veri setine bağlı (`yasam-holdout-taban`).

---

## Determinizm — bench'i gerçekten tekrarlanabilir yap · 2026-09-04

Yol haritası "aynı veri, aynı takvim, aynı sonuç" diyor. Bu iddia süreç
İÇİNDE tutuyordu (iki `bench.run()` aynı sonucu veriyordu) ama süreçler
ARASINDA tutmuyordu — ve sabitlenmiş çizelgeler bugün hiçbir sürümle yeniden
üretilemiyordu. Üç sızıntı vardı:

1. **Gerçek saat sızıntısı.** `mind/search.py._freshness`, geçmiş oturumları
   sıralarken `datetime.now()` çağırıyordu. Saat denetim testi yalnız
   `store.py` ile `mind/store.py`'yi gözlüyordu, `search.py`'yi değil — bu
   yüzden bir yıl boyunca görünmedi. Ölçüm hangi GÜN koşulduğuna bağlıydı;
   `sicak_oran` ve `prime_precision` bundan besleniyordu. Saat artık enjekte
   ediliyor; denetim tüm recall+mind yüzeyine genişletildi ve "enjekte
   edilebilir varsayılan" kalıbına (`now or datetime.now()`) izin veriyor.
2. **Rastgele kimlik sızıntısı.** Düğüm kimlikleri `n_<rastgele>`; eşit skorlu
   iki kayıt arasındaki küme sıralaması bu kimliklere bağlıydı, süreçten
   sürece değişiyordu. Bench artık deterministik (sayaç) kimlik enjekte
   ediyor — üründe sıfır değişiklik, kimliklerin rastgeleliği ürüne zaten
   fark etmiyor.
3. **Bütçe ve tohum.** Gerçek saniye bütçeleri nötrlendi (sanal takvimde
   makine hızı içeriğe karışmasın) ve `PYTHONHASHSEED` sabitlendi.

Yeni test `test_two_processes_give_the_same_result` iki AYRI süreci koşup
her içerik metriğinin birebir eştiğini zorluyor. `--old` kolunun kırık prime
fallback'i (`select_prime(raw=)` eski üründe yok) katmanlı hale getirildi.

**Kazanılan ders:** ölçüm aleti de üründür ve onun da regresyon testi olmalı.
Sızıntı, iyi görünen iki sayıyı üretiyordu; onarım onları düşürdü ama
gerçek kıldı.


---

## Tohum doygunluğu ve sıcak küme — IDF, taban, komşuluk ısısı · 2026-09-04

Üç fazın takıldığı duvarın adı **tohum doygunluğu**ydu; sonda onu tam
yerinde gösterdi. İmza kanalı değil, **harfi harfine kanalın skorlaması**:
bm25 büyüklüğü `x/(1+x)` ile ezildiği için tek yaygın kelimeyle ("eski",
"hangi", "yapılıyor", "kodu") eşleşen kayıt 0.45, dört nadir kelimeyle
eşleşen beklenen kayıt 0.50 alıyordu. Her soru beş yakın-eşiti prime'a
sürüklüyor, isabet 0.27'de kalıyordu.

**Değişiklikler (hepsi ölçüldü):**

1. **IDF-ağırlıklı kapsama** (`store._seed_literal`, `_idf`): FTS adayları
   `Σ idf(eşleşen kök) / Σ idf(sorgu kökü)` ile yeniden puanlanıyor; df
   FTS `MATCH` sayımından (fts5vocab aralık sorgusu denendi, yorumlayıcıyı
   bozdu). Bilinmeyen kök en nadir kök sayılıyor — paydadan düşürmek
   denendi, tuzak sorularda ters tepti ("düğün, kuzen" düşünce "zaman"
   %100 kapsama oldu). Soru kelimeleri (hangi, neydi, nerede, kaçta…)
   stopword. Sonuç: yanlış adayların medyanı 0.44 → 0.15, beklenenler 0.42.
2. **Taban 0.12 → 0.25** (`RECALL_PRIME_FLOOR`) + üst kayda göreli kuyruk
   kesimi (0.6×). Tarama: 0.20 / 0.25 / 0.30 → tuzak sessizliği 0.825 /
   0.925 / 0.975, recall 0.77 / 0.74 / 0.68. Genç hafıza (<30 kayıt) tabansız.
3. **Bağlam cezası sorgunun alan sayısına göre** (`/3` yerine `/len(context)`):
   tek alanlı çatışma artık tabana (0.15) iniyor. E kümesi sızıntısı 11 → 0.
4. **Sıcak küme.** Onarılmış bench'te -5.0 eşiği %77 sıcak veriyordu.
   "Soğuk kayıt kesin ipucuyla uyanır" kuralı denendi: recall'ı kurtardı ama
   K kümesinin on yasak sorusunun hepsini sızdırdı (yol haritası 3.11.5:
   yalıtık kayıt prime'a girmez) — geri alındı. Yerine **komşuluk ısısı**
   (`WARM_EDGE=0.8`): ≥0.8 ağırlıklı kenarla sıcak bir düğüme bağlı kayıt
   sıcak kalır (kullanılanın şeması). Tarama eşik×kenar: -4.0/0 → %13,
   -4.0/0.6 → %19, -4.5/0.8 → **%27**, -5.0/0.8 → %56. Seçilen -4.5/0.8.
5. **Bench: ruh muhasebesi.** `user/preference/lesson/voice` kayıtları
   ruhla her turda promptta; bench bunları "ulaşılamadı" sayıyordu. Recall
   artık prime ∪ ruh üzerinden, isabet ve prime_token yalnız prime
   üzerinden (ruhun bedeli `ruh_token`).

**Recall neden 0.8'in altında kaldı (0.74):** veri setinin A kümesi (30
soru) 1. gün yazılıp hiç kullanılmayan gerçekleri 20–85 gün sonra soruyor;
K kümesi aynı şeyi 80–86 gün sonra soruyor ve prime'a GİRMEMESİNİ istiyor.
95. günde ikisi aktivasyon (≈-5.7) ve kenar ağırlığı (≈0.35) bakımından
ayırt edilemiyor; tek fark tür (user/preference → ruh) ve zaman. Ruh
muhasebesi türle ayrılanı kurtardı; `fact` türündeki A kayıtları 3.11'in
söylediği gibi soğuyor. Bu, hedefin değil veri setinin sınırı; belgelendi.

| Metrik | eski | önceki tur | **bu tur** | hedef |
|---|---|---|---|---|
| `prime_precision` | 0.255 | 0.274 | **0.559** | ≥ 0.85 ✗ (2×) |
| `prime_recall` | 0.96 | 0.88 | 0.74 | ≥ 0.8 ✗ |
| `yasak_sizinti` | 59 | 6 | **3** | 0 ✗ |
| `tuzak_sessizlik` | 0.45 | 0.475 | **0.925** | ≥ 0.9 ✅ |
| `sicak_oran` | 1.00 | 0.77 | **0.233** | 0.10–0.30 ✅ |
| `prime_token` | 84.5 | 78.4 | **39.1** | ≤ taban ✅ |
| `sorumluluk_dogrulugu` | 0.50 | 1.00 | 0.875 | ≥ 0.85 ✅ |
| `komsuluk_recall` | 0 | 0.083 | 0.083 | ≥ 0.75 ✗ |
| `buyume_p95` | — | 6.09 | **3.65** | ≤ 1.5 ✗ |
| holdout `prime_precision` | 0.385 | 0.475 | **0.652** | |
| holdout `yasak_sizinti` | 12 | 5 | **0** | |

Süreçler-arası determinizm korunuyor; tüm sayılar `docs/charts/yasam-*.json`.


---

## Faz 7.6 — karakter tutarlılığı, gerçek modellerle · 2026-09-04

Koşu: `docs/charts/karakter-openrouter.md` — 30 karar, 3 bağlam, 3 tekrar
(30 gün arayla), 720 çağrı; modeller `deepseek/deepseek-v4-flash-0731`
(kullanıcının günlük modeli) ve `anthropic/claude-haiku-4.5`, ikisi de
OpenRouter üzerinden, sıcaklık 0, düşünme kapalı. Ürünün kendi backend'i ve
promptu.

**Taban mizaçlar gerçekten farklı** (deney anlamlı): yenilik 0.83 / 0.40,
sonuç 1.0 / 0.80, sebat 0.67 / 0.33, temkin 0.67 / 0.75; sosyal ikisinde 0.17.

| Metrik | deepseek | haiku | ortak | hedef | durum |
|---|---|---|---|---|---|
| `tutarlilik_model` (kaldıraç açık) | — | — | **0.711** | ≥ 0.8 | ✗ |
| `tutarlilik_model_kaldiracsiz` | — | — | 0.611 | rapor | |
| `kaldirac_farki` | — | — | **+0.10** | ≥ 0.15 | ✗ ama yönü doğru |
| `tutarlilik_zaman` (belge açık) | 0.667 | 0.856 | 0.761 | ≥ 0.8 | ✗ (haiku ✓) |
| `tutarlilik_zaman_kimliksiz` | 0.589 | 0.744 | 0.667 | rapor | |
| `kimlik_farki` | +0.078 | +0.111 | **+0.095** | ≥ 0.05 | ✅ |
| `tutarlilik_baglam` | 0.778 | 0.800 | 0.789 | ≥ 0.85 | ✗ |
| `sosyal_ulasilan` | 0.037 | 0.167 | 0.102 | rapor | |
| `belirsiz_oran` | 0.142 | 0.064 | 0.103 | ≤ 0.05 | ✗ |

**Okuma:**

1. **Kaldıraç iş yapıyor ama yetmiyor.** Kaldıraç açıkken iki model %71,
   kapalıyken %61 aynı kararı veriyor: +0.10. Yol haritasının eşiği 0.15;
   "modeller zaten aynı mizaçta" açıklaması taban vektörleriyle çürüyor —
   mizaçlar farklı, kaldıraç farkı kapatıyor ama tam değil. Eksen tablosu
   nedenini gösteriyor: yönlendirme satırları kaba. Haiku'nun yenilik ekseni
   0.40'tan hedefe (0.5) değil 0.67'ye fırladı, sonuç ekseni ters yöne gitti
   (0.80 → 0.93). Bir sonraki adım: satırların şiddetini kaldıraç
   büyüklüğüne göre kademelendirmek.
2. **Kimlik belgesi bir karakter aracı, gösterim aracı değil.** Belge
   açıkken zaman tutarlılığı +0.095 (hedef ≥ 0.05). Yol haritası 7.8'in
   sorusuna cevap: belge kalıyor ve iş yapıyor.
3. **Sosyal eksende bir tasarım hatası yakalandı.** Her iki model onay
   peşinde koşmuyor (0.17); varsayılan hedef 0.5 olduğu için kaldıraç 3.0×
   "daha çok onay ara" satırı üretti — tam ters ders. Düzeltildi: varsayılan
   hedef sosyalde 0.2 (`SOCIAL_TARGET`), sosyal eksende kaldıraç asla 1.0
   üstüne çıkmıyor (yalakalık yalnız bastırılır), ölçülmemiş modelde hiç
   kaldıraç satırı yok. Raporun "yalakalık bastırılamıyor" notu bu koşu için
   yanlış okumaydı: bastırılacak bir şey yoktu.
4. **Belirsizlik ölçümü aşağı çekiyor.** Cevapların %10'u (deepseek %14)
   `KARAR:` satırı yazmadı ve hepsi "uyuşmaz" sayıldı; bütün tutarlılık
   sayıları bu kadar deflasyonlu. Ayrıştırıcıya kesin son-satır yedeği
   eklendi (ham cevaplar saklanmadığı için bu koşu yeniden ayrıştırılamadı;
   bir sonraki koşu daha az belirsiz çıkacak).
5. **Bağlam tutarlılığı 0.79**: kararların beşte biri proje bağlamına göre
   değişiyor. Kısmen belirsizlik, kısmen gerçek — hangi kararların
   savrulduğu bir sonraki koşuda karar bazında raporlanmalı.


---

## Faz 7.6 ikinci koşu — kademeli kaldıraç · 2026-09-04

Aynı iki model, aynı 720 çağrı, tek fark: kaldıraç satırları üç kademeli
(`prompt.leverage_tier`). Rapor: `docs/charts/karakter-openrouter2.md`.

| Metrik | 1. koşu | 2. koşu |
|---|---|---|
| `tutarlilik_model` | 0.711 | 0.600 |
| `tutarlilik_model_kaldiracsiz` | 0.611 | 0.633 |
| `kaldirac_farki` | +0.10 | −0.03 |
| `tutarlilik_zaman` / kimliksiz | 0.761 / 0.667 | 0.717 / 0.745 |
| `kimlik_farki` | +0.095 | −0.028 |
| `tutarlilik_baglam` | 0.789 | 0.661 |
| `belirsiz_oran` | 0.103 | 0.129 (deepseek 0.203) |

**Dürüst okuma: iki koşu aynı şeyi ölçmedi ve ikisi de gürültünün
içinde.** Üç sebep, ham cevaplar artık saklandığı için üçü de görüldü:

1. **Taban ölçümü kaymış.** Eksen başına 6 sonda var; tek bir cevap 0.17
   oynatıyor. deepseek sebat 0.67 → 1.0, temkin 0.67 → 1.0; Haiku yenilik
   0.40 → 0.60, temkin 0.75 → 0.50. Kaldıraç = hedef / taban olduğu için
   kaldıraçlar ve kademeler de değişti: Haiku'nun temkin ekseni 1. koşuda
   "gevşet" satırı alırken 2. koşuda hiç satır almadı ve 0.71'e sürüklendi.
   1. koşudaki +0.095 "kimlik belgesi" farkı da bu gürültüden büyük değil.
2. **deepseek'in OpenRouter yolu bozuk cevaplar üretiyor**: çok dilli token
   çorbası, yer tutucu jetonlar, Türkçe yok. Bunlar "belirsiz" sayılıp
   uyuşmazlık olarak metriklere girdi. Karakterle ilgisi yok, yolla ilgili.
3. **Modeller uzun düşünüp KARAR'a gelmeden bitiriyor** ("duruma göre: X ise
   A, Y ise B…"). İkisi de böyle; deepseek'te beşte bir.

Kademeli satırların işe yarayıp yaramadığı bu aletle **söylenemez**; ölçüm
yanlışının işareti önce düzeltilmeli. Düzeltmeler (bir sonraki koşu için,
hepsi testli):

- `KARAR:` satırı cevabın **başında** isteniyor; gerekçe sonra, en fazla iki
  cümle. Kesilme ve gevezelik artık kararı yutamıyor.
- Bozuk cevap (`is_garbled`, çeyreğinden fazlası Latin/Türkçe dışı) ayrı
  sayılıyor (`bozuk_oran`), belirsizle karışmıyor.
- Ham cevaplar kol adıyla saklanıyor; koşu çevrimdışı yeniden ayrıştırılabilir.
- Taban ölçümü tekrarlı (aşağıda).

Bir eksen bulgusu yine de duruyor ve aleti düzeltince yeniden ölçülecek:
Haiku'nun yenilik ekseni 0.60'tan yalnız bir "biraz" dürtüsüyle 0.34'e indi
(hedef 0.5'i aştı). Tek bir satır, kademesi ne olursa olsun, Haiku'yu
büyük adımlarla oynatıyor — kademeleme gerekli ama yeterli olmayabilir;
kaldıraç doygunluğu (LEVERAGE_HIGH/LOW) yeni modelde daha dar olmalı.
