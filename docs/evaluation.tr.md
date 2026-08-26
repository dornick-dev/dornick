# neo kodlama değerlendirmesi (26.08.2026)

**Soru:** neo'ya bir kodlama işi verirseniz ne olur — ve neo'nun kabuğu
(araçlar + test koşma + kendi hatasını düzeltme) gerçekten fark yaratıyor mu?

## Düzenek

neo'ya **dış kapıdan** (`POST /api/gate` — sohbete kullanıcı gibi yazan API)
üç görev verildi. neo her görevi kendi atölyesinde yaptı: dosyaları yazdı,
testleri kendisi çalıştırdı, kırmızı gördüğünde düzeltti, bitirince raporladı.
Bütün çıktılar bağımsız denetlendi: 30 test yeniden koşuldu, CSV satır satır
sayıldı, CLI'lar elle çalıştırıldı.

| Görev | İçerik | neo'nun süresi |
|---|---|---|
| Kolay | Türkçe-duyarlı metin istatistikleri + testler | 76 sn |
| Orta | CSV gider raporu üretici + CLI + testler | 90 sn |
| Zor | TF-IDF arama motoru + SQLite kalıcılık + CLI + 10+ test | 99 sn |

İki karşılaştırma yapıldı:

1. **Sistem kıyası:** aynı görevleri değerlendirici (Claude, kendi modeliyle)
   de çözdü. Bu, iki farklı sistemin kıyasıdır — modeller farklıdır.
2. **Adil deney (aynı model):** neo'nun o günkü modeli
   (`openrouter/gpt-5.6-luna`) bir de **çıplak API'den tek atışla** denendi —
   araç yok, test koşma yok, düzeltme şansı yok. Aradaki fark modelin değil,
   neo'nun kabuğunun katkısıdır.

Rubrik: Çalışırlık 40 · Kapsam 25 · Kod kalitesi 20 · Test kalitesi 15 = 100.

## Sonuçlar

| | Kolay | Orta | Zor | Toplam |
|---|---|---|---|---|
| **neo** (luna, kabuk içinde) | 97 | 98 | 99 | **294/300** |
| Claude (değerlendirici, kendi modeli) | 96 | 96 | 97 | 289/300 |
| Aynı model, çıplak tek atış | 85 | 96 | 99 | 280/300 |

Öne çıkanlar:

- **neo'nun kod kalitesi değerlendiricisiyle baş başa** — yer yer önde:
  para hesabında `Decimal`, arama motorunda kosinüs normalizasyonlu
  yumuşatılmış TF-IDF gibi ders kitabı tercihler neo'dan geldi.
- **Kabuğun kanıtı, kolay görevde:** çıplak model `casefold()` kullanıp
  Türkçe I/İ tuzağına düştü ve **bozuk kodu teslim etti** (kendi test paketi
  1 kırmızı; testi doğru yazmıştı ama koşamadığı için göremedi). Aynı model
  neo'nun içinde de ilk geçişte hata yaptı — farkla ki **testi koşup hatayı
  yakaladı ve düzeltti**. Aynı model, kabuk içinde +14 puan ve sıfır bozuk
  teslimat.
- **Simetrik insan payı:** değerlendirici de ilk geçişte iki test
  beklentisini yanlış kurdu (Türkçe alfabe sırası) ve koşunca düzeltti.
  Yaz-koş-yakala-düzelt döngüsü her tarafta işledi; ölçülen şey tam da bu
  döngünün değeriydi.

## Dürüstlük notları

- Puanlar tek koşuluk, tek değerlendirici görüşüdür; ±2 fark gürültü
  sayılmalıdır.
- İlk kıyasta modeller farklıdır (bilinçli: "neo sistemi vs değerlendirici
  sistemi"); aynı-model deneyi bu açığı kapatmak için eklendi.
- Görev istemleri ve puanlama bu depodaki koşuyla aynı gün yazıldı; görevler
  modellerin eğitim verisinde birebir bulunmayacak kadar yereldir (Türkçe
  şartlar, atölye düzeni).
