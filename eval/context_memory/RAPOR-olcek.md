# Ölçek Raporu — 100 anı + 60 episode altında önyükleme (26.08.2026)

Soru (Fatih): *"Yanlış şeyler hatırlıyor muyuz? Context tasarrufu yapıyor
muyuz? Daha iyi yöntem var mı?"* Düzenek: `scale_bench.py` + donmuş korpus
`scale_dataset.json` (100 anı / 8 alan, 60 episode, 70 altın-etiketli sorgu).
Ölçülen yol ürünün kendisi — `loop.select_prime` doğrudan çağrılıyor ve
parametrik kopyanın ürüne eşitliği her koşuda doğrulanıyor.

## 1. Cevaplar, kısa

**Yanlış hatırlıyor muyuz?** Evet — tuzak sorguların yalnız üçte biri sessiz
kalıyor. "Yarın Konya'da hava nasıl?" → yarı-maraton hedefi + çay tercihi;
"Konyaspor maçı kaç kaç?" → eş bilgisi. Fatih'in tarif ettiği sınıf birebir
üretildi. İkinci savunma hattı var (not başlığı "ilgisizse yoksay" diyor) ama
token yine yanıyor.

**Tasarruf var mı?** Var ve büyük: bütün anıları her turda göndermek ~3.093
tok/sorgu olurdu; seçici önyükleme **118 tok/sorgu** (%96 tasarruf). Bu tur
eklenen dört iyileştirme bunun üstüne: aşağıda.

**Daha iyi yöntem?** On bir varyant ölçüldü. Bir tanesi mevcut yapıyı **katı
biçimde domine etti** ve ürüne alındı (ruh-dışlama). Kapı sıkılaştıran diğer
hepsi isabetten çalıyor — sözcüksel sinyaller tavanda (§4).

## 2. Sonuç tablosu

isabet = altınlı sorguda ≥1 altın gelmesi (ruhta duran altın "bağlamda"
sayılır — tüm yöntemlere adil). sessizlik = altınsız sorguda hiç enjeksiyon
olmaması. verim = isabet × 1000 / tok.

| yöntem | isabet | kesinlik | sessizlik | tok/sorgu | verim |
|---|---|---|---|---|---|
| ciplak (kapısız ablasyon) | 0.87 | 0.20 | 0.31 | 180 | 4.8 |
| **mevcut** (üründeki kapılar) | 0.87 | 0.31 | 0.50 | 129 | 6.7 |
| **ruhdisi → KABUL** | **0.87** | 0.32 | 0.50 | **118** | **7.4** |
| kisa120 (satır 220→120) | 0.87 | 0.31 | 0.50 | 120 | 7.2 |
| gap45 (kuyruk kesme) | 0.87 | 0.31 | 0.50 | 129 | 6.7 |
| kademe (çift kanıt öncelikli) | 0.81 | 0.58 | 0.50 | 77 | 10.5 |
| carpim16/20/24 (skor×oran eşiği) | 0.81→0.74 | 0.50→0.70 | 0.56→0.81 | 91→56 | 9→13 |
| zemin2 (≥2 kanıt şartı) | 0.76 | 0.71 | 0.81 | 57 | 13.3 |
| oran40 (≥%40 kanıt) | 0.67 | 0.82 | 0.88 | 39 | 17.3 |

Tür kırılımında görünen asıl hikâye: sıkı kapıların kazandırdığı trap
sessizliği (0.33→0.75), **devam sorgularından** (0.88→0.50) ve
**paraphrase'den** (0.70→0.50) çalınıyor. Fatih'in çekirdek senaryosu
"önceki projeye mi devam edecek" tam da devam sınıfı — feda edilemez.
`gap45` hiçbir şeyi değiştirmiyor (kuyruk zaten tabanda kesiliyor);
`kisa120` token kazanıyor ama 120 harf kayıtların kilit değerini (register
adresi gibi) ortadan kesebiliyor — id-bazlı metrik bu kaybı göremez, ilkece
reddedildi.

## 3. Ürüne giren iyileştirmeler (bu tur)

1. **Oturum-içi tekrar yok** — aynı hatıra bir kez enjekte edilir; eski not
   geçmişte zaten duruyor. 12 turluk tek-konu konuşmada **%20 tasarruf**
   (2.109→1.680 tok); uzun oturumda birikerek büyür. Sıkıştırmada hak döner.
2. **Ruh-dışlama (`ruhdisi`)** — ruhun tam gövdeyle prompta koyduğu kayıtlar
   (user/preference/lesson/voice) önyüklemeye giremez: bilgi zaten bağlamda.
   Aynı isabet, **−%9 token**; "hava" sorusuna sızan çay-tercihi türü
   kayıtların bir kısmı kendiliğinden susuyor. Yordamlar hariç (ruhta yalnız
   başlıkları var).
3. **Not biçimi** — tür bir kez yazılıyor (eskiden `- [fact] (fact) …`),
   otomatik başlıkta başlık/gövde tekrarı atlanıyor, etiketler girmiyor.
4. **`mind_recall` gövde sınırı 700 harf** — tek bir episode isabeti
   (sıkıştırma özeti 8.000 harfe kadar) binlerce token yiyebiliyordu;
   kırpılan kayıp değil, cevap "sorguyu daralt" diyor.

Donmuş dev/holdout kapısı değişmedi (dev 5/5 GEÇTİ; holdout 0.840 — bilinen
sinonim tavanı, dokunulmadı). 614 test yeşil.

## 4. Teşhis: tavan nerede, neden

* Ham skor **doymuş**: altın medyan 0.963, sızıntı 0.874 — eşik ayıramaz.
* Skor × kanıt-oranı kısmen ayırıyor (0.477 vs 0.167) ama eşiği trap'i
  susturacak kadar yükseltmek paraphrase/devam sorgularını da susturuyor —
  ikisi sözcüksel olarak **aynı görünüyor** (havuzdaki en iyi adayın kanıt
  oranı: altınlı p25=0.25, trap p25=0.25 — tam örtüşme).
* Sonuç: kelime/n-gram/IDF ailesinden hiçbir kapı "hava→borsa" sınıfını,
  "projeye devam"ı öldürmeden kapatamaz. Bu, 25.08 araştırma döngüsünün
  sinonim tavanıyla aynı duvar.

**Duvarı aşan ilk adım — SİNONİM KÖPRÜSÜ (aynı gece eklendi ve ölçüldü):**
`recall/bridge.py` — ~50 genel eş anlam grubu (kripto kısaltmaları,
endüstri, BT'nin EN↔TR sözlüğü, gündelik Türkçe), yalnız sorgu tarafında
açılır (kayıt yazıldığı gibi durur, indeks yeniden kurulmaz), ekli biçimler
önekle yakalanır, kısa anahtarlarda tam eşleşme şartı ("işlem"→"iş" kazası
yok). Hile kuralına sadık: tablo eval'e bakılarak değil kategori geneli
yazıldı ve TEK ATIŞTA ölçüldü:

| ölçüm | önce | sonra |
|---|---|---|
| dev recall@3 / paraphrase | 0.967 / 0.900 | **1.000 / 1.000** |
| mühürlü holdout recall@3 | 0.840 | **0.920** |
| holdout paraphrase (kapı >0.80) | 0.733 ✗ | **0.867 ✓** |
| holdout boş-dönüş | 0.938 | 0.938 (korundu) |
| ölçek: tuzak/boş/isabet/token | 0.33 / 1.00 / 0.87 / 129 | 0.33 / 1.00 / 0.87 / 132 (**regresyon yok**) |

Kalan 2 holdout kaçışı gerçek-eşanlamlı olmayan çiftler (iş↔mühendis türü) —
bunlar bilerek tabloya konmadı; genel bir tablo onları çözemez, çözmeye
çalışmak eval'e tablo yazmaktır.

## 4b. "Hepsini dene" turu — kalan yöntemler (26.08 sabaha karşı)

| deney | sonuç | karar |
|---|---|---|
| IDF ağırlıklı kanıt (idf16/24/32) | düz-oran ailesiyle AYNI takas eğrisi; yeni Pareto noktası yok | RET — önceki döngünün "IDF'e değmez" kararı ölçekte doğrulandı |
| Sayı-koruma (sayı-ağırlıklı sorguda sayıları atma) | hiçbir metrik kıpırdamadı (numeric kaçışı sayı-atmadan değilmiş) | RET — mevcut sayı-atma doğru |
| Kırpma 220→160 | token −%0.6 (gövdeler zaten kısa, kırpma nadiren biniyor) | RET |
| **LLM sorgu-yeniden-yazıcı (tavan ölçümü)** | isabet 0.87→**0.94**; sinonim 0.50→**1.00** (tam çözüm), paraphrase 0.70→0.90; trap 0.42; token +%5; bir "boş" sorguda kural delindi (empty 0.88) | ürüne GİRMEDİ — her mesaja +1 model çağrısı (~0.5-1 sn) prime'ın "ek tur yok" ilkesini bozar. Ölçüm, plandaki **küçük yerel yeniden-yazıcının** getiri kanıtı: +7 puan garantili tavan |

LLM deneyi tekrar üretilebilir: genişletmeler `llm_rewrites.json`
(gemini-2.5-flash-lite, temperature 0, 70 sorgu ~48 sn). Sıradaki gerçek
adım değişmedi: yerel küçük yeniden-yazıcı (zamir/eksilti + sinonim, ~5M
param, loglardan bedava eğitim verisi) — "olgular indekste, örüntü
ağırlıkta" ilkesiyle uyumlu; embedding bu ölçekte hâlâ erken.

## 5. Tekrar üretim

```
py eval/context_memory/scale_bench.py     # tablo + sızıntı örnekleri
py eval/context_memory/harness.py         # donmuş dev/holdout kapısı
```
Son koşu çıktısı: `son_kosu.txt`. Korpus donmuş; sorgular değişirse bu
rapor geçersizdir (yeni korpus = yeni rapor).
