# Uyku basıncı gerçek depoda (`pressure-real-store`)

*2026-09-07 · 1.5.10 · ölçüm: sahibin gerçek kurulumu (`%LOCALAPPDATA%\Dornick\.dornick\mind\recall.db`, kopya üzerinde; canlı dosyaya yazılmadı) · bench: `eval/context_memory/life_bench.py --watchman` ve `--threshold-curve`*

Bu sayfa tek soruya cevap veriyor: **panelin basınç çubuğu neden hep %100'de
duruyordu ve şimdi ne okuyor?** Önce ölçüm, sonra karar, sonra öncesi/sonrası.

---

## 1. Gerçek depo ne halde

| Ne | Değer |
|---|---|
| kayıt | 102 (hepsi 0–5 gün yaşında, hiçbiri silinmiş değil) |
| kenar | 474 yönsüz (948 satır); kayıt başına 4,6 |
| kenar ağırlığı | min 0,21 · medyan 0,36 · ortalama 0,41 · en yüksek 0,85 |
| toplam ağırlık | 386 (sabah 08:33'te 445'ti; 5 gece × %2 küçülme) |
| `strengthening` (toplam ağırlık / kayıt) | **3,786** |
| sıcak kayıt | 102 / 102 (%100) — hepsi "taze hafta" kuralıyla sıcak |
| aktivasyon | min −4,41 · medyan −2,78 · en yüksek −1,22; `COLD_THRESHOLD = −4,5` altında **0** kayıt |
| tek kullanımlık bir kaydın −4,5'e düşmesi | ~148 saat (6 gün) |

Basınç (eski tanım): `0,6 × 3,786 + 0,25 × 0 + 0,15 × 1,0 = 2,42` — eşik
2,3374'e göre **%104**. Günlük dosyası (`sleep_journal.jsonl`) beş günün
tamamında bunu gösteriyor: her geçişte S 2,9–4,4 arası, ısı hep 1,0, toplam
2,0–2,8.

**Bir gece ne yapıyor.** Kopya üzerinde `shrink_edges(0,02, 0,05)` gece gece
uygulandı:

| gece | S | toplam | eşiğe oran |
|---|---|---|---|
| 0 | 3,786 | 2,422 | 1,036 |
| 1 | 3,710 | 2,376 | 1,017 |
| 2 | 3,636 | 2,332 | 0,998 |
| 5 | 3,422 | 2,203 | 0,943 |
| 10 | 3,093 | 2,006 | 0,858 |
| 30 | 2,065 | 1,389 | 0,594 |
| 60 | 1,127 | 0,826 | 0,353 |
| 90 | 0,503 | 0,452 | 0,193 (kenarlar tabana inip silinmeye başlıyor) |

Yani hiç kullanılmayan depoda çubuğun eşiğin altına inmesi 2 gece, alt eşiğin
(`LOWER`) altına inmesi 60 gece. Ama depo kullanılıyor ve gece **kendisi
büyütüyor**: günlük dosyasında 2 oturumu tekrar oynatan gece S'yi 2,88 → 3,90'a,
4 oturumu oynatan gece 3,37 → 4,36'ya çıkardı (ileri tekrar her birlikte
dokunulan çifti bağlıyor: bir oturumdan 108 kenar; yeniden örgü 3 komşu × 0,8;
dikiş). Gündüz ise neredeyse hiç: 06:14 → 18:13 arası S 3,8204 → 3,8204.
Sonuç: S'yi gece yükseltiyor, gece %2 indiriyor, gündüz kımıldatmıyor —
çubuk sonsuza kadar %100.

**Isı terimi.** `HEAT_TARGET = 0,30`: sıcak pay %30'un üstündeyse ısı sayılıyor.
Yüz kayıtlık, beş günlük bir depoda herkes taze-hafta kuralıyla sıcak,
kimsenin aktivasyonu −4,5'in altında değil; gece `update_heat` çağırınca
0 ısınan, 0 soğuyan. Isı 1,0 ama gecenin düşürebileceği bir şey yok.
Küçük depo asla soğuk kayıt üretmiyor; terim ödenemeyen bir borç.

## 2. Bench aynı ölçekte mi?

Hayır, ve fark linklerde değil ağırlıkta. 90 günün sonunda bench 264 kayıt /
1243 yönsüz kenar = kayıt başına 4,7 (gerçek: 4,6). Ama kenar başına
ortalama ağırlık bench'te 0,225, gerçek depoda 0,407: gerçek deponun kenarları
neredeyse iki kat ağır, çünkü aynı 47 oturum bir hafta içinde art arda
gecelerde tekrar oynatıldı (sahibin elle başlattığı geceler dahil) ve
yeniden örgü her gece 0,8'lik kenarlar ekledi.

Daha önemlisi: gece **her gün** koşan bench kolunda bile toplam basınç hiçbir
gün eşiği geçmiyor (90 günün en yükseği 2,24; eşik 2,34) — S mutlak
2,1–3,5'te geziniyor, precision 0,67. Yani eğrinin "S = 2,34'te precision
düşer" dediği S mutlak ağırlık değil: eğri gece **kapalıyken**, sıfırdan
büyüyen ağırlığı ölçüyor. Gece geçmiş bir depoda o ağırlığın büyük kısmı
gecenin onayladığı, küçülttüğü, tekrar güçlendirdiği ağırlık — SHY'nin
"küçültülmemiş güçlenme" dediği şey değil.

## 3. Karar

**(a) Güçlenme, son gecenin bıraktığı ağırlığa göre büyüme.** `night_pass`
küçültmeden sonra toplam kenar ağırlığını filigrana yazıyor (`weight`).
`sleep.pressure` artık `max(0, W_şimdi − W_son_gece) / kayıt` okuyor. Gece
hiç koşmadıysa taban sıfır ve terim toplamın kendisi — eşik eğrisinin
ölçtüğü durum, birebir. Eşik böylece "son geceden beri kayıt başına 2,36
ağırlık büyüdü" demek oluyor; eğri de bench'in kendi kopyasıyla değil,
ürünün `sleep.pressure` çağrısıyla yeniden üretildi (aynı S sütunu).

**(b) Isı, gecenin bu gece soğutabileceği kayıt payı.** `store.cooling_debt`:
sıcak, taze haftayı geçmiş ve kendi izi `COLD_THRESHOLD`'un altına inmiş
kayıtlar — `update_heat`'in kendi kuralı, aynı aktivasyon kodu. Isı =
`min(1, pay / 0,70)`: tek başına tamamen sıcak bir depoyu %30 bandına
indirecek kadar borç varsa 1. Güçlü kenar üzerinden ısınan komşular
sayılmıyor (küçük bir fazla sayım, testte belgeli). Taze depo 0 okur.

**(c) Eşikler yeniden türetildi.** `--threshold-curve` onarılmış,
deterministik bench'le tekrar koştu: S sütunu 2026-09-02 koşusuyla aynı,
precision serisi değişmiş (o koşu bench onarımından önceydi). `ESIK_UST`
2,3374 → **2,3647**, `ESIK_ALT` 0,7791 → **0,7882**, taban precision 0,6033 →
0,8273. İki ayrı koşu aynı dosyayı üretiyor.

**Gece sınırında anahtar.** Basınç son geceye göre büyüme olunca gecenin ilk
döngüsü tabanı yeniden yazıyor; ikinci döngü sınırında canlı okunsa her gece
sıfır görüp "basınç düştü" diye kesilirdi (sahibin günlüğünde tam olarak bu
vardı: `asleep → waking pressure dropped`, 35 kesik gece bench'te). Bekçi
artık döngü sınırlarında anahtara **gecenin başladığı basıncı** söylüyor;
gece kendi işiyle bitiyor (tekrar oynatacak şey kalmayınca ya da döngü
bütçesi), ritim yine uyandırıyor, kullanıcının istediği gece bütün koşuyor.
`REST_HOURS` davranışı değişmedi: biten gece 12 saat dinlendiriyor, gece her
boş pencerede koşmuyor.

## 4. Öncesi / sonrası

**Gerçek depo (kopya):**

| durum | güçlenme | borç | ısı | toplam | çubuk |
|---|---|---|---|---|---|
| eski tanım, bugün | 3,786 | 0 | 1,0 | 2,422 | **%104** |
| yeni tanım, yükseltmeden hemen sonra (filigranda taban yok) | 3,786 | 0 | 0 | 2,272 | %97 (ilk geceye kadar) |
| yeni tanım, bir geceden sonra | 0 | 0 | 0 | 0 | **%0** |
| + 5 yeni kayıt | 0,14 | 0 | 0 | 0,084 | %3,6 |
| + 20 yeni kayıt | 0,50 | 0 | 0 | 0,303 | %13 |
| + 30 yeni kayıt | 0,76 | 0 | 0 | 0,458 | %20 |
| aynısı, 8 gün dokunulmadan | 0,76 | 0 | 0,94 | 0,599 | %26 |

Çubuk dinlenmiş depoda sıfırdan başlıyor, her yeni kayıtla (yaklaşık %0,65)
yükseliyor, dokunulmayan kayıtlar soğumaya başlayınca ısı ekleniyor.
Yükseltme sonrası ilk gece filigrana tabanı yazana kadar eski okuma sürüyor
(bir gece, dürüst geri dönüş).

**Bench, bekçi kolu (`--watchman`, 90 gün, aynı senaryo, gece kararını ürünün
bekçisi veriyor):**

| | önce (`sleep-schedule-before.md`) | sonra (`sleep-schedule.md`) |
|---|---|---|
| gece sayısı | 103 (günde 1,14) | 103 (günde 1,14) |
| tetik | basınç 0 · sigorta 103 | basınç 0 · sigorta 103 |
| bitiş | kendi bitti 59 · ritim 9 · **"basınç düştü" 35** | kendi bitti 85 · ritim 18 · basınç düştü **0** |
| gece başlarken çubuk | %41 | %3,7 |
| uyanıkken çubuk ortalama / en yüksek | %41 / %65 | %1,7 / %41 |
| %100'de geçen pay | 0 | 0 |
| 90. gün S (mutlak), kenar | 0,46 · 427 | 0,46 · 427 |
| prime precision / recall / sıcak oran | 0,627 / 0,50 / 0,10 | 0,627 / 0,50 / 0,10 |

Çizelge değişmedi — bench'te gece zaten yirmi saatlik sigortayla geliyordu,
basınç eşiği ne eskiden ne şimdi aşıyor — ama artık geceler kendi işleriyle
bitiyor ve çubuk gerçeği okuyor. Gündüz metrikleri aynı, çünkü aynı geceler
aynı işi yaptı.

## 5. Bekçi kolunun yan bulgusu (düzeltilmedi)

Bekçi kolunda 90 gün sonunda kenar 427, gece-her-gün kolunda 1243; precision
0,63'e karşı 0,67. Sebep basınç değil: gece 12 saat gecikince ilk boş
pencerede **mikro-uyku** bekleyen oturumları tekrar oynatıyor (ileri/ters
tekrar, şema) ama yeniden örgü yapmıyor ve filigrana işliyor; gece geldiğinde
oynatacak oturum kalmadığı için tek döngüde bitiyor ve yeniden örgü hiç
koşmuyor. Bu, ürünün gerçek davranışı; ayrı bir karar konusu.
