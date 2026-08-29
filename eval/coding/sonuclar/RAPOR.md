# Kodlama Ölçüm Raporu

**Koşu:** 20260829T053256Z · **Model:** `z-ai/glm-5.3-flash` · **Tekrar:** 2 · **Düzenek:** `eval/coding/` (dış kapı + izole örnek)

Puan dört eksenden: **çalışır mı** 40 · **istenen kapsam** 25 · **kod sağlığı** 20 · **test kalitesi** 15. Bir eksen ölçülemediyse paydadan da düşer; istem o işi istemiyorsa (*istenmedi*) ölçülür ama puana katılmaz. Puan sütunu 100'e normalize edilmiş haldir.

## Puan kırılımı

| görev | zorluk | dil | çalışır (40) | kapsam (25) | sağlık (20) | test (15) | **puan** |
|---|---|---|---|---|---|---|---|
| k1-modul† | kolay | python | 40.0 | 25.0 | 20.0 | 13.0 | **98.0** ±1.0 |
| k2-cli† | kolay | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| k3-tamir† | kolay | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| o1-rapor† | orta | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| o2-servis | orta | python | 40.0 | 25.0 | 20.0 | 14.3 | **99.3** |
| o3-ozellik† | orta | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| z1-arama† | zor | python | 40.0 | 25.0 | 20.0 | 15.0 | **100.0** ±1.5 |
| z2-panel† | zor | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| z3-gizli-hata† | zor | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |

`*` = istem bu işi istemedi; ölçüldü, raporlanıyor, puana katılmıyor.
`†` = bu satır bu koşudan değil, önceki bir koşudan devralındı: k1-modul (20260829T050710Z), k2-cli (20260829T050710Z), k3-tamir (20260829T050710Z), o1-rapor (20260829T050710Z), o3-ozellik (20260829T050710Z), z1-arama (20260829T050710Z), z2-panel (20260829T050710Z), z3-gizli-hata (20260829T050710Z).

## Davranış ölçütleri (puana katılmaz)

| görev | tur bitti | araç çağrısı | hatalı araç | süre sn | token (giren/çıkan) | maliyet $ | kendini doğruladı | plan yazdı | bozuk teslim |
|---|---|---|---|---|---|---|---|---|---|
| k1-modul | evet | 5 | 1 | 47.0 | 80158/1029 | 0.0063 | evet | hayır | 0/2 |
| k2-cli | evet | 3 | 0 | 36.5 | 62456/772 | 0.0049 | hayır | hayır | 0/2 |
| k3-tamir | evet | 3 | 0 | 28.0 | 62658/368 | 0.0048 | hayır | hayır | 0/2 |
| o1-rapor | evet | 4 | 2 | 50.8 | 79528/1123 | 0.0062 | hayır | hayır | 0/2 |
| o2-servis | evet | 14 | 2 | 113.2 | 246908/3218 | 0.0193 | evet | hayır | 0/2 |
| o3-ozellik | evet | 4 | 1 | 38.8 | 80249/857 | 0.0062 | evet | hayır | 0/2 |
| z1-arama | evet | 8 | 1 | 98.0 | 148903/3307 | 0.0120 | evet | hayır | 0/2 |
| z2-panel | evet | 12 | 1 | 111.7 | 145603/4667 | 0.0121 | evet | hayır | 0/2 |
| z3-gizli-hata | evet | 9 | 1 | 52.9 | 148187/852 | 0.0113 | evet | hayır | 0/2 |

**Ortalama puan:** 99.7/100 (9 görev ölçüldü)

## Bu sayılar ne kadar sağlam?

Her görev 2 kez koşuldu; puan sütunundaki ± koşular arası yayılımdır (min-maks yarı genişliği). Yayılımdan küçük farklar iyileştirme sayılmaz.

İzolasyon: her koşu kendi geçici çalışma alanında, **boş bir zihinle** ve kendi neo örneğiyle yapıldı. Kullanıcının anıları taşınmıyor — yani bu düzenek kodlama boru hattını ölçüyor, hafızanın kodlamaya katkısını ölçmüyor.

## Kanıt dökümü

### k1-modul — TCKN doğrulama modülü + testleri

- **çalışır mı: 40.0/40**
  - `+ tckn.py var (10p) — tckn.py`
  - `+ modül import ediliyor (15p) — tamam`
  - `+ dogrula() çağrılabiliyor (15p) — tamam`
- **istenen kapsam: 25.0/25**
  - `~ geçerli numaralara True (10.0/10p) — 5/5`
  - `~ geçersiz numaralara False (10.0/10p) — 6/6`
  - `~ çöp girdide patlamıyor (2.0/2p) — 4/4 girdi istisna atmadı`
  - `~ çöp girdiye False diyor (3.0/3p) — 4/4`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 13.0/15**
  - `+ testler yeşil (6p) — ............. [100%] 13 passed in 0.01s`
  - `~ test adedi (4.0/4p) — 13 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 1/1: dogrula`
  - `~ iddialar dolu (0.0/2p) — 0 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m unittest test_tckn -v`
- araçlar: write_file×2, kos×2, shell×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### k2-cli — Node görev listesi CLI

- **çalışır mı: 40.0/40**
  - `+ gorev.js var (10p) — gorev.js`
  - `+ ekle çalışıyor (10p) — çıkış 0/0`
  - `+ liste çalışıyor (10p) — 1. [ ] süt al 2. [ ] faturayı öde`
  - `+ bilinmeyen komut hata veriyor (10p) — çıkış kodu 1`
- **istenen kapsam: 25.0/25**
  - `+ eklenenler listede görünüyor (10p) — «süt al»: True, «faturayı öde»: True`
  - `+ bitir listeyi değiştiriyor (kalan görev duruyor) (8p) — bitir çıkışı 0; liste değişti`
  - `+ gorevler.json'da kalıcı (7p) — gorevler.json, 109 karakter`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- araçlar: shell×2, write_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### k3-tamir — PHP fatura hesabındaki hatayı bul ve düzelt

- **çalışır mı: 40.0/40**
  - `+ fatura.php duruyor (10p) — fatura.php`
  - `+ php -l temiz (10p) — No syntax errors detected in C:\Users\user\AppData\Local\Temp\neocp-eval-k3-tamir-jyhev1u5\atolye\fatura.php`
  - `+ fonksiyon dışarıdan çağrılabiliyor (20p) — tamam`
- **istenen kapsam: 25.0/25**
  - `+ vaka: üç kalem %18 (10p) — beklenen 82.60, çıkan 82.60`
  - `+ vaka: tek kalem %20 (7p) — beklenen 27.00, çıkan 27.00`
  - `+ vaka: iki kalem %0 (5p) — beklenen 50.00, çıkan 50.00`
  - `+ vaka: boş sipariş (3p) — beklenen 0.00, çıkan 0.00`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- araçlar: read_file×1, edit_file×1, shell×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### o1-rapor — CSV satış raporu + CLI

- **çalışır mı: 40.0/40**
  - `+ rapor.py var (8p) — rapor.py`
  - `+ csv ile koşuyor (16p) — çıkış 0; 2026-01 Toplam ciro: 47553.25 Urun Ciro Pompa 25197.00 Sensor 12159.05 PLC 8249.70 2026-02 Toplam ciro: 33938.45 Urun Ciro Sensor 17278.65 Pompa 8399.00 PLC 549`
  - `+ çıktı boş değil (8p) — 502 karakter`
  - `+ --ay koşuyor (8p) — çıkış 0; 2026-03 Toplam ciro: 99286.90 Urun Ciro Pompa 54593.50 PLC 30248.90 Sensor 12799.00`
- **istenen kapsam: 25.0/25**
  - `~ aylık cirolar doğru (10.0/10p) — 3/3 ay tuttu: 2026-01, 2026-02, 2026-03`
  - `+ en çok ciro yapan 3 ürün var (5p) — Pompa, PLC, Sensor`
  - `+ üçü çoktan aza sıralı (5p) — sıra tuttu`
  - `+ --ay 2026-03 doğru ayı veriyor (3p) — beklenen 99286.9`
  - `+ --ay diğer ayları süzüyor (2p) — temiz`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- araçlar: shell×2, ozet_csv×1, write_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8

### o2-servis — Kısa-link HTTP servisi + testleri

- **çalışır mı: 40.0/40**
  - `+ servis.py var (8p) — kisa-link\servis.py`
  - `+ süreç ayağa kalkıyor (12p) — ayakta`
  - `+ port açılıyor (10p) — 127.0.0.1:8099 açıldı`
  - `+ /saglik 200 (10p) — HTTP 200`
- **istenen kapsam: 25.0/25**
  - `+ POST /kisalt kod dönüyor (10p) — HTTP 200, kod «uuxafn»; gövde '{"kod": "uuxafn"}'`
  - `+ GET /<kod> 302 yönlendiriyor (10p) — HTTP 302, Location «https://ornek.gov.tr/ihale/2026/sondaj»`
  - `+ olmayan kod 404 (5p) — HTTP 404`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 14.3/15**
  - `+ testler yeşil (6p) — ..... [100%] 5 passed in 0.53s`
  - `~ test adedi (3.3/4p) — 5 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 2/2: kisalt, saglik`
  - `~ iddialar dolu (2.0/2p) — 9 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m unittest test_servis.py -v`; `shell: py -m unittest test_servis.py -v`; `shell: py -m unittest test_servis.py -v`
- araçlar: read_file×8, shell×3, write_file×2, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### o3-ozellik — Kitaplığa ödünç verme ekle (mevcut testler kırılmasın)

- **çalışır mı: 40.0/40**
  - `+ kitaplik.js duruyor (8p) — kitaplik.js`
  - `+ node --check temiz (6p)`
  - `+ modül yükleniyor (8p) — tamam`
  - `+ bozulmamış testler yeşil (18p) — TAP version 13 # Subtest: kitap eklenebiliyor ok 1 - kitap eklenebiliyor --- duration_ms: 0.4893 type: 'test' ... # Subtest: aynı ISBN iki kez eklenemiyor ok 2 - aynı ISBN iki kez `
- **istenen kapsam: 25.0/25**
  - `+ oduncVer çalışıyor (6p) — {'ok': True, 'deger': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'odunc': 'Mehmet'}}`
  - `+ liste ödünçteki kişiyi gösteriyor (5p) — [{"isbn":"978-1","baslik":"Kuyu","yazar":"Ahmet","odunc":"Fatih"},{"isbn":"978-2","baslik":"Zeytin","yazar":"Ayse"}]`
  - `+ ikinci ödünç hata fırlatıyor (6p) — {'ok': False, 'hata': "Kitap zaten ödünçte: 978-1 (Fatih'da)"}`
  - `+ olmayan ISBN hata fırlatıyor (4p) — {'ok': False, 'hata': 'Bu ISBN kayıtlı değil: yok-boyle'}`
  - `+ iadeAl kitabı serbest bırakıyor (4p) — {'ok': True, 'deger': 'Fatih'}`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `! tohumda zaten test takımı var — bu eksen ajanın kendi katkısını ayıramaz, o yüzden puana katılmıyor`
  - `- test dosyası yok (0p)`
- doğrulama izi: `shell: node -e "const {Kitaplik}=require('./atolye/kitaplik.js');const k=new Kitaplik();k.ekle('1`; `shell: node -e "const {Kitaplik}=require('C:/Users/user/AppData/Local/Temp/neocp-eval-o3-ozellik-`
- araçlar: shell×2, read_file×1, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8

### z1-arama — SQLite kalıcılıklı not arama aracı

- **çalışır mı: 40.0/40**
  - `+ ara.py var (5p) — ara.py`
  - `+ ekle koşuyor (12p) — çıkış 0; Indeks guncel: 6 dosya tarandi, 0 yeni, 0 guncellendi.`
  - `+ SQLite dosyası oluştu (8p) — ara_index.db`
  - `+ bul ayrı süreçte koşuyor (15p) — çıkış 0; 1 sonuc ('salmastra'): 1. pompa-katalog.txt ..., debi 12 m3/saat. Yedek parca: rulman, salmastra, motor mili....`
- **istenen kapsam: 25.0/25**
  - `+ tek kelime doğru notu buluyor (8p) — «salmastra» → pompa-katalog bekleniyordu; çıktı: "1 sonuc ('salmastra'):\n\n1. pompa-katalog.txt\n   ..., debi 12 m3/saat. Yedek parca: rulman, salmastra, motor mili....\n\n\n"`
  - `+ çok kelimede hepsi geçen not üstte (10p) — «rulman titresim» → kuyu-bakim yeri 33, pompa-katalog yeri 182`
  - `+ olmayan kelimede sonuç uydurmuyor (7p) — «helikopter» → çıktı: "Sonuc yok: 'helikopter' icin eslesen not bulunamadi.\n\n"`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 15.0/15**
  - `+ testler yeşil (6p) — ........ [100%] 8 passed in 1.10s`
  - `~ test adedi (4.0/4p) — 8 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 2/2: ekle, bul`
  - `~ iddialar dolu (2.0/2p) — 14 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m pytest test_ara.py -q`
- araçlar: shell×4, write_file×2, list_dir×1, kos×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 13

### z2-panel — Giriş korumalı mini yönetim paneli

- **çalışır mı: 40.0/40**
  - `+ index.php var (8p) — panel`
  - `! 8098 tutuluydu (ajan kendi sunucusunu açık bırakmış olabilir); ölçüm 8100 portunda yapıldı`
  - `+ sunucu ayağa kalkıyor (10p) — port açıldı`
  - `+ giriş sayfası açılıyor (10p) — 200, 1418 karakter; şifre alanı: True`
  - `+ doğru şifreyle içeri giriliyor (12p) — giriş POST → HTTP 200; ozet.php → HTTP 200`
- **istenen kapsam: 25.0/25**
  - `~ girişsiz erişim engelleniyor (7.0/7p) — ozet.php: engelli; kullanicilar.php: engelli; ayarlar.php: engelli`
  - `+ yanlış şifre reddediliyor (3p) — yanlış şifreden sonra ozet.php → HTTP 302`
  - `+ ozet.php giriş sonrası çalışıyor (5p) — 200, 1749 karakter`
  - `+ kullanicilar.php giriş sonrası çalışıyor (5p) — 200, 2300 karakter`
  - `+ ayarlar.php giriş sonrası çalışıyor (5p) — 200, 1865 karakter`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 6/6 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- doğrulama izi: `browser: `; `shell: $b='http://127.0.0.1:8098'; $j='test_cookie.txt'; "1) girissiz ozet:"; curl.exe -s -o NUL `; `shell: $b='http://127.0.0.1:8098'; $j='t.txt'; curl.exe -s "$b/index.php" -d 'kullanici=admin&sif`
- araçlar: write_file×7, shell×4, browser×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### z3-gizli-hata — Sepet modülündeki 3 gizli hatayı bul ve düzelt

- **çalışır mı: 40.0/40**
  - `+ sepet.py duruyor (6p) — sepet\sepet.py`
  - `+ modül import ediliyor (10p) — tamam`
  - `+ bozulmamış regresyon takımı koşuyor (8p) — ........ [100%] 8 passed in 0.01s`
  - `+ regresyon takımı tamamen yeşil (16p) — ........ [100%] 8 passed in 0.01s`
- **istenen kapsam: 25.0/25**
  - `+ hata 1: aynı ürün eklenince adet birikiyor (8p) — beklenen [7, 21.0], çıkan [7, 21.0]`
  - `+ hata 2: indirim sınırları dahil (8p) — 500→0.05 (0.05), 1000→0.1 (0.10), 499.99→0.0 (0.0)`
  - `+ hata 3: toplam kuruşu koruyor (6p) — 7 × 14.29 → beklenen 100.03, çıkan 100.03`
  - `+ gizli vaka: 1500 → %10, 500 → %5 (2p) — 1500→1350.0 (1350.0), 500→475.0 (475.0)`
  - `+ var olan koruma sökülmemiş (adet 0 → ValueError) (1p) — {'ok': True, 'deger': 'ValueError'}`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `! regresyon takımı tohumla geliyor — bu eksen ajanın kendi katkısını ayıramaz, puana katılmıyor`
  - `- test dosyası yok (0p)`
- doğrulama izi: `shell: cd atolye\sepet; py -m pytest -q`; `shell: py -m pytest -q`
- araçlar: read_file×3, edit_file×3, shell×2, list_dir×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8
