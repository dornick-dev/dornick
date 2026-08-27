# Kodlama ölçümü

neo'nun "vibe coding" tarafını ölçen düzenek. Soru şu değil: *model ne kadar
akıllı?* Soru şu: **neo'nun içinde koşan bir model, çalışan bir iş teslim
ediyor mu?**

Ölçüm tümüyle otomatik: her görev kendi geçici çalışma alanında, **boş bir
zihinle**, kendi neo örneğiyle koşuyor. Ajan işi bitirince puanlayıcı
atölyeye girip yazılan kodu **gerçekten çalıştırıyor** — dosya var mı diye
bakmakla yetinmiyor.

## Koşmak

```bash
py eval/coding/kosucu.py --gorev hepsi --tekrar 1
```

| bayrak | ne yapar |
|---|---|
| `--gorev` | `hepsi`, ya da virgülle: `k1-modul,z2-panel` |
| `--zorluk` | `kolay` / `orta` / `zor` süzgeci |
| `--model` | modeli bu koşu için değiştirir (varsayılan: yapılandırmadaki) |
| `--tekrar` | aynı görevi N kez koşar — tek koşu gürültüdür, karşılaştırma için 3 |
| `--bekle` | görev başına azami saniye (varsayılan 900) |
| `--onceki` | eksik görevleri eski bir koşudan devralır; rapor devralınanı `†` ile işaretler |
| `--sakla` | çalışma alanını silmez (kanıta elle bakmak için) |

Sonuç `sonuclar/<zaman>-<model>.json` ve okunur haliyle `sonuclar/RAPOR.md`.

## Puan nasıl çıkıyor

Dört eksen: **çalışır mı** 40 · **istenen kapsam** 25 · **kod sağlığı** 20 ·
**test kalitesi** 15.

İki kural puanı dürüst tutuyor:

- **Ölçülemeyen eksen paydadan da düşer.** Bir eksen hiç ölçülemediyse (araç
  yok, süreç kalkmadı) o eksen 0 yazılmaz — bölüme hiç girmez. Aksi hâlde
  "ölçemedim" ile "başarısız" aynı sayıya düşerdi.
- **`çalışır` ölçülemediyse puan yoktur.** Kodun koşup koşmadığı bilinmiyorsa
  geri kalanı puanlamak anlamsız; o satır `ölçülemedi` olarak raporlanır.
  (Bu kural bir hatadan doğdu: bir görev, iki taşıyıcı ekseni hiç ölçülmemişken
  100.0 almıştı.)

`istenmedi` işareti üçüncü bir durum: istem test yazmayı istemiyorsa test
ekseni ölçülür, raporlanır, ama puana katılmaz.

## Davranış ölçütleri

Puana katılmayan ama daha çok şey anlatan sütunlar: tur bitti mi, kaç araç
çağrıldı, kaçı hatalıydı, ajan işini **kendi doğruladı mı**, plan yazdı mı,
bozuk teslim var mı. Bir düzeltmenin işe yarayıp yaramadığı çoğu zaman
puanda değil burada görünüyor.

## Dosyalar

| dosya | işi |
|---|---|
| `kosucu.py` | koşuyu yönetir: alan hazırlar, neo'yu başlatır, dış kapıdan sorar, puanlatır |
| `ornek.py` | izole bir neo örneği ayağa kaldırır (kendi `.neocp`'si, kendi portu) |
| `puanla.py` | eksen/ölçüt altyapısı ve rapor üretimi |
| `davranis.py` | davranış ölçütlerini olay günlüğünden çıkarır |
| `gorevler/<ad>/gorev.md` | ajana verilen istem |
| `gorevler/<ad>/olcut.py` | o görevin ölçütleri — kodu çalıştıran taraf |
| `gorevler/<ad>/tohum/` | varsa başlangıç dosyaları (onarılacak hata, mevcut testler) |

Yeni görev eklemek: `gorevler/` altına bir klasör, içine `gorev.md` ve
`olcut.py`. Kosucu klasörü kendi buluyor.
