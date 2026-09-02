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
gece kapalıyken ölçülen bozulma eğrisinden (`--esik-egrisi`, 2026-09-02).
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

## Faz 5 — Bağlam bonusu · sırada
## Faz 7 — Ödül, mizaç, üç özne, karakter · bekliyor
## Faz 6 — Beyin görünümü · bekliyor
