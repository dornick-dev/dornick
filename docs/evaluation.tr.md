# neo kodlama değerlendirmesi (26-27.08.2026)

**Sorular:** neo'ya bir kodlama işi verirseniz ne olur? Sonucun ne kadarı
modelden, ne kadarı neo'nun kabuğundan (araçlar + test koşma + kendi
hatasını düzeltme) geliyor?

## Düzenek

neo'ya **dış kapıdan** (`POST /api/gate` — sohbete kullanıcı gibi yazan ve
tam çıktıyı döndüren API) üç görev verildi. neo her görevi kendi atölyesinde
yaptı: dosyaları yazdı, testleri kendisi çalıştırdı, kırmızı gördüğünde
düzeltti, bitirince raporladı. Her şey bağımsız denetlendi: bütün test
paketleri değerlendirici tarafından yeniden koşuldu, CSV'ler satır satır
sayıldı, CLI'lar elle çalıştırıldı.

| Görev | İçerik |
|---|---|
| Kolay | Türkçe-duyarlı metin istatistikleri + testler |
| Orta | CSV gider raporu üretici + CLI + testler |
| Zor | TF-IDF arama motoru + SQLite kalıcılık + CLI + 10+ test |

Tasarım bir **2×2 matris + referans noktası**: iki model
(`openai/gpt-5.6-luna` ve `anthropic/claude-fable-5`), her biri iki koşulda —
neo'nun kabuğu içinde ve çıplak API'den tek atış (araç yok, test koşma yok,
ikinci şans yok). Değerlendirici (Claude; claude-fable-5 + kendi kabuğu)
aynı görevleri referans olarak kendisi de çözdü.

Görev başına rubrik: Çalışırlık 40 · Kapsam 25 · Kod kalitesi 20 · Test 15.

## Sonuçlar — matris

| | neo'nun kabuğu içinde | çıplak tek atış |
|---|---|---|
| **gpt-5.6-luna** | **294**/300 | 280/300 |
| **claude-fable-5** | **294**/300 | 261/300 |

Referans: değerlendirici (claude-fable-5 + kendi kabuğu) 289/300.

Görev kırılımı:

| Koşu | Kolay | Orta | Zor | Not |
|---|---|---|---|---|
| neo + luna | 97 | 98 | 99 | Para için `Decimal`; kosinüs TF-IDF |
| neo + fable | 98 | 97 | 99 | Toplam 33 test; "sonuç yok" mesajı; yumuşatılmış IDF |
| çıplak luna | 85 | 96 | 99 | **Türkçe harf hatasını teslim etti** (`casefold()`) |
| çıplak fable | 98 | 97 | **66** | **`UnboundLocalError` teslim etti** — 10 test + CLI çöktü |
| değerlendirici | 96 | 96 | 97 | İlk geçişte 2 test-beklentisi hatası; koşunca düzeltti |

## Matrisin söyledikleri

1. **Kabuk, modelleri eşitliyor.** neo'nun içinde iki model de tam 294/300'e
   oturdu — güçlü yanları farklı, tavanları aynı. Çıplakken 19 puan
   ayrıştılar ve *ikisi de birer görevde bozuk kod teslim etti*: luna Türkçe
   I/İ tuzağına düştü, fable beş dosyalık projede bir değişken adını yanlış
   yazıp 10 testi ve CLI'yi birden götürdü. İkisi de kendi hatasını
   göremedi — çünkü hiçbir şey koşturamıyorlardı.
2. **Yaz-koş-yakala-düzelt döngüsü ürünün ta kendisi.** Aynı modeller
   neo'nun içinde de ilk geçiş hataları yaptı — sonra testleri koşup
   yakaladı ve raporlamadan önce düzeltti. Değerlendiricinin kendi iki
   test-beklentisi hatası da aynı yolla yakalandı; simetri tam.
3. **Bu görev ölçeğinde kabuk seçimi model seçiminden daha çok şey
   değiştirdi.** Model değişimi çıplak skoru 19 puan oynattı; kabuğun
   varlığı fable'ın skorunu 33 puan oynattı.

## Bu değerlendirmenin yakaladığı hata

Fable'ın neo içindeki ilk denemesi anında düştü: Anthropic API'si `system`
rolünü yalnız mesaj dizisinin başında kabul ediyor, neo ise tur ortasına
sistem notları (hedef senkronu, harness notları) ekliyor. Her istek 400
döndü — "modelden bağımsız" iddiasında, bir Claude modeli fiilen seçilene
dek görünmez kalan gerçek bir gedik. `backends/translate.py`'de düzeltildi
(tur ortası sistem notları artık etiketli user-notu olarak gidiyor; her
sağlayıcıda geçerli), gerileme testiyle. Gerçek yolları çalıştıran
değerlendirmeler gerçek hataları buluyor.

## Dürüstlük notları

- Hücre başına tek koşu, tek değerlendirici; ±2 puan gürültü sayılmalı.
  Çıplak fable'ın 66'sı tek şanssız değişken adı — başka örneklemde başka
  yere düşebilir; tek atışın kırılganlığı hakkındaki nokta da tam bu.
- Fable-neo koşusu luna koşularından sonra yapıldı; neo'nun hafızasında
  önceki sınava dair anılar vardı. Önceki çözüm klasörleri koşudan önce
  kaldırıldı (kopya imkânsız) ve araç izleri işin sıfırdan yapıldığını
  gösteriyor; yine de hafif aşinalık etkisi dışlanamaz.
- Çıplak koşular sınırlandırılmış akıl yürütmeyle yapıldı (fable akıl
  yürütmesiz çalışmayı kabul etmiyor; 3.000 token tavan) ve modele dosya
  biçimi tarif edildi; değerlendirici dosyaları mekanik olarak çıkardı.
- Görev istemleri ve puanlama koşularla aynı gün yazıldı; görevler herhangi
  bir eğitim setinde birebir bulunmayacak kadar yereldir.
