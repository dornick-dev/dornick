# Kodlama Ölçüm Raporu

**Koşu:** 20260828T230330Z · **Model:** `z-ai/glm-5.3-flash` · **Tekrar:** 2 · **Düzenek:** `eval/coding/` (dış kapı + izole örnek)

Puan dört eksenden: **çalışır mı** 40 · **istenen kapsam** 25 · **kod sağlığı** 20 · **test kalitesi** 15. Bir eksen ölçülemediyse paydadan da düşer; istem o işi istemiyorsa (*istenmedi*) ölçülür ama puana katılmaz. Puan sütunu 100'e normalize edilmiş haldir.

## Puan kırılımı

| görev | zorluk | dil | çalışır (40) | kapsam (25) | sağlık (20) | test (15) | **puan** |
|---|---|---|---|---|---|---|---|
| k1-modul | kolay | python | 40.0 | 25.0 | 20.0 | 13.0 | **98.0** ±1.0 |
| k2-cli | kolay | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| k3-tamir | kolay | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| o1-rapor | orta | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| o2-servis | orta | python | 40.0 | 25.0 | 20.0 | 14.3 | **99.3** |
| o3-ozellik | orta | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| z1-arama | zor | python | 40.0 | 25.0 | 20.0 | 15.0 | **100.0** ±1.7 |
| z2-panel | zor | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| z3-gizli-hata | zor | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |

`*` = istem bu işi istemedi; ölçüldü, raporlanıyor, puana katılmıyor.

## Davranış ölçütleri (puana katılmaz)

| görev | tur bitti | araç çağrısı | hatalı araç | süre sn | token (giren/çıkan) | maliyet $ | kendini doğruladı | plan yazdı | bozuk teslim |
|---|---|---|---|---|---|---|---|---|---|
| k1-modul | evet | 6 | 1 | 47.3 | 113367/1431 | 0.0089 | evet | hayır | 0/2 |
| k2-cli | evet | 3 | 0 | 29.6 | 62735/929 | 0.0049 | hayır | hayır | 0/2 |
| k3-tamir | evet | 4 | 0 | 24.2 | 78442/433 | 0.0060 | hayır | hayır | 0/2 |
| o1-rapor | evet | 5 | 1 | 44.6 | 95803/1009 | 0.0074 | hayır | hayır | 0/2 |
| o2-servis | evet | 9 | 2 | 75.9 | 152085/2249 | 0.0120 | evet | hayır | 0/2 |
| o3-ozellik | evet | 6 | 0 | 39.5 | 112545/871 | 0.0087 | evet | hayır | 0/2 |
| z1-arama | evet | 12 | 2 | 208.5 | 220659/3729 | 0.0175 | evet | hayır | 0/2 |
| z2-panel | evet | 24 | 3 | 174.8 | 394385/7049 | 0.0313 | evet | hayır | 0/2 |
| z3-gizli-hata | evet | 7 | 1 | 25.6 | 112037/586 | 0.0085 | evet | hayır | 0/2 |

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
  - `+ testler yeşil (6p) — ......... [100%] 9 passed in 0.01s`
  - `~ test adedi (4.0/4p) — 9 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 1/1: dogrula`
  - `~ iddialar dolu (0.0/2p) — 0 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m unittest test_tckn -v`; `shell: py -m unittest test_tckn -v`
- araçlar: write_file×2, shell×2, kos×1, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### k2-cli — Node görev listesi CLI

- **çalışır mı: 40.0/40**
  - `+ gorev.js var (10p) — gorev.js`
  - `+ ekle çalışıyor (10p) — çıkış 0/0`
  - `+ liste çalışıyor (10p) — [ ] 1. süt al [ ] 2. faturayı öde`
  - `+ bilinmeyen komut hata veriyor (10p) — çıkış kodu 1`
- **istenen kapsam: 25.0/25**
  - `+ eklenenler listede görünüyor (10p) — «süt al»: True, «faturayı öde»: True`
  - `+ bitir listeyi değiştiriyor (kalan görev duruyor) (8p) — bitir çıkışı 0; liste değişti`
  - `+ gorevler.json'da kalıcı (7p) — gorevler.json, 217 karakter`
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
  - `+ php -l temiz (10p) — No syntax errors detected in C:\Users\user\AppData\Local\Temp\neocp-eval-k3-tamir-ppn6l09b\atolye\fatura.php`
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
- araçlar: shell×2, read_file×1, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### o1-rapor — CSV satış raporu + CLI

- **çalışır mı: 40.0/40**
  - `+ rapor.py var (8p) — rapor.py`
  - `+ csv ile koşuyor (16p) — çıkış 0; 2026-01 Toplam ciro: 47553.25 1. Pompa: 25197.00 2. Sensor: 12159.05 3. PLC: 8249.70 2026-02 Toplam ciro: 33938.45 1. Sensor: 17278.65 2. Pompa: 8399.00 3. PLC:`
  - `+ çıktı boş değil (8p) — 275 karakter`
  - `+ --ay koşuyor (8p) — çıkış 0; 2026-03 Toplam ciro: 99286.90 1. Pompa: 54593.50 2. PLC: 30248.90 3. Sensor: 12799.00`
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
- araçlar: ozet_csv×1, write_file×1, edit_file×1, read_file×1, shell×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8

### o2-servis — Kısa-link HTTP servisi + testleri

- **çalışır mı: 40.0/40**
  - `+ servis.py var (8p) — servis.py`
  - `+ süreç ayağa kalkıyor (12p) — ayakta`
  - `+ port açılıyor (10p) — 127.0.0.1:8099 açıldı`
  - `+ /saglik 200 (10p) — HTTP 200`
- **istenen kapsam: 25.0/25**
  - `+ POST /kisalt kod dönüyor (10p) — HTTP 200, kod «ysnyxw»; gövde '{"kod": "ysnyxw"}'`
  - `+ GET /<kod> 302 yönlendiriyor (10p) — HTTP 302, Location «https://ornek.gov.tr/ihale/2026/sondaj»`
  - `+ olmayan kod 404 (5p) — HTTP 404`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 14.3/15**
  - `+ testler yeşil (6p) — ..... [100%] 5 passed in 0.52s`
  - `~ test adedi (3.3/4p) — 5 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 2/2: kisalt, saglik`
  - `~ iddialar dolu (2.0/2p) — 6 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m unittest test_servis -v`; `shell: py -m unittest test_servis -v`; `shell: py -m unittest test_servis -v`
- araçlar: shell×3, write_file×2, edit_file×2, kos×1, read_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### o3-ozellik — Kitaplığa ödünç verme ekle (mevcut testler kırılmasın)

- **çalışır mı: 40.0/40**
  - `+ kitaplik.js duruyor (8p) — kitaplik.js`
  - `+ node --check temiz (6p)`
  - `+ modül yükleniyor (8p) — tamam`
  - `+ bozulmamış testler yeşil (18p) — TAP version 13 # Subtest: kitap eklenebiliyor ok 1 - kitap eklenebiliyor --- duration_ms: 0.5141 type: 'test' ... # Subtest: aynı ISBN iki kez eklenemiyor ok 2 - aynı ISBN iki kez `
- **istenen kapsam: 25.0/25**
  - `+ oduncVer çalışıyor (6p) — {'ok': True, 'deger': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'odunc': {'kisi': 'Mehmet', 'alinma': '2026-`
  - `+ liste ödünçteki kişiyi gösteriyor (5p) — [{"isbn":"978-1","baslik":"Kuyu","yazar":"Ahmet","odunc":{"kisi":"Fatih","alinma":"2026-08-28T23:15:30.304Z"}},{"isbn":"978-2","baslik":"Zey`
  - `+ ikinci ödünç hata fırlatıyor (6p) — {'ok': False, 'hata': 'Kitap zaten ödünçte: 978-1 (Fatih)'}`
  - `+ olmayan ISBN hata fırlatıyor (4p) — {'ok': False, 'hata': 'Olmayan ISBN: yok-boyle'}`
  - `+ iadeAl kitabı serbest bırakıyor (4p) — {'ok': True, 'deger': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'odunc': {'kisi': 'Mehmet', 'alinma': '2026-`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `! tohumda zaten test takımı var — bu eksen ajanın kendi katkısını ayıramaz, o yüzden puana katılmıyor`
  - `- test dosyası yok (0p)`
- doğrulama izi: `shell: node --test`; `shell: node -e "const {Kitaplik}=require('./kitaplik'); const k=new Kitaplik(); k.ekle('1','Dune'`
- araçlar: edit_file×2, shell×2, read_file×1, list_dir×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8

### z1-arama — SQLite kalıcılıklı not arama aracı

- **çalışır mı: 40.0/40**
  - `+ ara.py var (5p) — ara.py`
  - `+ ekle koşuyor (12p) — çıkış 0; 0 yeni, 0 guncellendi, 6 degisiklik yok.`
  - `+ SQLite dosyası oluştu (8p) — ara.db`
  - `+ bul ayrı süreçte koşuyor (15p) — çıkış 0; a.txt Kuyu bakim notlari Dalgic pompa [salmastra] degistirmesi pompa-katalog.txt ... rulman, [salmastra], motor mili.`
- **istenen kapsam: 25.0/25**
  - `+ tek kelime doğru notu buluyor (8p) — «salmastra» → pompa-katalog bekleniyordu; çıktı: 'a.txt\n    Kuyu bakim notlari\nDalgic pompa [salmastra] degistirmesi\n\npompa-katalog.txt\n     ... rulman, [salmastra], moto'`
  - `+ çok kelimede hepsi geçen not üstte (10p) — «rulman titresim» → kuyu-bakim yeri 60, pompa-katalog yeri 161`
  - `+ olmayan kelimede sonuç uydurmuyor (7p) — «helikopter» → çıktı: "'helikopter' icin hicbir not bulunamadi.\n\n"`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 15.0/15**
  - `+ testler yeşil (6p) — ...... [100%] 6 passed in 0.76s`
  - `~ test adedi (4.0/4p) — 6 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 2/2: ekle, bul`
  - `~ iddialar dolu (2.0/2p) — 10 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m pytest test_ara.py -v 2>&1; py -m pytest --version 2>&1`; `shell: py -m pytest "$env:TEMP\neocp-eval-z1-arama-g4_x93o3\atolye\test_ara.py" -v 2>&1`; `shell: py -m pytest "$env:TEMP\neocp-eval-z1-arama-g4_x93o3\atolye\test_ara.py" -v 2>&1`; `shell: $d="$env:TEMP\neocp-eval-z1-arama-g4_x93o3\atolye"; (Get-Content "$d\test_ara.py" -Raw) `
`
- araçlar: shell×5, read_file×2, write_file×2, list_dir×1, kos×1, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 13

### z2-panel — Giriş korumalı mini yönetim paneli

- **çalışır mı: 40.0/40**
  - `+ index.php var (8p) — panel`
  - `! 8098 tutuluydu (ajan kendi sunucusunu açık bırakmış olabilir); ölçüm 8100 portunda yapıldı`
  - `+ sunucu ayağa kalkıyor (10p) — port açıldı`
  - `+ giriş sayfası açılıyor (10p) — 200, 1172 karakter; şifre alanı: True`
  - `+ doğru şifreyle içeri giriliyor (12p) — giriş POST → HTTP 200; ozet.php → HTTP 200`
- **istenen kapsam: 25.0/25**
  - `~ girişsiz erişim engelleniyor (7.0/7p) — ozet.php: engelli; kullanicilar.php: engelli; ayarlar.php: engelli`
  - `+ yanlış şifre reddediliyor (3p) — yanlış şifreden sonra ozet.php → HTTP 302`
  - `+ ozet.php giriş sonrası çalışıyor (5p) — 200, 2731 karakter`
  - `+ kullanicilar.php giriş sonrası çalışıyor (5p) — 200, 3155 karakter`
  - `+ ayarlar.php giriş sonrası çalışıyor (5p) — 200, 2648 karakter`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 7/7 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- doğrulama izi: `browser: `; `shell: $r1 = Invoke-WebRequest -Uri "http://127.0.0.1:8098/ozet.php" -MaximumRedirection 0 -Error`; `shell: cmd /c "echo --- giris olmadan korunan sayfa --- & curl.exe -s -o NUL -w %{http_code} %{re`; `shell: curl.exe -s -c cj.txt -d "kullanici=admin&sifre=9999" http://127.0.0.1:8098/index.php > y1`
- araçlar: write_file×10, shell×10, read_file×2, plan×1, browser×1
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
- doğrulama izi: `shell: Get-ChildItem atolye/sepet -Recurse | Select-Object FullName; py -m pytest atolye/sepet -x`; `shell: cd atolye\sepet; py -m pytest -q`
- araçlar: shell×2, list_dir×2, read_file×2, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8
