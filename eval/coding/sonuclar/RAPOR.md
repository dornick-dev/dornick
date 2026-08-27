# Kodlama Ölçüm Raporu

**Koşu:** 20260827T114900Z · **Model:** `minimax/minimax-m2.7` · **Tekrar:** 1 · **Düzenek:** `eval/coding/` (dış kapı + izole örnek)

Puan dört eksenden: **çalışır mı** 40 · **istenen kapsam** 25 · **kod sağlığı** 20 · **test kalitesi** 15. Bir eksen ölçülemediyse paydadan da düşer; istem o işi istemiyorsa (*istenmedi*) ölçülür ama puana katılmaz. Puan sütunu 100'e normalize edilmiş haldir.

## Puan kırılımı

| görev | zorluk | dil | çalışır (40) | kapsam (25) | sağlık (20) | test (15) | **puan** |
|---|---|---|---|---|---|---|---|
| k1-modul† | kolay | python | 40.0 | 15.0 | 20.0 | 9.0 | **84.0** |
| k2-cli† | kolay | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |
| k3-tamir† | kolay | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |
| o1-rapor† | orta | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |
| o2-servis† | orta | python | 40.0 | 25.0 | 18.7 | 9.0 | **92.7** |
| o3-ozellik† | orta | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |
| z1-arama | zor | python | 25.0 | 7.0 | 20.0 | 15.0 | **67.0** |
| z2-panel† | zor | php | 40.0 | 20.0 | 14.0 | 0.0* | **87.1** |
| z3-gizli-hata | zor | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |

`*` = istem bu işi istemedi; ölçüldü, raporlanıyor, puana katılmıyor.
`†` = bu satır bu koşudan değil, önceki bir koşudan devralındı: k1-modul (20260827T111835Z), k2-cli (20260827T111835Z), k3-tamir (20260827T111835Z), o1-rapor (20260827T111835Z), o2-servis (20260827T111835Z), o3-ozellik (20260827T111835Z), z2-panel (20260827T111835Z).

## Davranış ölçütleri (puana katılmaz)

| görev | tur bitti | araç çağrısı | hatalı araç | süre sn | token (giren/çıkan) | maliyet $ | kendini doğruladı | plan yazdı | bozuk teslim |
|---|---|---|---|---|---|---|---|---|---|
| k1-modul | evet | 10 | 5 | 825.0 | 278598/4525 | 0.0890 | evet | hayır | 0/1 |
| k2-cli | evet | 6 | 0 | 24.7 | 168082/1512 | 0.0522 | hayır | hayır | 0/1 |
| k3-tamir | evet | 4 | 2 | 379.4 | 113052/939 | 0.0350 | evet | hayır | 0/1 |
| o1-rapor | evet | 11 | 4 | 427.3 | 284517/2466 | 0.0883 | evet | hayır | 0/1 |
| o2-servis | **HAYIR** | 13 | 5 | 900.0 | 327507/6337 | 0.1059 | evet | hayır | 0/1 |
| o3-ozellik | evet | 14 | 4 | 80.1 | 392019/3043 | 0.1213 | evet | hayır | 0/1 |
| z1-arama | **HAYIR** | 16 | 5 | 900.0 | 408893/6396 | 0.1303 | evet | hayır | 0/1 |
| z2-panel | evet | 52 | 8 | 475.2 | 1476276/13435 | 0.4590 | evet | hayır | 0/1 |
| z3-gizli-hata | **HAYIR** | 16 | 6 | 900.0 | 396973/2642 | 0.1223 | evet | hayır | 0/1 |

**Turu bitmeden puanlanan görevler:** o2-servis, z1-arama, z3-gizli-hata. Bu satırlardaki puan ajanın BİTMİŞ işini değil, süre dolduğunda atölyede ne varsa onu ölçüyor — aşağı yönlü sapmalıdır.

**Ortalama puan:** 92.3/100 (9 görev ölçüldü)

## Bu sayılar ne kadar sağlam?

**Tek koşu gürültüdür.** Buradaki her puan tek atıştan geliyor; aynı görev aynı modelle yeniden koşulduğunda birkaç puan oynayabilir, bazı görevlerde (araç hatası, zaman aşımı) çok daha fazla. Bir iyileştirmenin işe yaradığını söylemek için `--tekrar 3` ile koşup ± aralığına bakmak gerekiyor. Tek koşudaki büyük fark (>15 puan) anlamlı, küçük fark (<5 puan) gürültüden ayırt edilemez.

İzolasyon: her koşu kendi geçici çalışma alanında, **boş bir zihinle** ve kendi neo örneğiyle yapıldı. Kullanıcının anıları taşınmıyor — yani bu düzenek kodlama boru hattını ölçüyor, hafızanın kodlamaya katkısını ölçmüyor.

## Kanıt dökümü

### k1-modul — TCKN doğrulama modülü + testleri

- **çalışır mı: 40.0/40**
  - `+ tckn.py var (10p) — tckn.py`
  - `+ modül import ediliyor (15p) — tamam`
  - `+ dogrula() çağrılabiliyor (15p) — tamam`
- **istenen kapsam: 15.0/25**
  - `~ geçerli numaralara True (0.0/10p) — 0/5`
  - `~ geçersiz numaralara False (10.0/10p) — 6/6`
  - `~ çöp girdide patlamıyor (2.0/2p) — 4/4 girdi istisna atmadı`
  - `~ çöp girdiye False diyor (3.0/3p) — 4/4`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 9.0/15**
  - `- testler yeşil (6p) — FFFFF................ [100%] ================================== FAILURES =================================== ___________`
  - `~ test adedi (4.0/4p) — 6 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 1/1: dogrula`
  - `~ iddialar dolu (2.0/2p) — 6 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m pytest atolye/test_tckn.py -v`; `shell: py -m pytest atolye/test_tckn.py -v --tb=short 2>&1 | head -60`; `shell: py -c "import sys; sys.path.insert(0, 'atolye'); from tckn import dogrula; print('1:', dog`; `shell: py -c "import sys; sys.path.insert(0, 'atolye'); from tckn import dogrula; print(dogrula('`
- araçlar: shell×6, write_file×3, read_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 6

### k2-cli — Node görev listesi CLI

- **çalışır mı: 40.0/40**
  - `+ gorev.js var (10p) — gorev.js`
  - `! ajanın bıraktığı gorevler.json ölçümden önce silindi (temiz sayfa)`
  - `+ ekle çalışıyor (10p) — çıkış 0/0`
  - `+ liste çalışıyor (10p) — 1. [ ] süt al 2. [ ] faturayı öde`
  - `+ bilinmeyen komut hata veriyor (10p) — çıkış kodu 1`
- **istenen kapsam: 25.0/25**
  - `+ eklenenler listede görünüyor (10p) — «süt al»: True, «faturayı öde»: True`
  - `+ bitir listeyi değiştiriyor (kalan görev duruyor) (8p) — bitir çıkışı 0; liste değişti`
  - `+ gorevler.json'da kalıcı (7p) — gorevler.json, 145 karakter`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- araçlar: shell×5, write_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 6

### k3-tamir — PHP fatura hesabındaki hatayı bul ve düzelt

- **çalışır mı: 40.0/40**
  - `+ fatura.php duruyor (10p) — fatura.php`
  - `+ php -l temiz (10p) — No syntax errors detected in C:\Users\user\AppData\Local\Temp\neocp-eval-k3-tamir-ctix1n64\atolye\fatura.php`
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
- doğrulama izi: `shell: php -r "
$siparis = [
    ['adet' => 2, 'fiyat' => 10.0],
    ['adet' => 1, 'fiyat' => 30.`
- araçlar: shell×2, read_file×1, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 6

### o1-rapor — CSV satış raporu + CLI

- **çalışır mı: 40.0/40**
  - `+ rapor.py var (8p) — rapor.py`
  - `+ csv ile koşuyor (16p) — çıkış 0; ══════════════════════════════════════════════ 2026-01 | Ciro: 47,553.25 TL ────────────────────────────────────────────── Ürün Ciro (TL) ──────────── ─────────`
  - `+ çıktı boş değil (8p) — 1090 karakter`
  - `+ --ay koşuyor (8p) — çıkış 0; ══════════════════════════════════════════════ 2026-03 | Ciro: 99,286.90 TL ────────────────────────────────────────────`
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
- doğrulama izi: `shell: python -c "print('test')"`
- araçlar: shell×4, ozet_csv×2, read_file×2, list_dir×1, write_file×1, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### o2-servis — Kısa-link HTTP servisi + testleri

- **çalışır mı: 40.0/40**
  - `+ servis.py var (8p) — servis.py`
  - `+ süreç ayağa kalkıyor (12p) — ayakta`
  - `+ port açılıyor (10p) — 127.0.0.1:8099 açıldı`
  - `+ /saglik 200 (10p) — HTTP 200`
- **istenen kapsam: 25.0/25**
  - `+ POST /kisalt kod dönüyor (10p) — HTTP 200, kod «wwajav»; gövde '{"kod": "wwajav"}'`
  - `+ GET /<kod> 302 yönlendiriyor (10p) — HTTP 302, Location «https://ornek.gov.tr/ihale/2026/sondaj»`
  - `+ olmayan kod 404 (5p) — HTTP 404`
- **kod sağlığı: 18.7/20**
  - `~ sözdizimi temiz (8.0/8p) — 3/3 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (4.7/6p) — tekrar eden satır %8, 4 yinelenen blok`
- **test kalitesi: 9.0/15**
  - `- testler yeşil (6p) — ......F. [100%] ================================== FAILURES =================================== _____________ TestYonlen`
  - `~ test adedi (4.0/4p) — 8 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 2/2: kisalt, saglik`
  - `~ iddialar dolu (2.0/2p) — 17 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m pytest test_servis.py -v`; `shell: py -m pytest test_servis.py -v 2>&1`; `shell: py -c "import http.server; print('http ok')"`
- araçlar: shell×8, write_file×5
- ! dış kapı: tur zaman aşımına uğradı
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 6

### o3-ozellik — Kitaplığa ödünç verme ekle (mevcut testler kırılmasın)

- **çalışır mı: 40.0/40**
  - `+ kitaplik.js duruyor (8p) — kitaplik.js`
  - `+ node --check temiz (6p)`
  - `+ modül yükleniyor (8p) — tamam`
  - `+ bozulmamış testler yeşil (18p) — TAP version 13 # Subtest: kitap eklenebiliyor ok 1 - kitap eklenebiliyor --- duration_ms: 0.5654 type: 'test' ... # Subtest: aynı ISBN iki kez eklenemiyor ok 2 - aynı ISBN iki kez `
- **istenen kapsam: 25.0/25**
  - `+ oduncVer çalışıyor (6p) — {'ok': True, 'deger': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'oduncDurumu': True, 'oduncKisi': 'Mehmet'}}`
  - `+ liste ödünçteki kişiyi gösteriyor (5p) — [{"isbn":"978-1","baslik":"Kuyu","yazar":"Ahmet","oduncDurumu":true,"oduncKisi":"Fatih"},{"isbn":"978-2","baslik":"Zeytin","yazar":"Ayse","o`
  - `+ ikinci ödünç hata fırlatıyor (6p) — {'ok': False, 'hata': 'Bu kitap zaten ödünçte: Kuyu'}`
  - `+ olmayan ISBN hata fırlatıyor (4p) — {'ok': False, 'hata': 'Bu ISBN kayıtlarda yok: yok-boyle'}`
  - `+ iadeAl kitabı serbest bırakıyor (4p) — {'ok': True, 'deger': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'oduncDurumu': True, 'oduncKisi': 'Mehmet'}}`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `! tohumda zaten test takımı var — bu eksen ajanın kendi katkısını ayıramaz, o yüzden puana katılmıyor`
  - `- test dosyası yok (0p)`
- doğrulama izi: `shell: node --test atolye/kitaplik.test.js`; `shell: cd atolye && node --test kitaplik.test.js`; `shell: node --test kitaplik.test.js`; `shell: node --test "D:\Projects\Fatih\neocp\atolye\kitaplik.test.js"`
- araçlar: shell×9, read_file×3, list_dir×1, edit_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### z1-arama — SQLite kalıcılıklı not arama aracı

- **çalışır mı: 25.0/40**
  - `+ ara.py var (5p) — ara.py`
  - `+ ekle koşuyor (12p) — çıkış 0; Tamamlandi: 6 not indekslendi.`
  - `+ SQLite dosyası oluştu (8p) — notlar.db`
  - `- bul ayrı süreçte koşuyor (15p) — çıkış 1; Kullanim: py ara.py bul "kelime1 kelime2 ..."`
- **istenen kapsam: 7.0/25**
  - `- tek kelime doğru notu buluyor (8p) — «salmastra» → pompa-katalog bekleniyordu; çıktı: 'Kullanim: py ara.py bul "kelime1 kelime2 ..."\n\n'`
  - `- çok kelimede hepsi geçen not üstte (10p) — «rulman titresim» → kuyu-bakim yeri -1, pompa-katalog yeri -1`
  - `+ olmayan kelimede sonuç uydurmuyor (7p) — «helikopter» → çıktı: 'Kullanim: py ara.py bul "kelime1 kelime2 ..."\n\n'`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 15.0/15**
  - `+ testler yeşil (6p) — .............. [100%] 14 passed in 0.29s`
  - `~ test adedi (4.0/4p) — 14 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 2/2: ekle, bul`
  - `~ iddialar dolu (2.0/2p) — 18 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: cd /d "C:\Users\user\AppData\Local\Temp\neocp-eval-z1-arama-q62q1jds\atolye" && py -m pyte`; `shell: cd /d "C:\Users\user\AppData\Local\Temp\neocp-eval-z1-arama-q62q1jds\atolye" ; py -m pytes`; `shell: py -m pytest --version 2>&1`; `shell: py -c "print('test')" 2>&1`
- araçlar: shell×7, list_dir×2, write_file×2, read_file×2, edit_file×2, kos×1
- ! dış kapı: tur zaman aşımına uğradı
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 12

### z2-panel — Giriş korumalı mini yönetim paneli

- **çalışır mı: 40.0/40**
  - `+ index.php var (8p) — yonetimpaneli`
  - `! 8098 tutuluydu (ajan kendi sunucusunu açık bırakmış olabilir); ölçüm 8099 portunda yapıldı`
  - `+ sunucu ayağa kalkıyor (10p) — port açıldı`
  - `+ giriş sayfası açılıyor (10p) — 200, 2284 karakter; şifre alanı: True`
  - `+ doğru şifreyle içeri giriliyor (12p) — giriş POST → HTTP 200; ozet.php → HTTP 200`
- **istenen kapsam: 20.0/25**
  - `~ girişsiz erişim engelleniyor (7.0/7p) — ozet.php: engelli; kullanicilar.php: engelli; ayarlar.php: engelli`
  - `+ yanlış şifre reddediliyor (3p) — yanlış şifreden sonra ozet.php → HTTP 302`
  - `+ ozet.php giriş sonrası çalışıyor (5p) — 200, 5684 karakter`
  - `+ kullanicilar.php giriş sonrası çalışıyor (5p) — 200, 5490 karakter`
  - `- ayarlar.php giriş sonrası çalışıyor (5p) — 200, 7751 karakter — giriş formuna düşüyor`
- **kod sağlığı: 14.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 6/6 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (0.0/6p) — tekrar eden satır %31, 38 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- doğrulama izi: `browser: `; `shell: curl -s http://127.0.0.1:8098/ | head -30`; `shell: Invoke-WebRequest -Uri http://127.0.0.1:8098/ -UseBasicParsing | Select-Object -ExpandProp`; `shell: Start-Sleep -Seconds 2; Invoke-WebRequest -Uri http://127.0.0.1:8098/index.php -UseBasicPa`
- araçlar: shell×24, browser×15, write_file×6, list_dir×4, hand×2, screen×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 6

### z3-gizli-hata — Sepet modülündeki 3 gizli hatayı bul ve düzelt

- **çalışır mı: 40.0/40**
  - `+ sepet.py duruyor (6p) — sepet\sepet.py`
  - `+ modül import ediliyor (10p) — tamam`
  - `+ bozulmamış regresyon takımı koşuyor (8p) — ........ [100%] 8 passed in 0.02s`
  - `+ regresyon takımı tamamen yeşil (16p) — ........ [100%] 8 passed in 0.02s`
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
- doğrulama izi: `shell: cd atolye/sepet && py -m pytest`; `shell: cd atolye/sepet ; py -m pytest`; `shell: py -m pytest atolye/sepet`; `shell: py -m pytest atolye/sepet`
- araçlar: shell×9, task_status×3, read_file×2, list_dir×1, edit_file×1
- ! dış kapı: tur zaman aşımına uğradı
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7
