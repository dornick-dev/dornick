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

## İkinci bölüm: otomatik düzenek (27.08.2026)

Yukarıdaki matris elle puanlandı; bu ne ölçeklenir ne de bir değişiklikten
sonra yeniden koşulabilir. O yüzden depoda yaşayan bir düzeneğe dönüştü:
[`eval/coding/`](../eval/coding/README.md). Python, Node ve PHP'de
kolay/orta/zor dokuz görev; her biri kendi geçici alanında, **boş bir
zihinle**, kendi neo örneğiyle, dış kapıdan sürülüyor. Sonra puanlayıcı
atölyeye girip **kodu çalıştırıyor** — modülü import ediyor, sunucuyu
kaldırıyor, uca POST atıyor, panele giriş yapıyor.

İki kural sayıyı dürüst tutuyor:

- **Ölçülemeyen eksen paydadan düşer** — yoksa "ölçemedim" ile "başarısız"
  aynı sayıya iner.
- **`çalışır` ekseni yoksa puan da yok.** Bu kural bir hatadan doğdu: bir
  görev, iki taşıyıcı ekseni hiç ölçülmemişken 100.0 almıştı.

### Taban ölçüm — `minimax/minimax-m2.7`, 9 görevin hepsi

| görev | zorluk | çalışır (40) | kapsam (25) | sağlık (20) | test (15) | **puan** |
|---|---|---|---|---|---|---|
| k1-modul | kolay/py | 40.0 | 15.0 | 20.0 | 9.0 | **84.0** |
| k2-cli | kolay/node | 40.0 | 25.0 | 20.0 | — | **100.0** |
| k3-tamir | kolay/php | 40.0 | 25.0 | 20.0 | — | **100.0** |
| o1-rapor | orta/py | 40.0 | 25.0 | 20.0 | — | **100.0** |
| o2-servis | orta/py | 40.0 | 25.0 | 18.7 | 9.0 | **92.7** |
| o3-ozellik | orta/node | 40.0 | 25.0 | 20.0 | — | **100.0** |
| z1-arama | zor/py | 25.0 | 7.0 | 20.0 | 15.0 | **67.0** |
| z2-panel | zor/php | 40.0 | 20.0 | 14.0 | — | **87.1** |
| z3-gizli-hata | zor/py | 40.0 | 25.0 | 20.0 | — | **100.0** |

**Ortalama 92.3/100.** (`—` = istem test istemedi: ölçüldü, raporlandı,
puana katılmadı.)

### Davranış sütunları ne diyor — puandan çok şey söylüyorlar

**1. Yeşil test, çalışan ürün demek değil.** Bütün setin en keskin sonucu
`z1-arama`. Ajan 14 test yazdı, hepsi geçti, 18 iddia, hiçbiri bedava değil —
kod sağlığı 20/20. Ve istemin asıl istediği komut satırı **çalışmıyor**:
`py ara.py bul "salmastra"` her sorguda kendi kullanım satırını basıp 1 ile
çıkıyor. Testler iç fonksiyonları kapsamış; kullanıcının yazacağı giriş
noktasına hiç dokunulmamış. Ajan kendini doğruladı ve tatmin oldu.

Bu bulgu önemli, çünkü akla ilk gelen çözümü aşıyor: kırmızı takımda turu
kapatmayı reddeden bir kapı burada hiçbir şey yapmaz — takım yeşildi. Bunu
yakalayan tek şey, teslim edilen şeyi kullanıcının çalıştıracağı gibi
çalıştırmak; puanlayıcının yaptığı, ajanın yapmadığı şey de tam bu.

**2. Dokuz turun üçü hiç bitmedi.** `o2-servis`, `z1-arama` ve
`z3-gizli-hata` 900 saniyelik tavana çarptı; o satırlardaki puan, süre
dolduğunda atölyede ne kaldıysa onu ölçüyor — aşağı yönlü sapmalı. Üçü de
orta/zor uçta: ajan zor işi on beş dakikada toparlayamıyor.

**3. İki kez kırmızı testle teslim, bir kez bile plan yok.** `k1-modul` beş
geçerli girdinin beşini de reddeden bir modülü kendi takımı `FFFFF`
gösterirken teslim etti; `o2-servis` sekiz testin biri başarısızken. İkisinde
de ajan takımı koştu, kırmızıyı gördü, bitti dedi. Dokuz görevin hepsinde
plan yazma sayısı **sıfır** — sistem promptu çok dosyalı işte plan istiyor ve
bu öğüt tek bir görevle temasta bile yaşamadı.

Ayrıca: `z2-panel` %31 tekrar eden satır ve 38 yinelenen blokla geldi, ve dört
sayfasından biri **başarılı** girişten sonra sessizce giriş formuna düşüyor —
"200 dönüyor mu?" denetimi buna yeşil derdi. Bir de dokuz görevde 39 hatalı
araç çağrısı, yani çağrıların yaklaşık onda biri.

3. numaralı bulgu, sonraki dalganın prompt öğüdünü **harness refleksine**
çevirmesinin sebebi: döngünün rica etmek yerine kendi attığı bir plan adımı ve
kırmızı takımda turu kapatmayı reddeden bir bitiş kapısı. Yukarıdaki tablo
bilerek saklanan **öncesi** ölçümüdür. 1. numaralı bulgu ise henüz
karşılıksız — bu dosyadaki en değerli açık problem.

### Bu düzenek hakkında dürüstlük

Görev başına tek koşu; ±5 puan gürültü, ancak >15 puanlık oynama anlamlı.
Her koşu boş zihinle başlıyor, yani bu ölçüm kodlama boru hattını ölçüyor —
hafızanın kodlamaya katkısını **değil**. Üretilen raporda `†` işaretli
satırlar aynı günün önceki koşusundan devralınmıştır; hepsi aynı yapıdan.

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
