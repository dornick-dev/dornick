# Kodlama Ölçüm Raporu

**Koşu:** 20260828T192350Z · **Model:** `z-ai/glm-5.3-flash` · **Tekrar:** 1 · **Düzenek:** `eval/coding/` (dış kapı + izole örnek)

Puan dört eksenden: **çalışır mı** 40 · **istenen kapsam** 25 · **kod sağlığı** 20 · **test kalitesi** 15. Bir eksen ölçülemediyse paydadan da düşer; istem o işi istemiyorsa (*istenmedi*) ölçülür ama puana katılmaz. Puan sütunu 100'e normalize edilmiş haldir.

## Puan kırılımı

| görev | zorluk | dil | çalışır (40) | kapsam (25) | sağlık (20) | test (15) | **puan** |
|---|---|---|---|---|---|---|---|
| z2-panel | zor | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |
| z3-gizli-hata | zor | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |

`*` = istem bu işi istemedi; ölçüldü, raporlanıyor, puana katılmıyor.

## Davranış ölçütleri (puana katılmaz)

| görev | tur bitti | araç çağrısı | hatalı araç | süre sn | token (giren/çıkan) | maliyet $ | kendini doğruladı | plan yazdı | bozuk teslim |
|---|---|---|---|---|---|---|---|---|---|
| z2-panel | evet | 11 | 2 | 103.1 | 138471/3618 | 0.0113 | evet | hayır | 0/1 |
| z3-gizli-hata | evet | 9 | 3 | 65.6 | 145612/673 | 0.0111 | evet | hayır | 0/1 |

**Ortalama puan:** 100.0/100 (2 görev ölçüldü)

**Koşulmadı:** k1-modul, k2-cli, k3-tamir, o1-rapor, o2-servis, o3-ozellik, z1-arama

## Bu sayılar ne kadar sağlam?

**Tek koşu gürültüdür.** Buradaki her puan tek atıştan geliyor; aynı görev aynı modelle yeniden koşulduğunda birkaç puan oynayabilir, bazı görevlerde (araç hatası, zaman aşımı) çok daha fazla. Bir iyileştirmenin işe yaradığını söylemek için `--tekrar 3` ile koşup ± aralığına bakmak gerekiyor. Tek koşudaki büyük fark (>15 puan) anlamlı, küçük fark (<5 puan) gürültüden ayırt edilemez.

İzolasyon: her koşu kendi geçici çalışma alanında, **boş bir zihinle** ve kendi neo örneğiyle yapıldı. Kullanıcının anıları taşınmıyor — yani bu düzenek kodlama boru hattını ölçüyor, hafızanın kodlamaya katkısını ölçmüyor.

## Kanıt dökümü

### z2-panel — Giriş korumalı mini yönetim paneli

- **çalışır mı: 40.0/40**
  - `+ index.php var (8p) — panel`
  - `! 8098 tutuluydu (ajan kendi sunucusunu açık bırakmış olabilir); ölçüm 8099 portunda yapıldı`
  - `+ sunucu ayağa kalkıyor (10p) — port açıldı`
  - `+ giriş sayfası açılıyor (10p) — 200, 824 karakter; şifre alanı: True`
  - `+ doğru şifreyle içeri giriliyor (12p) — giriş POST → HTTP 200; ozet.php → HTTP 200`
- **istenen kapsam: 25.0/25**
  - `~ girişsiz erişim engelleniyor (7.0/7p) — ozet.php: engelli; kullanicilar.php: engelli; ayarlar.php: engelli`
  - `+ yanlış şifre reddediliyor (3p) — yanlış şifreden sonra ozet.php → HTTP 302`
  - `+ ozet.php giriş sonrası çalışıyor (5p) — 200, 771 karakter`
  - `+ kullanicilar.php giriş sonrası çalışıyor (5p) — 200, 982 karakter`
  - `+ ayarlar.php giriş sonrası çalışıyor (5p) — 200, 1005 karakter`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 6/6 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- doğrulama izi: `browser: `; `shell: $jar = "$env:TEMP\pnut.jar"; "1) korumasız erişim: " + (curl.exe -s -o NUL -w "%{http_code`; `shell: $jar = "$env:TEMP\pnut.jar"; curl.exe -s -c $jar -d "kullanici=admin&sifre=yanlis" http://`
- araçlar: write_file×6, shell×4, browser×1
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
- doğrulama izi: `shell: py -m pytest atolye/sepet -x -q`; `shell: py -m pytest sepet -q`; `shell: py -m pytest sepet -q`; `shell: py -m pytest sepet -q`
- araçlar: shell×4, list_dir×2, edit_file×2, read_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8
