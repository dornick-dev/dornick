# Hafıza yükseltmesi — sonuç raporu (sade dille)

*2026-09-03 · dal `hafiza-insan-benzeri` · eski sürüm = `hafiza-eski` etiketi (yükseltmeden önceki `main`)*

Bu rapor tek bir soruya cevap veriyor: **bu işi yaptık da ne oldu?** Teknik
tablo en altta; önce düz cümlelerle.

---

## 1. Kısa cevap

Evet, anlamlı bir gelişme var, ama her yerde değil. Üç cümleyle:

1. **Ajan artık daha az saçmalıyor.** Yanlış projeden hatıra getirme 59'dan
   1'e düştü; eskimiş bir kuralı "hâlâ geçerli" diye öne sürme 3,5'ten sıfıra
   indi; öne sürdüğü hatıraların isabeti %26'dan %45'e çıktı.
2. **Ajan artık hatasından ertesi gün değil, hemen ders çıkarıyor.** Eski
   sürümde bir hatanın ders olarak hafızaya girmesi ortalama 79 tur sürüyordu;
   şimdi 1 tur. Hangi hatıranın hataya götürdüğünü de %50 değil %88 doğrulukla
   söylüyor.
3. **Bunları daha az token harcayarak yapıyor** ve hafıza büyüdükçe
   yavaşlamıyor: 200 bin kayıtta arama gecikmesi 33 ms'den 18 ms'ye, bellekte
   tuttuğu indeks 14 MB'tan 0,1 MB'a indi.

Gelişmeyen iki şey var, aşağıda saklamadan yazdım (bölüm 4).

---

## 2. Nasıl ölçtük — neden bu sayılara güvenilebilir

Sayı üretmenin kolay yolu, kodu yazanın kendi senaryosunda kendi kodunu
denemesidir; öyle yapmadık. Şunlar var:

- **Aynı hayat, iki beyin.** 90 günlük sanal bir takvim üzerinde 905 olaylık
  (286 oturum) bir yaşam senaryosu var: kayıt, düzeltme, hata, başarı, sessiz
  günler, proje değişimi. Eski sürüm ve yeni sürüm bu senaryoyu **aynı
  sırayla, aynı saatlerle** yaşıyor. Fark hafıza katmanından geliyor; başka
  bir şey değişmedi.
- **Eski sürüm donduruldu.** `main`, `hafiza-eski` etiketiyle dondurulup ayrı
  bir dizine alındı; bench onu ayrı bir süreçte gerçekten koşturuyor. "Eski"
  sütunu tahmin değil, ölçüm.
- **Kalibrasyon ana sete uydurulmadı mı diye ayrı sınav.** Sabitlerin hepsi
  ana veri setine bakılarak ayarlandı. Ezber yapmış olma ihtimaline karşı hiç
  bakılmamış ikinci bir senaryo (holdout, 30 gün) en son koşuldu: yön aynı,
  isabet ana setten bile yüksek (0,39 → 0,48). Ezber yok.
- **Her mekaniğin anahtarı var.** Her yeni mekanik tek tek kapatılıp bench
  yeniden koşuldu. "Bu parça ne kazandırıyor" sorusunun cevabı ölçüldü; işe
  yaramayan parça raporda işe yaramadı diye yazıldı (bölüm 4).
- **2001 birim testi** yükseltmeden önce 1678'di; hepsi geçiyor. Eski bir
  bellek dosyası (`recall-v1.db`) yeni kodla açılıp kayıp olmadan okunuyor.

---

## 3. Ne değişti — günlük hayatta ne demek

| Ne | Eski | Yeni | Bu ne demek |
|---|---|---|---|
| Öne sürülen hatıraların isabeti | %26 | **%45** | Ajan konuşmaya başlarken bağlama otomatik eklediği hatıraların yarıya yakını artık gerçekten işe yarıyor; eskiden dörtte biri. |
| Yanlış projeden sızan hatıra | 59 | **1** | SCADA işi yaparken kripto notunun araya girmesi: 90 günde 59 kez oluyordu, şimdi 1. |
| Ruha giren bayat kural | 3,5 | **0** | Ajanın "kimliği" olan kısa liste eskimiş bir kuralı artık taşımıyor; düzeltilmiş hâli taşıyor. |
| Bu haftaki düzeltme ruhta mı | %100 | **%100** | Bir kuralı bu hafta düzelttiysen, ajan bir sonraki oturumda yeni hâline göre davranıyor. |
| Hatadan ders çıkarma gecikmesi | 79 tur | **1 tur** | Eskiden hata "bir şekilde" ders oluyordu; şimdi sonuç belli olur olmaz ters tekrar koşuyor. |
| Hataya götüren hatırayı bulma | %50 | **%88** | "Bu hata hangi hatıradan çıktı" sorusuna yazı-tura değil, doğru cevap. |
| Düzeltilen kayda geri dönme | %100 | **%100** | Bir kaydı güncelledin; eski hâlini istediğinde hâlâ bulunuyor. Hiçbir şey silinmiyor. |
| Ruhun token maliyeti | 325 | **310** | Her oturumun başına konan kimlik metni kısaldı. |
| Öne sürme token maliyeti | 84 | **75** | Otomatik hatıra enjeksiyonu daha ucuz. |
| Sıcak hafıza payı | %100 | **%22** | Eskiden bütün hafıza her aramada RAM'deydi; şimdi son kullanılan beşte biri. Gerisi soğukta, istenince ısınıyor. |
| 200 bin kayıtta arama (p95) | 33 ms | **18 ms** | Hafıza büyüdükçe arama yavaşlamıyor. |
| 200 bin kayıtta indeks RAM'i | 14,4 MB | **0,14 MB** | Yüz kat daha küçük. |
| Şema tazeleme | yoktu | **0,80** | Gece, gündüz kullanılan kaydın eski komşularını da tazeliyor (eski sürümde böyle bir mekanik yoktu). |

`scale_bench` (tek turluk, eskiden beri olan bench): recall 0,78 → 0,83,
coverage 0,76 → 0,81, precision 0,63 → 0,65, sorgu başına token 71,8 → 70,7.
Yani eski ölçek de gerilemedi, hafifçe iyileşti.

**Yeni gelen ve eskide karşılığı olmayan davranışlar** (bunları eskiyle
kıyaslamak mümkün değil, sadece var/yok):

- Gece geçişi: oturumları önem sırasına koyup tekrar ediyor, dersleri ve
  yordamları yazıyor, hiç yan yana yaşanmamış iki hatırayı dikiyor, hiç
  dokunulmayan kenarları küçültüyor (uyku homeostazı).
- Uyku dinamiği: ölçülen basınca göre uyuyor, kullanıcı gelince yarım
  bıraktığı işi ertesi geceye devrediyor, ritmini (hafta içi mesai) öğreniyor.
- Uyanık tekrar: sonuç belli olunca sabahı beklemeden kısa ters tekrar;
  mikro-uyku ve yerel uyku.
- Supersede: bir kayıt güncellenince eskisi silinmiyor, "yerini aldı" diye
  bağlanıyor; ajan eskisini açarsa "güncellendi" uyarısı alıyor.
- Üç özne (kullanıcı / dünya / kendisi), ödül sinyali, mizaç, merak bütçesi,
  kanıtlı kimlik belgesi — mekanikleri kurulu ve testli; ölçümü bölüm 5'te.

---

## 4. Gelişmeyen ya da gerileyen şeyler (saklamadan)

| Ne | Eski | Yeni | Neden, ne yapılacak |
|---|---|---|---|
| Öne sürmede kapsama (`prime_recall`) | %96 | **%76** | Tasarım sonucu: soğuyan ve bağlamı çatışan kayıt artık kendiliğinden enjekte edilmiyor. Aynı değişiklik sızıntıyı 59'dan 1'e indirdi. Kayıtlar kaybolmadı: açık aramada hepsi bulunuyor (%100). Ama "daha az şey enjekte ediyor" gerçeğini yazmak lazım. |
| Tuzak sessizliği | %45 | **%50** | Alakasız soruda susma. Hedef %90'dı, tutmadı. Sebebi aşağıdaki "tohum doygunluğu". |
| Komşuluk / dikiş çağrışımı | 0 | **0** | Gece kurulan kenarlar var (ağırlık 0,47) ama aramada işe yaramıyor: tek bir ortak kelimeyi paylaşan yirmi kayıt 0,5 üstü skor alıyor, komşuluk bu gürültüyü aşamıyor. Adı **tohum doygunluğu**; üç fazda aynı duvara çarptı. Tek bilinen çare `vector.py`'ye IDF ağırlığı — yol haritasında hiçbir fazın kapsamında değildi, yapılmadı. |
| Kodlama gücü (Faz 4) | — | etkisiz | Sürprizli kaydı daha güçlü yazma mekaniği kuruldu, anahtarı kapatınca hiçbir metrik değişmedi. Sebebi yine tohum doygunluğu: sürpriz ölçüsü herkese aynı değeri veriyor. Kod duruyor, faydası kanıtlanmadı diye işaretli. |
| Damıtma token hedefi | — | tutmadı | Gece damıtması öne sürme isabetini %64 artırıyor ama token hedefinin altına inmiyor. |

Bunların hiçbiri yükseltmeyi geri almayı gerektirmiyor; ama "her şey düzeldi"
de değil.

---

## 5. Ölçülmeyenler — bu raporun boş kalan satırları

Yol haritasının son karşılaştırma tablosunda şu satırlar boş. Sebebi para ya
da model gerektirmesi; kod tarafı hazır.

| Deney | Durum | Ne gerekiyor |
|---|---|---|
| Yaşam bench, 3 tekrar ortalaması | tek koşu | Bench deterministik (aynı tohum → aynı rapor, testi var); 3 tekrar kuralı model-döngülü bench'ler için anlamlı. Yine de istenirse 3 kez koşulup ortalaması yazılır. |
| 9 görevlik kodlama bench'i, sıcak hafızayla | koşulmadı | `docs/benchmark-2026-08.md` rig'i; iki sürüm önce 30 gün "yaşatılıp" sonra 9 görev. Model çağrısı gerektirir (`z-ai/glm-5.3-flash`, 3 tekrar ≈ 27 görev × 2 sürüm). **API bütçesi lazım.** |
| Aynı 9 görev, soğuk hafıza (kontrol) | koşulmadı | Aynı rig, aynı bütçe. |
| Kirlilik deneyi (28.08 C kolu) yeniden | koşulmadı | Aynı rig. |
| Gece geçişi süresi 50k düğüm / 200 oturum | ölçülmedi | Sentetik; model gerektirmez, koşulabilir. |
| Model değişimi sonrası karakter tutarlılığı (Faz 7.6) | ölçülmedi | 30 karar seti + iki gerçek model (Anthropic → yerel). **Model erişimi ve bütçe lazım.** |

---

## 6. Yapılmayanlar (kod)

- **Faz 6 görsel katman** — beyin bölgeleri, gece animasyonu, gündüz görünümü,
  kimlik/mizaç panelleri, Playwright uçtan uca testler. Veri katmanı hazır
  (donmuş olay şeması, `/api/uyku`, `/api/gece/<tarih>`), arayüz çizilmedi.
- **Kodun İngilizce'ye çevrilmesi** — bu raporun yazıldığı sırada yapılıyor;
  bitince buraya işlenecek.
- Temizlik tablosunun 7 satırından 3'ü kurulu (checkpoint, FTS optimize,
  VACUUM); gece başı yedek, eski gece günlüklerini sıkıştırma ve önbellek
  boşaltma yok.
- CI iş akışı (`hafiza.yml`) ve satır kapsamı ölçümü yok.

---

## 7. Teknik ek — tam tablo

Ana set (90 gün, 905 olay). "yok" = o sürümde bu mekanik yok ya da o sette bu
olay türü yok.

| Metrik | Yön | eski | yeni | Hedef |
|---|---|---|---|---|
| `prime_precision` | ↑ | 0.2553 | **0.4471** | ≥ 0.85 ✗ |
| `prime_recall` | ↑ | 0.96 | 0.76 | ≥ 0.8 ✗ (tasarım) |
| `yasak_sizinti` | ↓ | 59 | **1** | ≤ 0 (≈) |
| `tuzak_sessizlik` | ↑ | 0.45 | 0.50 | ≥ 0.9 ✗ |
| `bayat_ruh` | ↓ | 3.48 | **0** | ≤ 0 ✓ |
| `taze_ruh` | ↑ | 1.00 | **1.00** | ≥ 0.8 ✓ |
| `ruh_token` | ↓ | 325.0 | **309.9** | ≤ taban ✓ |
| `prime_token` | ↓ | 84.07 | **74.74** | ≤ taban ✓ |
| `geri_donus_recall` | ↑ | 1.00 | **1.00** | ≥ 0.7 ✓ |
| `komsuluk_recall` | ↑ | 0 | 0 | ≥ 0.75 ✗ |
| `sorumluluk_dogrulugu` | ↑ | 0.50 | **0.875** | ≥ 0.85 ✓ |
| `dikis_recall` | ↑ | 0 | 0 | ≥ 0.6 ✗ |
| `gomulme_recall` | ↑ | 1.00 | **1.00** | ≥ 0.9 ✓ |
| `sema_tazeleme` | ↑ | yok | **0.80** | > 0 ✓ |
| `yakalama` | ↑ | yok | 0.006 | > 0 (≈) |
| `ders_gecikmesi` | ↓ | 79.4 | **1.0** | ≤ 1 ✓ |
| `sicak_oran` | · | 1.00 | **0.22** | 0.10–0.30 ✓ |
| `gecikme_p95` (ms) | ↓ | 8.97 | **5.39** | — |

Holdout (30 gün, 43 düğüm, hiç bakılmamış set — yalnız gündüz yolu):

| Metrik | eski | yeni |
|---|---|---|
| `prime_precision` | 0.385 | **0.475** |
| `prime_recall` | 1.00 | 0.95 |
| `yasak_sizinti` | 12 | **5** |
| `bayat_ruh` | 1.63 | **0** |
| `ruh_token` | 130.0 | **113.8** |
| `prime_token` | 56.3 | **50.4** |
| `sicak_oran` | 1.00 | 0.88 |

Büyüme (P kümesi, 20k → 200k düğüm): recall p95 33.2 → **18.4 ms**, imza
indeksi RAM 14.4 MB → **0.14 MB**, `buyume_p95` 6.78 → 3.4.

Ayrıntılı faz defteri, kalibrasyonlar ve olumsuz sonuçlar:
`docs/hafiza-fazlar.md`. Ham koşular: `docs/charts/yasam-*.json`.
