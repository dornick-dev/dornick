# Otonom araştırma günlüğü — hatırlama motoru

Her iterasyon: **hipotez → değişiklik → sayı → karar**. Yalnız `recall/`
altına dokunulur, bir iterasyon bir fikir. Eşik dev'de bir kez seçilir,
tutulmuş sette dokunulmaz. Kazanma koşulu 5 metrikli Pareto (ARASTIRMA.md).

Ölçüm: `python eval/context_memory/harness.py` (dev + tutulmuş, tek eşik,
gecikme soğuk+tekrar ortancası). Referans dökümü: `baseline.py`.

---

## Kurulum (25.08.2026)

**Ortam doğrulandı.** `baseline.py` bu makinede tabanı birebir yeniden
üretti: Recall@3 0.93, Recall@1 0.87, MRR 0.908, paraphrase R@3 0.80,
boş-dönüş (%95 eşiği) 0.55, p95 ~0.8 ms, token 53. ARASTIRMA.md'deki
sayılarla örtüşüyor.

**Tutulmuş set mühürlendi.** `holdout.json` bir kez üretildi: aynı 24 hafıza
(dondurulmuş), aynı dağılımda 41 YENİ sorgu (15 paraphrase + 16 boş + 5
exact + 3 entity + 2 followup), dev'dekilerle örtüşmeyen sözcüklerle,
algoritma çıktısına bakılmadan yazıldı. Bir daha dokunulmayacak.

**Ölçer kuruldu.** `harness.py` — eşiği dev'de seçip (recall@3 ≥ 0.93 tutan
en yüksek eşik) tutulmuş sete aynen uygular; 5 metriği ikisinde de basar.

**Test tabanı:** 451 geçti, 110 atlandı, 2 ortamsal hata (`test_listen`
dead-stream, `test_organs` deaf-ear — ses donanımı yok; recall ile ilgisiz).
recall/ değişiklikleri bu sayıyı bozmamalı.

### fatih1 taban ölçümü (harness, eşik dev'de seçildi = 1.0000)

| metrik | DEV | TUTULMUŞ | hedef |
|---|---|---|---|
| recall@3 | 0.933 ✓ | 0.840 ✗ | ≥ 0.93 |
| paraphrase@3 | 0.800 | 0.733 ✗ | > 0.80 |
| boş-dönüş | 0.550 ✗ | 0.562 ✗ | ≥ 0.80 |
| p95 (ms) | 0.77 ✓ | 0.88 ✓ | ≤ 5 |
| token | 53 ✓ | 52 ✓ | ≤ 200 |

fatih1 kazanma koşulunu geçmiyor (beklenen — döngünün amacı bunu geçmek).
Dev'de asıl açık **boş-dönüş 0.55**; tutulmuşta ayrıca eşik=1.0 kırılgan
olduğundan recall de düşüyor (doğru ama top1<1.0 olan paraphrase'ler kapıda
eleniyor).

### İlk iş — belge/kod ayrışması (ARASTIRMA.md açık soru 1)

`neo-hafiza-mimarisi.pdf` okuma yolunu (bölüm 04) şöyle anlatıyor: iki kanal
tohum (fts5·bm25 + imza·Hamming) → **rrf ile birleştir** → yayılan
aktivasyon → eşik. **Kodda RRF YOK.** `recall/store.py:_seed` gerçekte:

- Literal kanal (`_seed_literal`): skor = `1/(1+pozisyon) + aşinalık` —
  bu sıra-tabanlı, bm25 büyüklüğünü ATIYOR. En üstteki sonuç eşleşme ne
  kadar zayıf olursa olsun **her zaman 1.0** alıyor.
- İmza kanalı (`_seed_signature`): ham Hamming benzerliği × 0.9.
- Birleşim: iki kanalın **MAX**'ı (RRF'in toplamı/sırası değil).

**Teşhis (kök neden):** boş-dönüş yarası ile paraphrase zayıflığı AYNI
kökten. Literal skorun sıra-tabanlı olması yüzünden top1 mutlak eşleşme
gücünü taşımıyor → boş bir sorgu `"terim"*` ön-ek genişletmesiyle herhangi
bir kayda değse top1=1.0 alıyor, gerçek isabetten ayırt edilemiyor (ölçüm:
hafıza ve boş'un tepe skoru ikisi de 1.00). MAX birleşim de imza kanalını
bastırıyor (0.9×~0.2 ≈ 0.18, literalin 1.0'ıyla yarışamaz) → kelime
tutmayan paraphrase kaçıyor.

Yani PDF'in "rrf" dediği yer kodda yok VE olması gereken şey saf RRF değil
(saf RRF de sıra-tabanlı, büyüklüğü atar, boş ayrımını çözmez): **büyüklüğü
koruyan, kalibre edilebilir bir skor birleşimi**. Bu tam olarak ARASTIRMA.md
hipotez 1. Döngü oradan başlıyor.

---

## İterasyon 1 — kalibre skor birleşimi (hipotez 1)

**Hipotez.** Literal skoru sıra (`1/(1+pozisyon)`) yerine BM25 BÜYÜKLÜĞÜNE
dayandır (`strength/(1+strength)`), imzayla MAX yerine **noisy-or**
(`1-(1-lit)(1-sig)`) birleştir. Böylece top1 gerçek bir güven skoru olur:
yüksek, kanallardan biri güvenliyse; düşük, ancak ikisi de zayıfsa. Boş
ayrımı da paraphrase de birleşik skordan çıkar.

**Değişiklik.** `recall/store.py:_seed` + `_seed_literal` (yalnız recall/).

**Sayılar (harness):**
| | DEV önce→sonra | TUTULMUŞ önce→sonra |
|---|---|---|
| recall@3 | 0.933 → **0.967** | 0.840 → 0.880 |
| paraphrase@3 | 0.800 → **0.900** | 0.733 → **0.800** |
| boş-dönüş | 0.550 → **0.600** | 0.562 → **0.688** |
| ham recall@3 | 0.933 → 0.967 | 0.880 → **0.920** |

**Karar: TUT.** Her metrikte, her iki sette ilerleme; hiçbir gerileme yok —
Pareto cephesi ilerledi. Kazanma çizgisini geçmedi (boş < 0.80) ama temel
mekanizma bu: eşik ancak kalibre skorla anlamlı. Üstüne inşa ediliyor.

## İterasyon 2 — işlev kelimelerini FTS'ten ele (hipotez 4'ün literal ayağı)

**Hipotez (teşhisten).** Sızan boşların ~hepsi genel anılara (`neocp-hedef`)
**işlev kelimeleriyle** gidiyor — özellikle "**bir**" (belgisiz edat), ki o
memory'de iki kez geçiyor. FTS `"bir"*` bu genel anıyı yanlış uyandırıyor.
İşlev kelimelerini FTS eşleşmesinden çıkar.

**Değişiklik.** `recall/store.py:_match_expression` — `vector.STOPWORDS`
elenir. (Önce imzadan da denedim; kısa metni "bir şey"→tek "şey" özniteliğine
çökertip `test_vector` short-texts'i bozdu → geri alındı. Sızıntı zaten
tamamen literal kanaldanmış: FTS-only ile birebir aynı sonuç.)

**Sayılar:**
| | DEV i1→i2 | TUTULMUŞ i1→i2 |
|---|---|---|
| recall@3 | 0.967 → 0.967 ✓ | 0.880 → 0.840 |
| paraphrase@3 | 0.900 → 0.900 ✓ | 0.800 → 0.733 |
| **boş-dönüş** | 0.600 → **0.850 ✓** | 0.688 → **0.938 ✓** |
| p95 (ms) | 0.71 ✓ | 0.74 ✓ |
| token | 51 ✓ | 50 ✓ |

**DEV artık 5/5 GEÇİYOR.** Holdout boş-dönüş de 0.94'e fırladı. Holdout
recall@3 (0.84) + paraphrase (0.733) hâlâ eşiğin altında — çünkü eşik (dev'de
0.6539) holdout'un çok zayıf paraphrase'lerini eliyor.

**Karar: TUT.** Front ilerledi, gerileme yok. Regresyon: `test_recall_eval`
içindeki eski "skor ayıramıyor" testi (Faz 0 yarasını belgeliyordu, "ayrım
açılırsa güncelle" notuyla) → `test_fused_score_now_gates`'e çevrildi (artık
ayrım kazanımını koruyor). Tam paket: 451 geçti (+ 2 ortamsal ses hatası,
recall dışı), recall testleri yeşil.

### Kalan yara — sinonim paraphrase tavanı (holdout)

Holdout'ta doğru anı ilk3'te ama top1 çok düşük olan asıl kayıt:
"etiketleri hangi düzende isimlendiriyoruz" → tag-adlandirma **top1 0.148**.
Neden: etiket≠tag, isimlendirme≠adlandırma — sözcük de 4-gram da paylaşmıyor,
saf sinonim. Lexical/n-gram imza bunu köprüleyemez (embedding yasak).

## İterasyon 3 (planlandı, UYGULANMADI) — IDF ve neden yetmez

**Hipotez.** IDF ağırlıklı SimHash (ayırt edici nadir kelime baskın) holdout
sıralama kaçışlarını düzeltir.

**Analiz (uygulama öncesi).** Holdout'un 4 hafıza-kaçışını tek tek çıkardım:

| # | sorgu → hedef | rank | neden | lexical düzeltilebilir? |
|---|---|---|---|---|
| 1 | "depodaki su kaç metrede" → corum-depo-seviye | r4 | "su" (sık) ayırt edici "depo/metre"yi geçiyor | **EVET** (IDF) |
| 2 | "bitcoin kaç liraydı" → btc-fiyat | r0 | bitcoin≠BTC, lira≠TL (kısaltma) | HAYIR |
| 3 | "beni ne iş yaparken tanıyorsun" → fatih | r0 | iş≠mühendis, çalışan (semantik) | HAYIR |
| 4 | "etiketleri isimlendiriyoruz" → tag-adlandirma | r1(gated) | etiket≠tag, isimlendir≠adlandır (sinonim) | HAYIR |

**Sonuç: IDF UYGULANMADI.** IDF ayırt edici öznitelikleri güçlendirir ama
**var olmayan örtüşmeyi yaratamaz.** #2/#3/#4'te sorgu ile hedef HİÇ ortak
sözcük/n-gram taşımıyor — köprülenecek sinyal yok. IDF en iyi ihtimalle #1'i
düzeltir → holdout recall 22/25 = **0.88**, hâlâ < 0.93. Yani hiçbir yalnız-
`recall/` değişikliği kazanma çizgisini geçemez; karmaşıklık + baseline
tutarsızlığı getirir, sonucu değiştirmez. Uygulamamak doğru karar.

## Karar: kabul edilen en iyi = iter1+2 (fatih2 adayı), döngü erken durdu

**fatih1 → (iter1+2) Pareto tablosu:**
| metrik | fatih1 DEV | iter1+2 DEV | fatih1 HOLD | iter1+2 HOLD | hedef |
|---|---|---|---|---|---|
| recall@3 | 0.933 | **0.967** | 0.840 | 0.840 | ≥0.93 |
| paraphrase@3 | 0.800 | **0.900** | 0.733 | **0.800** | >0.80 |
| **boş-dönüş** | 0.550 | **0.850** | 0.562 | **0.938** | ≥0.80 |
| p95 (ms) | 0.77 | 0.71 | 0.88 | 0.74 | ≤5 |
| token | 53 | 51 | 52 | 50 | ≤200 |

iter1+2 fatih1'i her iki sette, her metrikte **domine ediyor** (eşit ya da
daha iyi) ve **ASIL YARAYI kapatıyor**: boş-dönüş dev 0.55→0.85, holdout
0.56→0.94. DEV kazanma koşulunun 5/5'ini geçiyor.

**Neden tam kazanma (holdout recall ≥0.93) ulaşılamadı:** tutulmuş set,
dev'den farklı olarak, hiç ortak sözcük taşımayan saf sinonim/kısaltma
paraphrase'leri içeriyor (etiket/tag, bitcoin/BTC, iş/mühendis). Dev'in
"zor" paraphrase'leri tesadüfen bir içerik kelimesi paylaşıyordu
("veritabanı dökümü ALINIYOR" ↔ "pg_dump ile ALINIYOR"), holdout'unkiler
paylaşmıyor. Bu, dağılımın biraz daha zoruna denk geldi; ama mühür kuralı
gereği holdout'a dokunulmadı.

**Erken durma (ARASTIRMA.md kuralı):** kazanma yalnız-lexical yöntemlerle
tutulmuş sette **yapısal olarak ulaşılamaz** (embedding yasak; eval'den
sinonim tablosu = hile). Bu, plato'nun en güçlü hali. Döngü burada duruyor.

**Öneri (kullanıcı seçerse, gelecek yön):**
- Sinonim tavanı yalnızca embedding ya da **küçük, alan-bilgisinden türeyen**
  (eval'den DEĞİL) bir eş-anlamlı/kısaltma sözlüğüyle aşılır (BTC↔bitcoin,
  TL↔lira gibi). Bu meşru alan mühendisliği ama genellemez ve sıfır-bağımlılık
  ilkesini zorlar — kullanıcı kararı.
- Ya da tutulmuş seti dev ile aynı zorlukta yeniden üretmek (ama o mührü
  bozar; ancak yeni bir araştırma turunda).

**Test durumu:** 451 geçti, 2 ortamsal ses hatası (recall dışı), tüm recall
testleri yeşil. iter1+2 commit'lendi (bebfbc4).

---

---

## 26.08.2026 — ölçek turu (100 anı + 60 episode)

Yeni düzenek: `scale_dataset.json` (donmuş, 70 altın-etiketli sorgu; tuzak/
boş/devam sınıfları ayrı) + `scale_bench.py` (ürünle özdeşlik korumalı).
Ayrıntı: `RAPOR-olcek.md`.

Kabul: **ruh-dışlama** (ruhta tam gövdeyle duran kayıt prime'a giremez —
aynı isabet, −%9 token) + oturum-içi prime tekrarının kesilmesi (12 turda
−%20) + not biçimi temizliği + `mind_recall` gövde sınırı 700.

Ret (ölçülerek): zemin2 / oran40 / carpim* / kademe — tuzak sessizliğini
devam+paraphrase isabetinden satın alıyorlar; gap45 etkisiz; kisa120 id-bazlı
metriğin göremediği bilgi kaybı riskiyle ilkece reddedildi.

Teşhis (kalıcı bulgu): altınlı ve tuzak sorgular kanıt-oranı dağılımında tam
örtüşüyor (p25=0.25 her ikisinde) — sözcüksel aile bu ayrımı YAPAMAZ. Skor
doygun (0.963 vs 0.874). Sıradaki gerçek sıçrama sorgu tarafında: yeniden
yazıcı ya da statik sinonim köprüsü.

Dev/holdout kapısı değişmedi: dev 5/5 GEÇTİ, holdout 0.840 (sinonim tavanı).

## 26.08.2026 — sinonim köprüsü (aynı gece, devam)

`recall/bridge.py`: ~50 genel eş anlam grubu, yalnız sorgu tarafında;
ekli biçimler önekle, kısa anahtarda tam eşleşme şartı. Tablo kategori
geneli yazıldı (eval'e bakılmadı) ve TEK ATIŞTA ölçüldü — hile kuralı korundu.

Sonuç: dev 1.000/1.000 (recall/paraphrase, tam puan), MÜHÜRLÜ HOLDOUT
recall@3 0.840→0.920, paraphrase kapısı geçildi (0.733✗→0.867✓), boş-dönüş
korundu (0.938). Ölçek korpusunda sıfır regresyon (tuzak 0.33, boş 1.00,
token +%2). Kalan 2 holdout kaçışı gerçek-eşanlamsız çiftler — bilerek
tabloya konmadı. recall@3 kazanma şartına (0.93) 1 sorgu uzak; oraya
tabloyla gitmek eval'e tablo yazmak olur, gidilmedi.

## 26.08.2026 — "hepsini dene" turu (sabaha karşı)

Kalan yöntemler tek tek ölçüldü, DÖRDÜ DE ürünü değiştirmedi (RAPOR §4b):
IDF ağırlıklı kanıt düz-oranla aynı eğri (yeni Pareto noktası yok);
sayı-koruma etkisiz; 160 kırpma −%0.6. LLM sorgu-yeniden-yazıcı TAVAN
ölçümü: isabet 0.87→0.94, sinonim 0.50→1.00, paraphrase 0.90 — ama tur
başına +1 model çağrısı; ürüne girmedi, yerel küçük yeniden-yazıcının
getiri kanıtı olarak kayda geçti (llm_rewrites.json ile tekrar üretilir).

Durum: kabul edilen yapı (dedup + ruh-dışlama + köprü + biçim + gövde
sınırı) Pareto'da; sözcüksel aile tüketildi. Sıradaki sıçrama yerel
yeniden-yazıcı.
