# Kodlama Ölçüm Raporu

**Koşu:** 20260828T163730Z · **Model:** `z-ai/glm-5.3-flash` · **Tekrar:** 1 · **Düzenek:** `eval/coding/` (dış kapı + izole örnek)

Puan dört eksenden: **çalışır mı** 40 · **istenen kapsam** 25 · **kod sağlığı** 20 · **test kalitesi** 15. Bir eksen ölçülemediyse paydadan da düşer; istem o işi istemiyorsa (*istenmedi*) ölçülür ama puana katılmaz. Puan sütunu 100'e normalize edilmiş haldir.

## Puan kırılımı

| görev | zorluk | dil | çalışır (40) | kapsam (25) | sağlık (20) | test (15) | **puan** |
|---|---|---|---|---|---|---|---|
| k2-cli | kolay | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |
| o1-rapor | orta | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** |
| z1-arama | zor | python | 40.0 | 25.0 | 20.0 | 15.0 | **100.0** |

`*` = istem bu işi istemedi; ölçüldü, raporlanıyor, puana katılmıyor.

## Davranış ölçütleri (puana katılmaz)

| görev | tur bitti | araç çağrısı | hatalı araç | süre sn | token (giren/çıkan) | maliyet $ | kendini doğruladı | plan yazdı | bozuk teslim |
|---|---|---|---|---|---|---|---|---|---|
| k2-cli | evet | 2 | 0 | 51.6 | 46759/778 | 0.0037 | hayır | hayır | 0/1 |
| o1-rapor | evet | 4 | 0 | 35.3 | 63941/734 | 0.0050 | hayır | hayır | 0/1 |
| z1-arama | evet | 14 | 4 | 175.7 | 248122/4216 | 0.0197 | evet | hayır | 0/1 |

**Ortalama puan:** 100.0/100 (3 görev ölçüldü)

**Koşulmadı:** k1-modul, k3-tamir, o2-servis, o3-ozellik, z2-panel, z3-gizli-hata

## Bu sayılar ne kadar sağlam?

**Tek koşu gürültüdür.** Buradaki her puan tek atıştan geliyor; aynı görev aynı modelle yeniden koşulduğunda birkaç puan oynayabilir, bazı görevlerde (araç hatası, zaman aşımı) çok daha fazla. Bir iyileştirmenin işe yaradığını söylemek için `--tekrar 3` ile koşup ± aralığına bakmak gerekiyor. Tek koşudaki büyük fark (>15 puan) anlamlı, küçük fark (<5 puan) gürültüden ayırt edilemez.

İzolasyon: her koşu kendi geçici çalışma alanında, **boş bir zihinle** ve kendi neo örneğiyle yapıldı. Kullanıcının anıları taşınmıyor — yani bu düzenek kodlama boru hattını ölçüyor, hafızanın kodlamaya katkısını ölçmüyor.

## Kanıt dökümü

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
  - `+ gorevler.json'da kalıcı (7p) — gorevler.json, 109 karakter`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 1/1 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 0.0/15** *(istenmedi)*
  - `- test dosyası yok (0p)`
- araçlar: write_file×1, shell×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 7

### o1-rapor — CSV satış raporu + CLI

- **çalışır mı: 40.0/40**
  - `+ rapor.py var (8p) — rapor.py`
  - `+ csv ile koşuyor (16p) — çıkış 0; 2026-01 Toplam ciro: 47553.25 Pompa 25197.00 Sensor 12159.05 PLC 8249.70 2026-02 Toplam ciro: 33938.45 Sensor 17278.65 Pompa 8399.00 PLC 5499.80 2026-03 Toplam `
  - `+ çıktı boş değil (8p) — 310 karakter`
  - `+ --ay koşuyor (8p) — çıkış 0; 2026-03 Toplam ciro: 99286.90 Pompa 54593.50 PLC 30248.90 Sensor 12799.00`
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
- araçlar: shell×2, read_file×1, write_file×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 8

### z1-arama — SQLite kalıcılıklı not arama aracı

- **çalışır mı: 40.0/40**
  - `+ ara.py var (5p) — ara.py`
  - `+ ekle koşuyor (12p) — çıkış 0; 0 dosya indekslendi, 9 not indeks içinde.`
  - `+ SQLite dosyası oluştu (8p) — notlar.db`
  - `+ bul ayrı süreçte koşuyor (15p) — çıkış 0; 2 eşleşme: [skor 2] salmastra.txt Hidrolik silindir salmastra seti 40mm, yaylı keçe kullanılıyor. [skor 1] pompa-katalog.txt …, debi 12 m3/saat. Yedek parca: ru`
- **istenen kapsam: 25.0/25**
  - `+ tek kelime doğru notu buluyor (8p) — «salmastra» → pompa-katalog bekleniyordu; çıktı: '2 eşleşme:\n\n[skor 2] salmastra.txt\n  Hidrolik silindir salmastra seti 40mm, yaylı keçe kullanılıyor.\n\n[skor 1] pompa-kat'`
  - `+ çok kelimede hepsi geçen not üstte (10p) — «rulman titresim» → kuyu-bakim yeri 97, pompa-katalog yeri 213`
  - `+ olmayan kelimede sonuç uydurmuyor (7p) — «helikopter» → çıktı: '"helikopter" için hiçbir notta eşleşme bulunamadı.\n\n'`
- **kod sağlığı: 20.0/20**
  - `~ sözdizimi temiz (8.0/8p) — 2/2 dosya`
  - `~ boy/karmaşıklık (6.0/6p) — temiz`
  - `~ tekrar yok (6.0/6p) — tekrar eden satır %0, 0 yinelenen blok`
- **test kalitesi: 15.0/15**
  - `+ testler yeşil (6p) — ....... [100%] 7 passed in 0.75s`
  - `~ test adedi (4.0/4p) — 7 test bulundu`
  - `~ kritik yol kapsanıyor (3.0/3p) — 2/2: ekle, bul`
  - `~ iddialar dolu (2.0/2p) — 15 iddia, 0 tanesi bedava geçiyor`
- doğrulama izi: `shell: py -m pytest test_ara.py -v`; `shell: py -m pytest test_ara.py -v`; `shell: py -m pytest test_ara.py -v`
- araçlar: edit_file×5, shell×4, write_file×2, read_file×2, kos×1
- ! ölçüm dışı (dokunulmamış tur öncesi dosya): 13
