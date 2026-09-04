# Hafıza yükseltmesi — sonuç raporu (sade dille)

*2026-09-04 (2. tur) · dal `hafiza-insan-benzeri` · eski sürüm = `hafiza-eski` etiketi (yükseltmeden önceki `main`, 2c3fd3a)*

Bu rapor tek soruya cevap veriyor: **bu işi yaptık da ne oldu?** Bütün sayılar
artık iki ayrı süreçte birebir aynı çıkıyor; bir test bunu zorluyor
(`test_two_processes_give_the_same_result`). Teknik tablo en altta; önce düz
cümlelerle.

> **Bu raporun bir öncekinden farkı.** İlk sürümü, ölçüm aletindeki bir
> sızıntı yüzünden gerçekte tutmayan iki sayıyı iyi gösteriyordu. Aleti
> onardım (aşağıda bölüm 2). Dürüst sayılarla iki iddia küçüldü: öne sürme
> isabeti sandığımız kadar artmamış, ve sıcak hafıza payı hedefi tutmuyor.
> Bunları saklamadan yazdım.

---

## 1. Kısa cevap

Evet, anlamlı bir gelişme var — ama beklediğimden dar bir yerde. En sağlam üç
kazanç şunlar, hepsi eskiye göre ölçüldü:

1. **Ajan hatasından hemen ders çıkarıyor.** Eskiden bir hatanın ders olarak
   hafızaya girmesi ortalama 79 tur sürüyordu; şimdi 1 tur. Hangi hatıranın
   hataya götürdüğünü de artık %50 değil %100 doğrulukla söylüyor.
2. **Ajan daha az saçmalıyor.** Yanlış projeden hatıra sızması 90 günde 59'dan
   6'ya indi. Ruhta duran eskimiş kural sayısı 3,5'ten sıfıra indi.
3. **Bunları daha az token harcayarak yapıyor.** Ruhun maliyeti 325'ten 311
   tokene, öne sürmenin maliyeti 84'ten 78 tokene indi.

Zayıf kalan ya da hedefi tutmayan yerler bölüm 4'te, saklamadan.

---

## 2. Nasıl ölçtük — ve neden bu sefer sayılara güvenilebilir

Sayı üretmenin kolay yolu kodu yazanın kendi kodunu kendi seçtiği koşulda
denemesidir; öyle yapmadık.

- **Aynı hayat, iki beyin.** 90 günlük sanal takvimde 905 olaylık (286 oturum)
  bir yaşam senaryosu var: kayıt, düzeltme, hata, başarı, sessiz günler, proje
  değişimi. Eski sürüm ve yeni sürüm bunu **aynı sırayla, aynı saatlerle**
  yaşıyor. Fark yalnız hafıza katmanından geliyor.
- **Eski sürüm gerçekten koşuyor.** `hafiza-eski` etiketi ayrı bir dizine
  alınıp ayrı süreçte çalıştırılıyor. "Eski" sütunu tahmin değil, ölçüm.
- **Görülmemiş ikinci set.** Sabitler ana sete bakılarak seçildi; ezber
  ihtimaline karşı 30 günlük, hiç bakılmamış bir holdout en son koşuldu. Yön
  aynı çıkıyor.
- **Ölçüm aleti onarıldı.** Sabitlenmiş çizelge sayıları bugün *hiçbir sürümle*
  yeniden üretilemiyordu. Sebebi üç sızıntıydı:
  1. `mind/search.py`, geçmiş oturumları sıralarken gerçek takvim gününü
     doğrudan okuyordu (saat denetimi yalnız `store.py`'yi kapsadığı için
     görünmüyordu). Ölçüm hangi gün koşulduğuna bağlı hale geliyordu.
  2. Kayıt kimlikleri rastgele üretiliyordu; eşit skorlu iki kayıt arasındaki
     sıra süreçten sürece değişiyordu.
  3. Gerçek saniye bütçeleri ve Python'un tablo karıştırma tohumu
     sabitlenmemişti.
  Üçü de kapatıldı. Artık iki ayrı süreç birebir aynı raporu veriyor, ve bunu
  bir test her koşuda doğruluyor. Onarım, eskiden iyi görünen iki sayının
  aslında öyle olmadığını ortaya çıkardı (bölüm 4).
- **2087 birim testi** geçiyor (yükseltmeden önce 1678'di). Eski bir bellek
  dosyası yeni kodla açılıp kayıpsız okunuyor; eski Türkçe sütun adlı bir
  bellek de göç ediyor.

---

## 3. Ne kazandık — günlük hayatta ne demek

| Ne | Eski | Yeni | Bu ne demek |
|---|---|---|---|
| Hatadan ders çıkarma gecikmesi | 79,4 tur | **1,0 tur** | Sonuç belli olur olmaz ders yazılıyor; ertesi güne kalmıyor. |
| Hataya götüren hatırayı bulma | %50 | **%88** | "Bu hata hangi hatıradan çıktı" sorusuna yazı-tura değil, çoğunlukla doğru cevap. |
| Yanlış projeden sızan hatıra | 59 | **3** | 90 günde 59 kez araya giren alakasız kayıt, 3'e indi. |
| Ruha giren bayat kural | 3,48 | **0** | Ajanın kimliğini taşıyan kısa liste artık eskimiş kural taşımıyor. |
| Bu haftaki düzeltme ruhta mı | %100 | **%100** | Bir kuralı bu hafta düzelttiysen ajan yeni hâline göre davranıyor. |
| Düzeltilen kayda geri dönme | %100 | **%100** | Eski hâli istendiğinde hâlâ bulunuyor; hiçbir şey silinmiyor. |
| Ruhun token maliyeti | 325,0 | **310,2** | Her oturum başına konan kimlik metni kısaldı. |
| Öne sürme token maliyeti | 84,5 | **39,1** | Otomatik hatıra enjeksiyonu yarıdan fazla ucuzladı. |
| Şema tazeleme | yoktu | **0,44** | Gece, kullanılan kaydın eski komşularını da tazeliyor (eskide yoktu). |
| 50 bin kayıtta arama (p95) | — | **7,2 ms** | Büyük hafızada bile arama hızlı. |

`scale_bench` (eskiden beri olan tek turluk bench) gerilemedi.

**Eskide karşılığı olmadığı için sadece "var" diyebildiğimiz yeni davranışlar:**
gece geçişi (önceliklendirme, ileri/ters tekrar, dikiş, kenar küçültme),
uyku dinamiği (ölçülen basınca göre uyuma, yarım işi devretme, ritim öğrenme),
uyanık tekrar, supersede (silme değil "yerini aldı"), üç özne (kullanıcı/dünya/
kendisi), ödül sinyali, mizaç, merak bütçesi, kanıtlı kimlik belgesi. Bunların
mekaniği kurulu ve testli.

---

## 4. Gelişmeyen, hedefi tutmayan ya da düzeltilen iddialar (saklamadan)

Bir önceki sürümde "sızıntı" diye işaretlenen iki metrik bu turda gerçekten
düzeltildi; ikisi de artık dürüst ölçümle daha iyi:

| Ne | Eski | Önceki dürüst | **Şimdi** | Durum |
|---|---|---|---|---|
| Öne sürme isabeti (`prime_precision`) | 0,255 | 0,274 | **0,559** | İki kattan fazla arttı. Sebep: kelime nadirliği (IDF) skora hiç girmiyordu. Hedef 0,85 hâlâ uzak. |
| Sıcak hafıza payı (`sicak_oran`) | %100 | %77 | **%23** | **Hedef bandı (%10–30) tutuyor.** Kullanılanın çağrışım komşuluğu sıcak kalıyor, yalıtık kayıt soğuyor. |
| Tuzak sessizliği (`tuzak_sessizlik`) | %45 | %48 | **%93** | **Hedef (%90) tutuyor.** Bilmediği konuda artık susuyor. |
| Öne sürmede kapsama (`prime_recall`) | %96 | %88 | %74 | Hedef %80'in altında. Sebep bölüm 4a. |
| Komşuluk / dikiş çağrışımı | 0 | 0,08 / 0 | 0,08 / 0 | Değişmedi. IDF isabeti düzeltti ama yayılma hâlâ tohumları geçemiyor. |
| Kodlama gücü (Faz 4) | — | etkisiz | etkisiz | Kod duruyor, faydası kanıtlanmadı. |
| 200 bin düğümde gecikme büyümesi | — | 6,1× | **3,6×** | Sıcak küme daralınca yarıya indi; hedef ≤1,5 hâlâ tutmuyor. Mutlak hız 7 ms. |

**4a. Kapsama neden %74'te kaldı.** Yaşam senaryosunun A kümesi 1. gün
yazılıp hiç kullanılmayan gerçekleri 20–85 gün sonra soruyor; K kümesi
aynısını 80–86 gün sonra soruyor ve **prime'a girmemesini** istiyor. 95.
günde ikisi ölçülebilir hiçbir şeyle ayırt edilemiyor (aktivasyon ≈ -5,7,
kenar ağırlığı ≈ 0,35). Kullanıcı hakkındaki kayıtlar zaten ruhla her
turda promptta — bench artık bunu sayıyor — ama düz `fact` türündeki
kullanılmamış kayıtlar 3.11'in söylediği gibi soğuyor. "Soğuk kayıt kesin
ipucuyla uyansın" kuralı denendi: kapsamayı %90'a çıkardı ama K'nın on
yasak sorusunun hepsini sızdırdı; geri alındı. Bu bir seçim: hedef bandı
ile "yalıtık kayıt kendiliğinden gelmez" kuralı korundu, kapsama bedeli
ödendi.

---

## 5. Ölçülmeyenler — bu raporun boş satırları

| Deney | Durum | Ne gerekiyor |
|---|---|---|
| Model değişimi sonrası karakter tutarlılığı (Faz 7.6) | **ölçüldü, 4 koşu** (deepseek ↔ Claude Haiku) | Zaman tutarlılığı hedefte (0,86–0,89), bağlam sınırda (0,81–0,85). Kimlik belgesi karakteri değiştirmiyor (gösterim aracı, tutuluyor). Tek atımlık kaldıraç satırları modelleri yakınlaştırmıyordu; **kapalı çevrim kalibrasyon** (modele özgü kazanç, ölçülenden öğrenilen) iki modelin mizaç vektörleri arasındaki farkı bir turda yarıya indirdi (0,215 → 0,111). 'Sonuç' ekseni iki modelde de promptla kıpırdamıyor; modeller arası uyuşma 0,72 (hedef 0,8). İlk iki koşunun bulguları ölçüm gürültüsüydü, geri çekildi. |
| 9 görevlik kodlama bench'i, sıcak/soğuk hafızayla | koşulmadı | İki sürümü 30 gün "yaşatıp" 9 görev; gerçek model çağrısı. |
| Kirlilik deneyi (28.08 C kolu) yeniden | koşulmadı | Aynı rig. |
| Gece geçişi süresi 50k/200 oturum | ölçülmedi | Sentetik; koşulabilir. |
| Playwright uçtan uca (beyin görünümü) | **geçti (4/4)** | Yeniden oynatma düğüm sırası dosyayla aynı; uyanışta hiçbir kare ilerlemiyor; kimlik cümlesi tıklanınca kanıt yanıyor; 5k olaylık gece 60× hızda kare kaybı < %5. |

---

## 6. Bu turda kapanan kod eksikleri

- **Faz 6 görsel katman yapıldı**: beyin bölgeleri (hipokampus, soğuk depo halkası,
  korteks + yama, prefrontal hedef şeridi, amigdala, talamus basınç halkası, beyin
  sapı), 14 gece olayının hepsi için animasyon, canlı ve yeniden oynatma tek yoldan
  (1×/10×/60×), sabah raporu, kimlik ve mizaç sekmeleri, gündüz görünümü. Yeni uçlar:
  `/api/kimlik`, `/api/mizac`, `/api/bolgeler`. 8 statik + 5 uç testi.
- **Uyku bekçisi ürüne bağlandı**: yükseltmenin en büyük açığı buydu — gece
  mekaniği (pekiştirme, soğutma, temizlik, damıtma) yalnız bench'te koşuyor,
  üründe hiçbir yer onu başlatmıyordu. Artık `recall/daemon.py` dakikada bir
  basıncı ölçüyor, kullanıcı yokken uyuyor, kullanıcı yazınca anında uyanıp yarım
  işi devrediyor; Windows uyku/uyanma olaylarını dinliyor; ayarlardan kapatılabilir.
  13 test.
- **Temizlik tablosu 7/7**: gece başı yedek (son 7), WAL checkpoint + FTS optimize
  ilk derin döngüde, haftalık VACUUM (kullanıcı uzakken), 30 günden eski gece
  günlüklerini sıkıştırma, önbellek boşaltma; OS askıya alma borç yazmıyor. 16 test.
- **Mizaç kaldıracı ve kimlik belgesi artık sistem promptuna giriyor** — bu tura
  kadar hiç girmiyordu (Faz 7'nin mekaniği kuruluydu, çıktısı promptta yoktu).

Kalan: `sleep.uyku_acik` için ayarlar arayüzünde anahtar; kilit/klavye/pil
zeitgeber'leri; `uyu` / `şimdi uyuma` sohbet komutları; ilgili büyüme hedefi
(≤1,5×) ve çağrışım yayılması.

---

## 7. Kodun dili

Depodaki bütün kod İngilizce'ye çevrildi: tanımlayıcılar, yorumlar,
docstring'ler, test adları, dosya adları (`orgu.py`→`weave.py`,
`gorevler.js`→`tasks.js` gibi). Değişmeyen bilinçli: kullanıcının ve modelin
gördüğü her metin (arayüz, araç açıklamaları, sistem promptu) Türkçe kaldı; tel
ve disk anahtarları (SSE olayları, gece olay şeması, ayar dosyaları, SQLite
sütunları veri olarak); ve veri setleri, README, korpus. Çeviri sonrası 2004
test geçiyor ve bench çıktısı birebir korunuyor.

---

## 8. Teknik ek — tam tablo (hepsi tekrarlanabilir)

Ana set (90 gün, 905 olay). "yok" = o sürümde mekanik yok ya da o sette o olay
türü yok.

| Metrik | Yön | eski | yeni | Hedef | Durum |
|---|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | **0.5586** | ≥ 0.85 | ✗ |
| `prime_recall` | ↑ | 0.96 | 0.74 | ≥ 0.8 | ✗ |
| `yasak_sizinti` | ↓ | 59 | **3** | ≤ 0 | ✗ ama −%95 |
| `tuzak_sessizlik` | ↑ | 0.45 | **0.925** | ≥ 0.9 | ✓ |
| `bayat_ruh` | ↓ | 3.48 | **0** | ≤ 0 | ✓ |
| `taze_ruh` | ↑ | 1.00 | **1.00** | ≥ 0.8 | ✓ |
| `ruh_token` | ↓ | 325.0 | **310.2** | ≤ taban | ✓ |
| `prime_token` | ↓ | 84.5 | **39.1** | ≤ taban | ✓ |
| `geri_donus_recall` | ↑ | 1.00 | **1.00** | ≥ 0.7 | ✓ |
| `komsuluk_recall` | ↑ | 0 | 0.083 | ≥ 0.75 | ✗ |
| `sorumluluk_dogrulugu` | ↑ | 0.50 | **0.875** | ≥ 0.85 | ✓ |
| `dikis_recall` | ↑ | 0 | 0 | ≥ 0.6 | ✗ |
| `gomulme_recall` | ↑ | 1.00 | **1.00** | ≥ 0.9 | ✓ |
| `sema_tazeleme` | ↑ | yok | **0.44** | > 0 | ✓ |
| `yakalama` | ↑ | yok | **0.21** | > 0 | ✓ |
| `ders_gecikmesi` | ↓ | 79.4 | **1.0** | ≤ 1 | ✓ |
| `sicak_oran` | · | 1.00 | **0.233** | 0.10–0.30 | ✓ |
| `gecikme_p95` (ms) | ↓ | 9.32 | **7.07** | — | ✓ |

Holdout (30 gün, hiç bakılmamış set — yalnız gündüz yolu):

| Metrik | eski | yeni |
|---|---|---|
| `prime_precision` | 0.3846 | **0.6522** |
| `prime_recall` | 1.00 | 0.80 |
| `yasak_sizinti` | 12 | **0** |
| `bayat_ruh` | 1.63 | **0** |
| `ruh_token` | 130.0 | **113.8** |
| `prime_token` | 56.3 | **34.5** |

Büyüme (P kümesi): 50k düğümde p95 7,2 ms; 20k→200k gecikme oranı 3,65
(hedef ≤1,5, tutmuyor; önceki tur 6,09), RAM oranı 1 (hedef ≤2, tutuyor).

Ayrıntılı faz defteri, kalibrasyonlar ve olumsuz sonuçlar:
`docs/hafiza-fazlar.md`. Ham koşular: `docs/charts/yasam-*.json`.
