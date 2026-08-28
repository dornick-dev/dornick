# neo × OpenCode kıyası — aynı görev, aynı model (28.08.2026)

**Görev:** `o1-rapor` (orta/python — CSV satış raporu + CLI).
**Model:** `z-ai/glm-5.3-flash` (OpenRouter; OpenCode oturumunda `openrouter/z-ai/glm-5.3-flash` olarak oturum kaydından doğrulandı).
**Puanlayıcı:** iki taraf için de AYNI dosya — `eval/coding/gorevler/o1-rapor/olcut.py`
(neo tarafında koşucunun içinden, OpenCode tarafında `py olcut.py <atolye>` tek-başına kipiyle).
**Süre tavanı:** 900 sn (ikisi de tavana çarpmadı).

## Görev seçimi neden o1-rapor?

- Zorluk **orta** istendi; üç adaydan (`o1-rapor`, `o2-servis`, `o3-ozellik`)
  `o2-servis` önceki koşuda 900 sn tavanına çarpmıştı — elendi.
- `o1-rapor`un puanlayıcısı tümüyle dosya/koşum tabanlı (aracı gerçekten
  çalıştırıp donmuş tohum CSV'den hesaplanan doğru cevapla karşılaştırıyor);
  sunucu/port oynaklığı yok, OpenCode atölyesine aynen uygulanabiliyor.
- Tohumu tek dosya (`satislar.csv`) — taze klasöre kopyalamak deterministik.

## Koşullar

| | neo | OpenCode |
|---|---|---|
| çalışma alanı | `%TEMP%\neocp-eval-o1-rapor-*` (koşucu kurdu, izole örnek + boş zihin) | taze `%TEMP%` klasörü, tohum kopyalandı, `opencode run` (cwd = klasör) |
| istem | `gorev.md` birebir, dış kapıdan (POST /api/gate) | `gorev.md` birebir, tek atımlık `run` argümanı |
| tekrar | 1 (tek koşu — gürültü payı aşağıda) | 1 |

## Sonuç tablosu

| harness | **puan** | çalışır (40) | kapsam (25) | sağlık (20) | test (15) | süre | tur / araç çağrısı | hatalı araç | token (giren / çıkan) | maliyet |
|---|---|---|---|---|---|---|---|---|---|---|
| **neo** | **100.0** | 40.0 | 25.0 | 20.0 | 0* | **671,5 sn** | 16 model turu / 15 araç | **6 (%40)** | 384.676 / 2.740 | $0,0295 |
| **OpenCode** | **96.5** | 40.0 | 25.0 | 17.0 | 0* | **140 sn** | 5 adım / 5 araç | 0 | 78.885† / 4.866 (3.643'ü akıl yürütme) | $0,0044 |

`*` istem test istemedi; eksen ölçüldü ama puana katılmadı (iki tarafta da test dosyası yok).
`†` 18.213 önbelleksiz + 60.672 önbellekten okunan giriş; neo'nun 384.676'sı da kümülatif istem toplamı (16 turun tamamı). Dürüst ortak ölçü maliyet sütunu.

**Puan farkı (3,5) anlamlı değil:** README'nin kendi eşiğiyle tek koşuda <5 puan
gürültüden ayırt edilemez; farkın tamamı da tek bir stil maddesinden geliyor
(OpenCode'un `rapor.py`'ında 6 kat girinti → boy/karmaşıklık 3/6). İkisi de
tam çalışan, kapsamı eksiksiz bir araç teslim etti. **Anlamlı olan fark verim:
4,8× süre, ~6,7× maliyet, %40'a karşı %0 hatalı araç çağrısı.**

## Gözlemler

**OpenCode'un izi ders gibi:** `ls` + ortam tespiti → `satislar.csv`'yi oku →
`rapor.py`'ı yaz → `py rapor.py satislar.csv` → `py rapor.py satislar.csv --ay 2026-03`.
Beş çağrı, sıfır hata, iki doğrulama da istemdeki örnek çağrıların birebir kendisi.
Yazdıktan sonra tek turda doğrulayıp durdu.

**neo aynı işi 16 turda yaptı.** Teslim ürünü kusursuz (100.0; Türkçe biçimli
çıktı bile üretti: `47.553,25 TL`) ama yol dolambaçlı: 15 araç çağrısının 6'sı
hatalı (bilinen `py`/`python` ve tırnaklama tuzakları), doğrulama izinde
`py -c "print('ok')"` gibi ortamı yoklayan sondalar var — ürünü değil kabuğu
test eden turlar. Her tur ~24 bin token'lık istem taşıyor; OpenCode'un tur başı
~15,8 bin girişinin %77'si önbellekten gelirken neo'nun kümülatif istem faturası
5 kata yakın.

**Harness farkları:** OpenCode tek ajan-tek oturum, dar araç seti (bash/read/write
üçlüsü işi bitirdi) ve agresif istem önbelleği ile koşuyor. neo tarafında
yetenek yüklemesi, daha geniş araç yüzeyi ve tur başına daha kalın bağlam var;
bu, zor/uzun işlerde güç ama bu boydaki bir görevde saf yük. (Not: neo'nun
"boş zihin" izolasyonu iki tarafta da eşit — hafıza katkısı ölçümde yok.)

## neo'nun OpenCode'u geçmesi için en etkili 3 öneri

1. **Hatalı araç döngüsünü ortam sondasıyla kes.** 6/15 hatalı çağrının kaynağı
   Windows kabuk tuzakları (`py`/`python`, tırnaklama, `cd &&`). Turda BİR kez
   koşan bir ortam tespiti (hangi yorumlayıcı, hangi kabuk) sonucunu oturum
   bağlamına sabitle ve araç hatasının normalize edilmiş metnini bir sonraki
   tura "düzeltme ipucu" olarak ekle. Bu tek başına ~4-6 boş turu, yani sürenin
   ve token faturasının yarıya yakınını geri kazandırır. (Açık işler notundaki
   "hatalı araç %10" bu koşuda %40'tı — en büyük kaldıraç burası.)

2. **İstem önekini incelt ve önbelleğe hizala.** Tur başına ~24k token'lık
   istem, 16 turda 384,7k kümülatif giriş yaptı; OpenCode aynı işi tur başına
   ~15,8k ve %77 önbellek isabetiyle götürdü. Ertelenmiş araç şeması köprüsü
   (ee8c48f) bu koşuda istem boyunu hedeflenen kadar düşürmemiş görünüyor:
   sistem öneki + yetenek listesini bayt-bayt sabit tutup OpenRouter
   `cache_read` oranını davranış tablosuna ölçüt olarak ekle — düşen her
   önbelleksiz bayt doğrudan maliyet ve gecikme.

3. **Doğrulamayı ürüne bağla, ortama değil, ve "yeşilse dur" refleksi ekle.**
   neo'nun doğrulama izi `print('ok')` sondaları; OpenCode'unki istemdeki
   çağrıların birebir koşulması. Harness'e şu refleksi koy: teslimden sonra
   istemde geçen somut çağrı örneklerini (varsa) aynen koş, çıktı beklentiyle
   tutuyorsa TURU BİTİR. Bu, "disiplin promptta değil harness refleksinde
   yaşar" dersinin uygulaması: 671 sn'nin büyük kısmı işi bitmiş ajanın
   dolanması, ve zor görevlerdeki 900 sn tavan yarası da aynı kökten.

## Ham kayıtlar

- neo: `eval/coding/sonuclar/20260828T133225Z-z-ai-glm-5.3-flash.json` (koşucu çıktısı; RAPOR.md de bu koşuyla yenilendi)
- OpenCode: olay akışı ve puanlayıcı çıktısı oturum geçici klasöründe koşuldu; puan dökümü: çalışır 40/40, kapsam 25/25, sağlık 17/20 (`boy/karmaşıklık: rapor.py 6 kat girinti`), test 0/15 (istenmedi) → ham 82/85 = 96,5.
- Tek koşudur: <5 puanlık farklar gürültü; verim farkları (süre/araç/maliyet) ise kat mertebesinde ve yönü nettir.
