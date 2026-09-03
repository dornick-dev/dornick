# Hafıza yükseltmesi — sonuç raporu (sade dille)

*2026-09-04 · dal `hafiza-insan-benzeri` · eski sürüm = `hafiza-eski` etiketi (yükseltmeden önceki `main`, 2c3fd3a)*

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
- **2004 birim testi** geçiyor (yükseltmeden önce 1678'di). Eski bir bellek
  dosyası yeni kodla açılıp kayıpsız okunuyor; eski Türkçe sütun adlı bir
  bellek de göç ediyor.

---

## 3. Ne kazandık — günlük hayatta ne demek

| Ne | Eski | Yeni | Bu ne demek |
|---|---|---|---|
| Hatadan ders çıkarma gecikmesi | 79,4 tur | **1,0 tur** | Sonuç belli olur olmaz ders yazılıyor; ertesi güne kalmıyor. |
| Hataya götüren hatırayı bulma | %50 | **%100** | "Bu hata hangi hatıradan çıktı" sorusuna yazı-tura değil, doğru cevap. |
| Yanlış projeden sızan hatıra | 59 | **6** | 90 günde 59 kez araya giren alakasız kayıt, 6'ya indi. |
| Ruha giren bayat kural | 3,48 | **0** | Ajanın kimliğini taşıyan kısa liste artık eskimiş kural taşımıyor. |
| Bu haftaki düzeltme ruhta mı | %100 | **%100** | Bir kuralı bu hafta düzelttiysen ajan yeni hâline göre davranıyor. |
| Düzeltilen kayda geri dönme | %100 | **%100** | Eski hâli istendiğinde hâlâ bulunuyor; hiçbir şey silinmiyor. |
| Ruhun token maliyeti | 325,0 | **310,8** | Her oturum başına konan kimlik metni kısaldı. |
| Öne sürme token maliyeti | 84,5 | **78,4** | Otomatik hatıra enjeksiyonu ucuzladı. |
| Şema tazeleme | yoktu | **0,68** | Gece, kullanılan kaydın eski komşularını da tazeliyor (eskide yoktu). |
| 50 bin kayıtta arama (p95) | — | **5,25 ms** | Büyük hafızada bile arama hızlı. |

`scale_bench` (eskiden beri olan tek turluk bench) gerilemedi.

**Eskide karşılığı olmadığı için sadece "var" diyebildiğimiz yeni davranışlar:**
gece geçişi (önceliklendirme, ileri/ters tekrar, dikiş, kenar küçültme),
uyku dinamiği (ölçülen basınca göre uyuma, yarım işi devretme, ritim öğrenme),
uyanık tekrar, supersede (silme değil "yerini aldı"), üç özne (kullanıcı/dünya/
kendisi), ödül sinyali, mizaç, merak bütçesi, kanıtlı kimlik belgesi. Bunların
mekaniği kurulu ve testli.

---

## 4. Gelişmeyen, hedefi tutmayan ya da düzeltilen iddialar (saklamadan)

| Ne | Eski | Yeni | Durum |
|---|---|---|---|
| Öne sürme isabeti (`prime_precision`) | 0,255 | **0,274** | Arttı ama çok az. Bir önceki rapor bunu 0,45 gösteriyordu; o sayı ölçüm sızıntısının ürünüydü, gerçek değil. Hedef 0,85, uzak. |
| Sıcak hafıza payı (`sicak_oran`) | %100 | **%77** | Düştü ama hedef %10–30'du, **tutmuyor**. Bir önceki rapor bunu %22 (hedefi geçmiş) gösteriyordu; yine sızıntı. Sıcak küme istenen kadar daralmıyor. |
| Öne sürmede kapsama (`prime_recall`) | %96 | **%88** | Tasarım gereği düştü: soğuyan/çatışan kayıt kendiliğinden enjekte edilmiyor. Kayıtlar kaybolmadı, açık aramada hepsi bulunuyor (%100). |
| Tuzak sessizliği | %45 | **%48** | Alakasız soruda susma. Hedef %90, neredeyse hiç ilerlemedi. |
| Komşuluk / dikiş çağrışımı | 0 | **0,08 / 0** | Gece kenar kuruyor ama aramada işe yaramıyor. Adı **tohum doygunluğu**: tek ortak kelimeli yirmi kayıt 0,5 üstü skor alıyor. Tek çare `vector.py`'ye IDF; hiçbir fazın kapsamında değildi. |
| Kodlama gücü (Faz 4) | — | etkisiz | Ablation'da hiçbir metrik değişmedi. Kod duruyor, faydası kanıtlanmadı. |
| 200 bin düğümde gecikme büyümesi | — | **6,1× (hedef ≤1,5)** | Mutlak hızlı (5 ms), ama "sabit zaman" iddiası bu sette tutmuyor: 20 binden 200 bine gecikme 6 katına çıkıyor. RAM oranı 1 (hedef ≤2, tutuyor). |

Bunların hiçbiri yükseltmeyi geri almayı gerektirmiyor; ama "her şey düzeldi"
de değil, ve bu raporun ilk sürümü iki yerde fazla iyimserdi.

---

## 5. Ölçülmeyenler — bu raporun boş satırları

| Deney | Durum | Ne gerekiyor |
|---|---|---|
| 9 görevlik kodlama bench'i, sıcak hafızayla | koşulmadı | İki sürümü 30 gün "yaşatıp" 9 görev; gerçek model çağrısı gerektirir. **API bütçesi lazım.** |
| Aynı 9 görev, soğuk hafıza (kontrol) | koşulmadı | Aynı bütçe. |
| Kirlilik deneyi (28.08 C kolu) yeniden | koşulmadı | Aynı rig. |
| Model değişimi sonrası karakter tutarlılığı (Faz 7.6) | ölçülmedi | 30 karar seti + iki gerçek model. **Model erişimi ve bütçe lazım.** |
| Gece geçişi süresi 50k/200 oturum | ölçülmedi | Sentetik; koşulabilir. |

---

## 6. Yapılmayanlar (kod)

- **Faz 6 görsel katman** — beyin bölgeleri, gece animasyonu, kimlik/mizaç
  panelleri, Playwright uçtan uca testler. Veri katmanı hazır, arayüz çizilmedi.
- Temizlik tablosunun 7 satırından 3'ü kurulu (checkpoint, FTS optimize,
  VACUUM); gece başı yedek, eski günlükleri sıkıştırma, önbellek boşaltma yok.
- CI iş akışı `hafiza.yml` eklendi ama gerçek runner'da hiç koşmadı.
- Satır kapsamı (%90 hedefi) ölçülmedi.

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
| `prime_precision` | ↑ | 0.2553 | 0.2741 | ≥ 0.85 | ✗ |
| `prime_recall` | ↑ | 0.96 | 0.88 | ≥ 0.8 | ✓ |
| `yasak_sizinti` | ↓ | 59 | **6** | ≤ 0 | ✗ ama −%90 |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.475 | ≥ 0.9 | ✗ |
| `bayat_ruh` | ↓ | 3.48 | **0** | ≤ 0 | ✓ |
| `taze_ruh` | ↑ | 1.00 | **1.00** | ≥ 0.8 | ✓ |
| `ruh_token` | ↓ | 325.0 | **310.8** | ≤ taban | ✓ |
| `prime_token` | ↓ | 84.5 | **78.4** | ≤ taban | ✓ |
| `geri_donus_recall` | ↑ | 1.00 | **1.00** | ≥ 0.7 | ✓ |
| `komsuluk_recall` | ↑ | 0 | 0.083 | ≥ 0.75 | ✗ |
| `sorumluluk_dogrulugu` | ↑ | 0.50 | **1.00** | ≥ 0.85 | ✓ |
| `dikis_recall` | ↑ | 0 | 0 | ≥ 0.6 | ✗ |
| `gomulme_recall` | ↑ | 1.00 | **1.00** | ≥ 0.9 | ✓ |
| `sema_tazeleme` | ↑ | yok | **0.68** | > 0 | ✓ |
| `yakalama` | ↑ | yok | 0.011 | > 0 | ✓ |
| `ders_gecikmesi` | ↓ | 79.4 | **1.0** | ≤ 1 | ✓ |
| `sicak_oran` | · | 1.00 | 0.77 | 0.10–0.30 | ✗ |
| `gecikme_p95` (ms) | ↓ | 8.43 | **5.21** | — | ✓ |

Holdout (30 gün, hiç bakılmamış set — yalnız gündüz yolu):

| Metrik | eski | yeni |
|---|---|---|
| `prime_precision` | 0.3846 | **0.4750** |
| `prime_recall` | 1.00 | 0.95 |
| `yasak_sizinti` | 12 | **5** |
| `bayat_ruh` | 1.63 | **0** |
| `ruh_token` | 130.0 | **113.8** |
| `prime_token` | 56.3 | **50.4** |
| `sicak_oran` | 1.00 | 0.88 |

Büyüme (P kümesi): 50k düğümde p95 5,25 ms; 20k→200k gecikme oranı 6,09
(hedef ≤1,5, tutmuyor), RAM oranı 1 (hedef ≤2, tutuyor).

Ayrıntılı faz defteri, kalibrasyonlar ve olumsuz sonuçlar:
`docs/hafiza-fazlar.md`. Ham koşular: `docs/charts/yasam-*.json`.
