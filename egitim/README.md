# egitim — taban yazıcının eğitim düzeneği

neo'nun sorgu-yeniden-yazıcısının **genel tabanı**: kullanıcı sorusuna bakıp
aramaya eklenecek eş anlamlı / kısaltma / zamir-çözümü terimleri üreten
~10.8M parametrelik bayt-düzeyi model. Ürün tarafında saf numpy ile CPU'da
milisaniyelerde koşar (`src/neocp/assets/taban.npz`); kişisel ince ayar her
kullanıcının makinesinde bu tabanın üstüne gecelik yapılır ("Beni tanı").

## Akış

```
01_soru_uret.py    soru üretimi (öğretmen LLM, paralel, sürdürülebilir)
02_etiketle.py     öğretmen etiketleri (20 soru/istek, süzgeçli; susma sınıfı bedava)
04_egit.py         GPU'da eğitim (bf16, checkpoint)
05_disari_aktar.py → out/taban.npz + torch↔numpy eşitlik denetimi
06_sinav.py        kabul sınavı: neo'nun ölçek benchmark'ında mevcut sisteme karşı
07_en_yoklama.py   İngilizce yoklama
08_kisisel_dongu.py gecelik kişisel ince ayar döngüsü (ürün tanima.py'den çağırır)
```

Ortak ayarlar ve öğretmen-API bütçe bekçisi `ayarlar.py` içinde.

## Kurulum notları

* `anahtar.env` (satır: `OPENROUTER_API_KEY=...`), `veri/` ve `out/` git
  dışıdır — kendi anahtarınla oluşturursun.
* **Büyük dosyalar repoda yok.** Eğitilmiş checkpoint (`out/eniyi.pt`) ve
  korpuslar (`veri/korpus.jsonl`, `veri/korpus_en.jsonl`) GitHub
  **Releases** sayfasından indirilir ve bu klasördeki `out/` ile `veri/`
  altına konur. Sıfırdan üretmek istersen 01–02 betikleri korpusu, 04 ise
  checkpoint'i üretir.
* Ürünle dağıtılan hazır taban (`src/neocp/assets/taban.npz`) repodadır;
  eğitim düzeneği yalnızca yeni bir taban üretmek ya da kişisel ince ayar
  döngüsünü koşturmak isteyenler içindir.

## Kabul kapıları (ürünle dağıtılma şartı)

* Ölçek benchmark isabeti ≥ mevcut köprülü sistem, tuzak/boş sessizliğinde
  gerileme yok
* Susma örneklerinde model gerçekten susuyor (gevezelik cezası)
* CPU çıkarımı: tam genişletme p95 < 500 ms, erken susma < 50 ms
* İngilizce yoklama bir önceki modelin altına düşmez
* torch↔numpy eşitliği (fp16 paketleme payı içinde)

## Veri biçimi

`veri/korpus.jsonl` satırı:

```json
{"girdi": "bağlam?\n soru", "cikti": "terim …", "tur": "duz|zamir|susma"}
```

Susma sınıfının çıktısı her zaman boş: model susmayı da örnekten öğrenir.
