# dornick — İnsan Benzeri Hafıza: Yol Haritası ve Benchmark Şartnamesi

> Bu belge bir uygulama emri olarak yazıldı. Her faz tek başına merge edilebilir bir PR'dır;
> fazlar sıralıdır, atlanmaz. Kod tanımlayıcıları ve yorumlar proje konvansiyonu gereği
> **Türkçe** yazılır. Her faz "kabul kriteri" bölümündeki benchmark sayılarını geçmeden
> bir sonrakine geçilmez.

---

## 0. Amaç ve değişmezler

**Amaç:** Hafıza katmanına zaman, pekişme, güncelleme ve konsolidasyon eklemek — yani
bir kaydın *ne zaman* ve *ne kadar* hatırlanacağını, yazıldığı andaki sabit ağırlık değil,
kullanım geçmişi ve bağlam belirlesin.

**Değişmezler (hiçbir faz bunları bozamaz):**

1. **Hiçbir şey silinmez.** Mezar taşı felsefesi korunur. "Unutma" = aktivasyonun eşik
   altına inmesi; kayıt `mind_recall` ile her zaman bulunabilir.
2. **Bağımlılık eklenmez.** sqlite3 + (opsiyonel) numpy. Embedding modeli, torch, harici
   servis yok.
3. **Ölçülen yol = ürün.** `eval/` altındaki her rig, `dornick.loop.select_prime` ve
   `RecallStore.recall` gibi ürünün kendi fonksiyonlarını çağırır; kopya mantık yasak
   (mevcut `scale_bench.py` deseni).
4. **Eski `recall.db` açılmaya devam eder.** Her şema değişikliği `_add_missing_columns`
   yoluyla ileri uyumlu; yeni sütunlar ilk erişimde geriye dönük doldurulur.
5. **Gizlilik ilkesi eklenir (Faz 3):** Konsolidasyon geçişi asla hosted modele veri
   göndermez; `tanima.bulut_onayi` kapalıysa geçiş sadece yerel modelle koşar, yoksa atlanır.

**Mevcut kod haritası (değişecek yerler):**

| Dosya | Ne var | Ne değişecek |
|---|---|---|
| `src/dornick/recall/store.py` | `node`/`link`/`node_fts`, `remember`, `_weave`, `open`, `recall`, `_seed*` | zaman bazlı aktivasyon, supersede, kodlama gücü, saat enjeksiyonu |
| `src/dornick/recall/vector.py` | SimHash imza | değişmez (Faz 5'te IDF opsiyonel) |
| `src/dornick/mind/store.py` | `Mind`, `Soul`, `soul()`, `memories()` | ruh seçimi aktivasyona göre |
| `src/dornick/mind/tools.py` | `mind_memory`, `mind_recall` | `save` çelişki tespiti + `supersedes` parametresi |
| `src/dornick/loop.py` | `select_prime`, `prime_note`, `_prime_recall` | bağlam bonusu, aktivasyon eşiği |
| `src/dornick/tanima.py` | gece döngüsü tetikleyici | konsolidasyon adımı |
| `training/betikler/08_kisisel_dongu.py` | hasat → etiket → ince ayar → sınav | konsolidasyon ve yeniden örme adımları |
| `eval/context_memory/` | `scale_bench.py` (tek-tur prime kalitesi) | yeni `yasam_bench.py` (çok-gün yaşam döngüsü) |

---

## 1. Faz 0 — Ölçüm altyapısı (önce bu, hiçbir mekanik değişmeden)

Mevcut benchmark tek turluk: "bu sorguya bu 100 hatıradan hangileri gelmeli". Zamanı,
tekrarı ve düzeltmeyi ölçmüyor. İnsan benzeri hafızanın faydası ancak **günler süren bir
yaşam senaryosunda** görünür. Önce onu ölçebilir hale gel.

### 0.1 Saat enjeksiyonu

`recall/store.py` ve `mind/store.py` içindeki `_now()` çağrıları doğrudan
`datetime.now()` okuyor. Bunu enjekte edilebilir yap:

```python
# recall/store.py
class RecallStore:
    def __init__(self, path, *, cache_bytes=..., saat: Callable[[], datetime] | None = None):
        self._saat = saat or (lambda: datetime.now(timezone.utc))
    def _simdi(self) -> str:
        return self._saat().isoformat(timespec="milliseconds")
```

`Mind` ve `open_mind` aynı parametreyi geçirir. Ürün davranışı değişmez; benchmark
sanal saati gün gün ilerletebilir. **Bu olmadan Faz 1 test edilemez.**

### 0.2 Yaşam senaryosu veri seti — `eval/context_memory/yasam_dataset.json`

Bir kullanıcının **90 sanal günü**. Her gün 0–6 olay. Olay türleri:

Olaylar **oturumlara** gruplanır: bir gün birden çok oturum içerebilir, her oturumun
bir sonucu vardır. Gece tekrarı (Faz 3) oturumu bir bütün olarak yürüdüğü için bu
gruplama zorunludur.

```json
{
  "gun": 12,
  "oturum": "s_012a",
  "sira": 3,
  "tur": "kaydet | sor | duzelt | kullan | arac | sonuc | sessiz | uyan",
  "kind": "preference",
  "icerik": "Raporları PDF değil xlsx istiyorum",
  "etiket": "rapor-format",
  "beklenen": ["n_rapor_xlsx"],
  "yasak": ["n_rapor_pdf"],
  "baglam": {"proje": "koru1000", "saat": 10},
  "sonuc": null
}
```

- `kaydet`: yeni hatıra girer (id deterministik: `n_<etiket>`).
- `sor`: kullanıcı mesajı; `beklenen` listesi prime'a **girmeli**, `yasak` listesi
  **girmemeli**.
- `duzelt`: aynı etiketle çelişen yeni bilgi ("artık PDF istiyorum"). Bundan sonraki
  `sor` olaylarında eski kayıt `yasak`a düşer.
- `kullan`: model `open()` çağırdı (pekiştirme sinyali). `sira` alanı oturum içindeki
  sırayı verir — zaman komşuluğu buradan çıkar.
- `arac`: bir araç çağrısı (`icerik` = araç adı + kısa özet). Oturum günlüğüne yazılır;
  tekrar bunları da yürür.
- `sonuc`: oturumun kapanışı. `"sonuc": "basarili" | "basarisiz" | "duzeltildi" | "acik"`.
  `basarisiz` = test kırıldı / araç hatası; `duzeltildi` = kullanıcı "hayır, öyle değil"
  dedi; `acik` = hedef tamamlanmadan oturum bitti. Ters tekrarın girdisi budur.
- `sessiz`: o gün hiçbir şey olmadı (unutma eğrisi için gerekli).
- `uyan`: gece geçişi sürerken dış uyarı (`icerik`: `"kullanici" | "otomasyon" | "tepsi"`).
  `baglam.yuzde` gece geçişinin yüzde kaçında geldiğini verir; bench o noktada
  `gece_gecisi`'ne uyanma sinyali gönderir. Yalnız `kullanici` gerçek uyanma; diğerleri
  eşik altı kalmalı (bkz. 3.10).

Senaryo en az şunları içermeli (her biri ayrı ölçüm kümesi):

| Küme | Ne test eder | Asgari olay |
|---|---|---|
| **A. Sabit gerçekler** | 90 gün boyunca değişmeyen, arada kullanılan bilgiler (ad, şirket, stack) | 15 kayıt, 30 sor |
| **B. Düzeltme zinciri** | Aynı konuda 2–4 kez güncellenen tercihler | 8 zincir, her zincirde 3+ düzelt |
| **C. Tek seferlik gürültü** | Bir kez yazılıp hiç kullanılmayan alakasız notlar | 60 kayıt |
| **D. Tekrar kullanılan yordamlar** | `procedure` türü, düzenli aralıkla `kullan` | 6 yordam |
| **E. Bağlam çakışması** | Aynı kelimeler, farklı proje (koru1000 "rapor" vs kobyte "rapor") | 10 çift |
| **F. Tuzak sorular** | Hafızada hiçbir karşılığı olmayan sorular; beklenen = boş | 40 sor |
| **G. Uzun sessizlik** | 30 gün hiç kullanılmayan sonra geri dönen konu | 5 konu |
| **H. Zaman komşuluğu** | Aynı oturumda peş peşe kullanılan, içerikleri **benzemeyen** iki hatıra; sonra biri sorulunca diğeri açık `recall`'da gelmeli ("o raporu yaparken kullandığım şey neydi") | 12 çift, 12 sor |
| **I. Ters tekrar** | Aynı hatıra bir oturumda başarıya, başka oturumda başarısızlığa götürür; sonra aynı konuda `sor` — başarıya götüren üstte olmalı, başarısızlığa götüren `lesson` ile yan yana | 8 hatıra, 16 oturum, 8 sor |
| **J. Dikiş** | Pazartesi A→B, Perşembe B→C; A sorulunca C açık recall'da 2. sıçramada gelmeli | 6 üçlü, 6 sor |
| **K. Gömülme** | 90 gün boyunca hiç dokunulmayan, hiçbir aktif düğüme bağlı olmayan kayıt; 90. günde açık `recall` ile (soğuk FTS yolu) bulunmalı ama `select_prime`'a **girmemeli**. Karşı grup: aynı yaşta ama aktif bir şemaya bağlı kayıt — şema tazelemesiyle sıcak kalmalı ve prime'a girebilmeli | 10 yalıtık + 10 şemalı kayıt, 20 sor |
| **N. Şema tazeleme** | 30 gün önce yazılmış X; bugün X'e içerik kenarıyla bağlı Y kullanılıyor; ertesi gün X sorulunca X'in aktivasyonu, Y kullanılmasaydı olacağından yüksek olmalı | 10 çift |
| **O. Geriye dönük yakalama** | Sıradan bir kayıt Z, aynı oturumda 40 dk sonra yüksek sürprizli olay; Z'nin ertesi gün aktivasyonu, sürprizsiz kontrol oturumundaki eşine göre yüksek | 8 çift |
| **P. Büyüme** | 200k düğümlük sentetik hafıza (%95 soğuk); `recall()` p95 ve RAM, 20k düğümlük hafızayla karşılaştırılır | 2 hafıza, 200 sor |
| **L. Kesinti** | Gece geçişi %30 / %60 / %90'ında `uyan` olayıyla kesilir; ertesi gece devreden oturumlar tamamlanmalı, kesilmeden önce tekrar edilenler korunmalı, yarım damıtma kümesi var olmamalı | 9 gece (3 kesinti noktası x 3) |
| **M. Ritim** | Kullanıcı 60 gün boyunca hafta içi 09:00-18:00 aktif; sistem 61. günden itibaren gece geçişini 08:30'dan önce bitirmeli, hafta sonu daha geç başlayabilmeli | 60 gün örüntü, 10 gün ölçüm |

Veri seti Türkçe (mevcut bench ile aynı gerekçe), el yazımı, dondurulmuş, `holdout`
bölümü ayrı.

### 0.3 Yaşam benchmark'ı — `eval/context_memory/yasam_bench.py`

Senaryoyu gün gün oynatır; her `sor` olayında **ürünün** `select_prime` ve `mind.soul()`
çıktısını alır. Metrikler:

| Metrik | Tanım | Yön |
|---|---|---|
| `prime_precision` | prime'a giren kayıtlardan `beklenen` olanların oranı | ↑ |
| `prime_recall` | `beklenen` kayıtlardan prime'a girenlerin oranı | ↑ |
| `yasak_sizinti` | `yasak` listesinden prime'a giren toplam kayıt sayısı | ↓ (hedef 0) |
| `tuzak_sessizlik` | F kümesinde prime'ın boş döndüğü oran | ↑ |
| `bayat_ruh` | ruhta görünen ama supersede edilmiş/`yasak` kayıt sayısı (gün başına) | ↓ (hedef 0) |
| `taze_ruh` | son 7 günde düzeltilen kayıtların ruha girme oranı | ↑ |
| `ruh_token` | ruhun ortalama uzunluğu (4 karakter = 1 token) | ↓ veya sabit |
| `prime_token` | tur başına enjekte edilen ortalama token | ↓ veya sabit |
| `geri_donus_recall` | G kümesinde uzun sessizlik sonrası ilk sorguda recall | ↑ (açık recall ile) |
| `komsuluk_recall` | H kümesinde içerik-benzemez komşunun açık `recall` ilk 5'e girme oranı | ↑ |
| `sorumluluk_dogrulugu` | I kümesinde başarıya götüren hatıranın başarısıza götürenin üstünde sıralanma oranı | ↑ |
| `dikis_recall` | J kümesinde A sorulunca C'nin ilk 8'e girme oranı | ↑ |
| `gomulme_recall` | K kümesinde 90. günde recall | ↑ |
| `gece_suresi` | gece geçişinin 50k düğümde toplam süresi | ↓ (bütçe: 5 dk) |
| `kesinti_kaybi` | L kümesinde kesinti sonrası ertesi gece tamamlanmayan oturum oranı | ↓ (hedef 0) |
| `kesinti_gecikmesi` | `uyan(kullanici)` sinyalinden gece geçişinin durmasına kadar geçen süre | ↓ (bütçe: 500 ms) |
| `yarim_damitma` | L kümesinde kesinti sonrası kaynak kenarı eksik damıtık düğüm sayısı | ↓ (hedef 0) |
| `ritim_isabeti` | M kümesinde gece geçişinin tahmini geliş saatinden önce bitme oranı | ↑ |
| `atalet` | uyanma sonrası ilk oturumda ruhun bayat (gece öncesi) aktivasyonla yüklenme sayısı | ↓ (hedef 0) |
| `sema_tazeleme` | N kümesinde X'in aktivasyon artışı (Y kullanıldı − kontrol) | ↑ (>0) |
| `yakalama` | O kümesinde Z'nin aktivasyon artışı (sürprizli − kontrol) | ↑ (>0) |
| `sicak_oran` | aktif (imza indeksinde) düğümlerin toplam düğüme oranı, 90. gün | bilgi (beklenen %10-30) |
| `buyume_p95` | P kümesinde 200k / 20k `recall()` p95 oranı | ↓ (hedef ≤ 1.5) |
| `buyume_ram` | P kümesinde imza indeksinin RAM'i, 200k / 20k | ↓ (hedef ≤ 2) |
| `gecikme_p95` | `recall()` p95 ms, 50k düğümde | ↓ (bütçe: 20 ms) |

Bench, gün sınırlarında **gece geçişini de çağırır** (`orgu.gece_gecisi(mind, saat)`),
yani Faz 3'ten itibaren ölçülen şey yalnızca arama değil, gece + arama birlikte. Faz 0'da
gece geçişi henüz yokken H/I/J/K taban çizgisi düşük çıkacaktır — bu beklenen ve
istenen sonuç; faydayı kanıtlayacak fark buradan gelir.

Rapor formatı: `docs/charts/` altına JSON + markdown tablo; **her faz için önce/sonra
sütunu**. Bench ablation destekler: `--kapat aktivasyon,supersede,...` ile her mekanik
tek tek kapatılıp Pareto tablosu üretilir (mevcut `scale_bench.py` deseni).

### 0.4 Birim testleri

`tests/test_yasam_bench.py` — bench'in kendisinin deterministik olduğunu doğrular (aynı
seed, aynı sonuç). `tests/test_saat.py` — enjekte saatin tüm `created/last_used`
alanlarına ulaştığını doğrular.

**Faz 0 kabul:** Bench koşuyor, mevcut ürün için **taban çizgisi** raporu
`docs/charts/yasam-taban.md` olarak commit'lenmiş. Bu rapor olmadan Faz 1 PR'ı açılmaz.

---

## 2. Faz 1 — Zaman bazlı aktivasyon (ACT-R base-level)

**Sorun:** `uses` sayacı zamanı bilmiyor; `by_kind` `uses DESC` sıralıyor, çok kullanılmış
eski kayıt yeni düzeltmeyi ruhtan dışarıda tutuyor. 300 gün önce yazılmış kayıt dünkü
kadar güçlü.

### 1.1 Şema

```sql
ALTER TABLE node ADD COLUMN kullanimlar TEXT NOT NULL DEFAULT '[]';
-- JSON dizi, son 30 kullanım: [{"t": "<ISO>", "w": 1.0, "etiket": "acildi"}, ...]
-- Yazım anı (created) ilk kullanımdır (w = 1.0; Faz 4 bunu sürprizle değiştirir).
-- w negatif olabilir (Faz 3 ters tekrar). etiket: acildi | basari | hata | gece-dokunuş
-- Faz 1'de yalnız "acildi" yazılır; alan baştan bu biçimde açılır ki sonraki fazlar
-- şema değiştirmesin.
```

`uses` ve `last_used` sütunları korunur (arayüz okuyor), `open()` üçünü birlikte günceller.
Göç: `_add_missing_columns` boş dizi ekler; ilk `_load_index` sırasında `kullanimlar`
boş olanlara `[created] + [last_used]*min(uses, 19)` yazılır (kabaca geriye dönük).

### 1.2 Formül — `recall/aktivasyon.py` (yeni modül)

```python
BOZUNMA = 0.5        # d — ACT-R standart
TABAN_SANIYE = 3600  # t'nin birimi: saat; günlerle değil saatlerle ölçülür ki
                     # aynı gün içindeki iki kullanım da ayrışsın.

def taban_aktivasyon(kullanimlar: list[Kullanim], simdi: datetime) -> float:
    """B = ln( Σ w_k · t_k^(-d) ). Ağırlıklı toplam ≤ 0 ise (yalnız hatalar) sabit taban.
    Faz 1'de her w = 1.0, formül klasik ACT-R'a indirgenir."""
    toplam = 0.0
    for k in kullanimlar:
        gecen = max((simdi - k.t).total_seconds() / TABAN_SANIYE, 0.01)
        toplam += k.w * gecen ** (-BOZUNMA)
    return math.log(toplam) if toplam > 0 else -10.0

def aktivasyon_carpani(b: float) -> float:
    """B'yi 0..1 arası bir çarpana sıkıştır: sigmoid(B / OLCEK).
    Tohumlama skoru bununla çarpılır; ruh sıralaması doğrudan B kullanır."""
```

Kalibrasyon: `OLCEK` ve `BOZUNMA` bench ile ayarlanır; varsayılanlar ACT-R literatüründen.
**Kalibrasyon sonuçları dokümante edilir**, "sihirli sayı" yasak.

### 1.3 Nereye bağlanır

- `RecallStore._seed_literal`: `familiarity = min(0.15, 0.03*uses)` **silinir**, yerine
  `conf * (0.5 + 0.5 * aktivasyon_carpani(B))`. Yani en unutulmuş kayıt bile skorun
  yarısını korur — hiç kaybolmaz, geride kalır.
- `RecallStore._seed_signature`: aynı çarpan.
- `RecallStore.by_kind`: `ORDER BY uses DESC` → Python tarafında B'ye göre sırala
  (SQL'de hesaplanamaz; `by_kind` zaten limit 50 çekiyor, sıralama ucuz).
- `Mind.soul()`: değişmez, `by_kind` üzerinden otomatik düzelir.
- `loop.select_prime`: `RECALL_PRIME_FLOOR` aynı kalır; eşik artık aktivasyonla çarpılmış
  skora uygulanıyor, dolayısıyla unutulmuş kayıtlar kendiliğinden prime'a giremez.
- Yayılma (`recall` içindeki hop döngüsü): komşu aktivasyonu `strength * weight *
  HOP_DECAY` → `* aktivasyon_carpani(B_komsu)` ile de çarpılır. Unutulmuş düğüm
  çağrışım yolunu iletmez.

### 1.4 Testler

- `test_aktivasyon.py`: (a) tek kullanım, 1 saat sonra > 1 gün sonra > 30 gün sonra;
  (b) 5 aralıklı kullanım, 30 gün sonra > 5 ardışık kullanım, 30 gün sonra (aralıklı
  tekrar etkisi); (c) hiç kullanılmamış kayıt skoru 0 değil, taban değer.
- `test_recall.py` mevcut testler kırılmaz (saat sabitlenerek).

### 1.5 Kabul (yaşam bench, taban çizgisine göre)

- `bayat_ruh` ≥ %50 azalma
- `taze_ruh` ≥ 0.8
- `prime_precision` düşmez, `tuzak_sessizlik` düşmez
- `gecikme_p95` bütçede

---

## 3. Faz 2 — Supersede (yeniden pekiştirme)

**Sorun:** "Aynı konuda kayıt varsa eskisini sil, yenisini yaz" araç açıklamasında; sistem
yapmıyor. `save` onaysız, `forget` onaylı → model çelişki üretmekte serbest, temizlemekte
değil.

### 2.1 Şema

```sql
ALTER TABLE node ADD COLUMN supersedes TEXT NOT NULL DEFAULT '';   -- eski kaydın id'si
ALTER TABLE node ADD COLUMN superseded_by TEXT NOT NULL DEFAULT ''; -- yeni kaydın id'si
CREATE INDEX IF NOT EXISTS node_superseded ON node(superseded_by) WHERE superseded_by != '';
```

### 2.2 Mekanik — `RecallStore.guncelle(eski_id, yeni_body, ...)`

1. Yeni node yazılır (`remember` ile), `supersedes=eski_id`.
2. Eski node'a `superseded_by=yeni_id` yazılır; **silinmez, deleted=0 kalır**.
3. `link(yeni, eski, weight=1.0, reason="günceller")`.
4. Eski node'un `kullanimlar` listesi yeni node'a **kopyalanır** (pekişme mirası: düzeltme,
   düzeltilen şeyin aktivasyonunu devralır — yoksa yeni kayıt sıfırdan başlayıp ruhta
   eskisinin altında kalırdı).

### 2.3 Okuma tarafı

- `_seed*`, `by_kind`, `recent`: `WHERE deleted=0 AND superseded_by=''`. Eski sürüm
  tohumlanmaz.
- `recall` yayılma: eski node'a aktivasyon gelirse **yeni node'a yönlendirilir**
  (`superseded_by` zinciri sonuna kadar takip edilir, döngü koruması ile).
- `open(eski_id)`: eski kaydı döner ama sonuna `[güncellendi → yeni_id]` notu ekler;
  `mind_recall` çıktısında model bunu görür.
- `series(tag)`: **tüm sürümleri** döner (zaman dizisi zaten geçmişi istiyor).
- Arayüz beyin grafiği: supersede kenarı farklı renk; eski düğüm soluk.

### 2.4 Araç yüzeyi — `mind/tools.py`

`mind_memory` `save` aksiyonuna:
- `supersedes: str` (isteğe bağlı) — model biliyorsa doğrudan verir.
- Model vermezse **otomatik çelişki adayı**: `_seed(yeni_body, 3)` en yakın komşu aynı
  `kind` ve benzerlik ≥ `CELISKI_ESIK` (bench ile kalibre, başlangıç 0.75) ise araç sonucu
  şunu döner: `"Benzer kayıt var [n_xxx]: '...'. Bunu güncelliyorsan supersedes=n_xxx ile
  tekrar çağır; farklı bir şeyse olduğu gibi kaydedildi."` — kayıt **yine de yazılır**
  (kaçırmamak, temiz olmaktan önemli), model isterse ikinci çağrıyla birleştirir.
- Araç açıklamasındaki "eskisini sil ve güncelini yaz" cümlesi kaldırılır, yerine
  supersede anlatılır.
- `forget` onaylı kalır; supersede onaysız (`safe_actions`'a girer) çünkü hiçbir şey
  silinmiyor.

### 2.5 Testler

- Zincir: A → B → C; `recall` A'yı tohumlasa bile hits'te C var, A yok.
- `series` üçünü de sırayla döner.
- Aktivasyon mirası: A 10 kez kullanılmış, B onu supersede ediyor → B'nin ruh sırası A'nın
  eski sırasıyla aynı.
- Döngü: A supersedes B, B supersedes A elle yazılırsa `recall` sonsuz döngüye girmez.

### 2.6 Kabul

- `yasak_sizinti` (B kümesi) = 0
- `bayat_ruh` = 0
- Ablation: supersede kapalıyken B kümesi precision'ı en az 0.2 düşmeli (yani mekanik
  gerçekten iş yapıyor; yapmıyorsa veri seti yetersizdir, önce onu düzelt).

---

## 4. Faz 3 — Gece: tekrar (replay) ve konsolidasyon

**Sorun:** Night school bugün *eğitim* yapıyor (taban yazıcıyı kişisel korpusla ince
ayarlıyor), *tekrar* yapmıyor. Beynin gece yaptığı asıl iş günün dizilerini yeniden
oynatmak; bundan çıkan şeyler dornick'te hiç yok:

1. Kenarların tamamı "benzer içerik" — **birlikte yaşandı** bağı yok. "Geçen hafta o
   raporu yaparken kullandığım şey neydi" içerik aramasıyla bulunamaz.
2. `uses` sayacı ayrım yapmıyor: yanlış cevaba götüren hatıra da doğru cevaba götüren de
   bir puan alıyor. **Sorumluluk atama** yok.
3. Tekrar önceliksiz: tetik "25 yeni anı birikti mi". Başarısız oturum, açık hedef,
   düzeltme turu rutin oturumla aynı muameleyi görüyor.
4. `_weave` yazım anında donuyor; ağ sıraya bağımlı, erken kayıtlar zayıf bağlı.
5. Eski hatıralar hiç "dokunulmadan" gömülüyor; uzun süre kullanılmayan iz kaybolmuyor
   ama ulaşılmaz oluyor.
6. Episode'lar damıtılmıyor; hafıza büyür ama özetlenmez.
8. Tekrar tamamen geceye bağlı. Beyinde ters tekrar ilk olarak **uyanık** dinlenmede
   gözlendi (Foster-Wilson 2006); görev biter bitmez koşar. Dornick'te araç hatasının
   dersi ertesi geceye kadar yazılmıyor; aynı oturumda aynı hata tekrar edebiliyor.
9. Hiç boşta kalmayan makinede (7/24 gate, sürekli otomasyon) gece hiç gelmez; borç
   sınırsız birikir ve kimse fark etmez.
7. İmza indeksi (`vector.Index`) **tüm** düğümleri RAM'de tutup lineer tarıyor; maliyet
   toplam hafızayla büyüyor. 50k'da 3-5 ms, 500k'da 30-50 ms, ve RAM düğüm sayısıyla
   doğrusal. Beyin bunu aktif kümeyi sınırlı tutarak çözüyor; dornick tutmuyor.

**Tasarım ilkesi:** Gece geçişi altı adımdan oluşur ve **ilk beşi model gerektirmez** —
saf Python + SQLite. Modeli olmayan bir kurulumda bile gece anlamlı iş yapar; damıtma
(6. adım) yalnızca yerel model varsa koşar.

**İş bölümü (3.12 ile birlikte okunur):** Uyanıkken olan şey **yerel ve anlık** — bu
oturumun içinde, sonuç belli olur olmaz. Uykuda olan şey **küresel ve bütünleştirici** —
oturumlar arası, ağın tamamı. Küçültme (Adım 5b) **yalnız** uykuda: öğrenme sürerken
küçültmek o an güçleneni de küçültür (Tononi). Aşağıdaki adımların hangisinin nerede
koştuğu:

| Adım | Uyanık (oturum içi) | Uyku |
|---|---|---|
| 1 Öncelik | — | ✓ |
| 2 İleri tekrar (zaman komşuluğu) | ✓ mevcut oturum, artımlı | ✓ kaçırılan oturumlar |
| 2b Şema tazelemesi | — (oturumlar arası) | ✓ |
| 3 Ters tekrar (sorumluluk) | ✓ **birincil**, sonuç anında | ✓ yalnız uyanıkken koşmamışsa |
| 4 Dikiş | — | ✓ |
| 5a Yeniden örme | — | ✓ |
| 5b Küçültme | **asla** | ✓ |
| 6 Damıtma | — | ✓ |

Yeni modül: `src/dornick/recall/orgu.py`. Giriş noktası:

```python
def gece_gecisi(store: RecallStore, sessions_dir: Path, *, saat, filigran: Path,
                model: Callable | None = None, butce_sn: float = 300) -> GeceRaporu
```

`08_kisisel_dongu.py` bunu **hasattan önce** çağırır; `tanima.belki_baslat` tetikleyicisi
aynı kalır. `GeceRaporu` her adımın sayılarını taşır ve `.dornick/gece.jsonl`'a yazılır —
arayüzdeki "hafıza sağlığı" paneli bunu okur.

### 3.1 Adım 1 — Oturumları önceliklendir (Mattar-Daw: kazanç × ihtiyaç)

Filigrandan beri kapanan her oturum için öncelik puanı:

```python
KAZANC = {"basarisiz": 1.0, "duzeltildi": 1.0, "acik": 0.7, "basarili": 0.4, "rutin": 0.1}
# rutin: hiç araç hatası yok, hedef yok, düzeltme yok, ≤ 3 tur

oncelik = KAZANC[sonuc] * (1 + 0.1 * dokunulan_dugum_sayisi) * (1 + surpriz_ort)
```

`surpriz_ort`: oturumda yazılan yeni hatıraların Faz 4 sürpriz değeri ortalaması (Faz 4
henüz yoksa 0). "İhtiyaç" terimi = `dokunulan_dugum_sayisi` — çok hatıraya değen oturum
gelecekte de değecek. Oturumlar bu puana göre sıralanır; bütçe (`butce_sn`) bitince
kalanlar **bir sonraki geceye devredilir**, atlanmaz. Filigran oturum bazında tutulur.

**Tekrar penceresi:** Filigrandan beri kapanan oturumlar her zaman adaydır. Önceki 7
günün oturumları da adaydır, ama önceliği `× 0.5^gun` ile düşürülür ve yalnızca bütçe
artarsa sıraya girer. Daha eski oturumlar taranmaz — eskinin pekişmesi tarama ile değil
3.2b'deki şema tazelemesiyle olur.

**Geriye dönük yakalama (synaptic tagging and capture):** Bir oturumda sürprizi
`YAKALAMA_ESIK` (başlangıç 0.7) üzerinde bir kayıt varsa, o kaydın ±60 dakikasında
yazılan **düşük sürprizli** kayıtlar da tekrar dizisine tam ağırlıkla alınır ve
`kullanim_ekle(w=+0.3, etiket="yakalandi")` alır. Sıradan sabah notu, öğleden sonraki
büyük hatayla birlikte pekişir; zayıf iz, güçlü olayın yanında durduğu için kurtulur.

Oturum sonucu nereden geliyor: `session.py` oturum günlüğüne kapanışta `sonuc` olayı yazar
— `kos` aracının son test çıktısı (geçti/kırıldı), açık kalan `goal` sayısı, ve
kullanıcının son turda düzeltme yapıp yapmadığı (Faz 2'nin çelişki tespiti tetiklendiyse
ya da `mind_memory save kind=lesson` çağrıldıysa `duzeltildi`). Bu, `transcript()`
tarafından süzülen harness notlarıyla aynı kanaldan gider (`internal=True`).

### 3.2 Adım 2 — İleri tekrar: zaman komşuluğu kenarları

Her öncelikli oturumun günlüğü baştan sona yürünür. Günlükte `open()` edilen, `remember`
ile yazılan ve prime ile enjekte edilen düğümler **oturum içi sırayla** bir dizi oluşturur:
`[n_a, n_b, n_c, ...]`.

```python
for i, a in enumerate(dizi):
    for j in range(i + 1, min(i + PENCERE, len(dizi))):      # PENCERE = 4
        b = dizi[j]
        agirlik = 0.6 * (0.7 ** (j - i - 1))                    # komşu 0.6, iki ötesi 0.42, ...
        _link(a, b, weight=agirlik, reason=f"birlikte kullanıldı ({oturum_id})")
```

`_link` zaten `max(weight)` ile birleştiriyor; aynı çift birçok oturumda peş peşe
gelirse ağırlık **artmalı**, max'ta kalmamalı. Bunun için `_link`'e `birikimli=True`
seçeneği: `weight = min(1.0, eski + yeni * 0.5)`. Aynı gerekçeli kenar 5 oturumda
tekrarlanınca 1.0'a yaklaşır — sıkça birlikte kullanılan şeyler güçlü bağlanır.

Bu kenarlar `recall()` yayılmasında içerik kenarlarıyla aynı yoldan yürür; **prime'a
girmez** (prime hop-0 ile sınırlı, Faz 0'daki kural korunur). Yani zaman komşuluğu
açık `mind_recall`'ı zenginleştirir, otomatik enjeksiyonu kirletmez.

**2b — Şema tazelemesi (eskinin pekişmesi buradan gelir):** Tekrar dizisindeki her düğüm
için, kenar türü fark etmeksizin 1 sıçrama uzaklıktaki komşulara
`kullanim_ekle(w=+0.15 * kenar_agirligi, etiket="sema")` verilir. Bugünün anısına bağlı
eski anı kendiliğinden tazelenir; bağlı olmayan tazelenmez. Bu, beynin "eskiyi tarayıp
pekiştirme" yapmamasının, örtüşen örüntüyü yeniden oynatmasının karşılığıdır (Tse 2007:
şemaya uyan bilgi hızlı konsolide olur). 2 sıçrama ötesine gidilmez; ötesi Faz 1
bozunmasına bırakılır.

### 3.3 Adım 3 — Ters tekrar: sorumluluk atama

**Birincil koşum yeri uyanık tekrardır (3.12.1):** sonuç belli olduğu an, oturum içinde.
Gece yalnızca `sonuc` olayı yazılmış ama ters tekrarı koşmamış oturumları (çökme,
kesinti, eski günlük) toplar. Mekanik iki yerde de aynı fonksiyon: `orgu.ters_tekrar(
store, oturum, sonuc)`. Oturum sonucundan **geriye** yürünür:

```python
if sonuc == "basarili":
    for k, dugum in enumerate(reversed(dizi)):
        pay = 0.8 ** k                                   # sonuca yakın olan çok alır
        kullanim_ekle(dugum, w=+0.5 * pay, etiket="basari")
    if len(dizi) >= 3 and oturumda_arac_dizisi_var:
        remember(arac_dizisi_ozeti, kind="procedure", tags=[proje],
                 links=dizi[-3:], reason="bu yordam şu hatıralarla başarıya götürdü")
        # Aynı başlıklı procedure zaten varsa: supersede değil, kullanım ekle (Faz 2 dışı)

elif sonuc in ("basarisiz", "duzeltildi"):
    for k, dugum in enumerate(reversed(dizi)):
        pay = 0.8 ** k
        kullanim_ekle(dugum, w=-0.3 * pay, etiket="hata")  # negatif ağırlıklı kullanım
    hata_kaynagi = dizi[-1] if dizi else None
    if hata_kaynagi and hata_metni:
        remember(f"{hata_metni} — bu yolda {hata_kaynagi} kullanılmıştı",
                 kind="lesson", links=[hata_kaynagi], reason="bu hatıra hataya götürdü")

elif sonuc == "acik":
    # açık hedef: dokunma; Faz 1 bozunması işini yapsın, ama hedefi 'goal' düğümü
    # olarak recall.db'ye yaz ki bir sonraki oturum "kaldığın yer" diye bulabilsin
    remember(acik_hedef_metni, kind="goal", tags=["acik"], links=dizi[-2:])
```

**Negatif ağırlıklı kullanım** Faz 1'in `taban_aktivasyon` formülünü değiştirir:
`toplam += w * t^-d` — w negatifse aktivasyon düşer. Toplam sıfırın altına inebilir;
`aktivasyon_carpani` sigmoid olduğu için sorun yok, kayıt 0.5'in altına iner ama asla
0 olmaz. Yani hataya götüren hatıra unutulmaz, **geride kalır** ve yanında bir `lesson`
durur. Bu, "yanlış cevaba götüren de bir puan alıyor" sorununun doğrudan çözümü.

Aynı hatıra bir oturumda başarıya, başka oturumda hataya götürdüyse: her ikisi de
`kullanimlar`'da durur, formül toplar; sonuç netleşir. `mind_recall` çıktısında hatıranın
yanında `[3 başarı / 1 hata]` sayacı gösterilir — model "bu bazen yanıltıyor" bilgisini
görür.

### 3.4 Adım 4 — Dikiş: hiç yaşanmamış diziler

Aynı gecenin oturumları arasında ortak düğüm arar:

```python
for (s1, s2) in oturum_ciftleri:
    ortak = set(dizi[s1]) & set(dizi[s2])
    for o in ortak:
        a = dizi[s1] içinde o'dan önceki düğüm
        c = dizi[s2] içinde o'dan sonraki düğüm
        if a and c and a != c and not link_var(a, c):
            _link(a, c, weight=0.3, reason=f"{o} üzerinden dikildi ({s1}→{s2})")
```

Ağırlık düşük (0.3): yaşanmamış bir bağ, yaşanmışın yarısı kadar güvenilir. Sonradan
gerçekten birlikte kullanılırsa Adım 2 ağırlığı artırır; kullanılmazsa Adım 5'teki kenar
bozunması onu düşürür. Saf grafik işi, model yok, 50k düğümde ihmal edilebilir maliyet.

### 3.5 Adım 5 — Eski hatıralara dokunuş + yeniden örme + kenar bozunması

İki ilke: tamamlayıcı öğrenme sistemleri (yeni, eskiyi ezmesin) ve **sinaptik homeostaz**
(Tononi-Cirelli: gündüz güçlenen her şey gece orantılı küçülür; güçlü olan güçlü kalır,
zayıf olan gürültü altına iner ve budanır). Rastgele "eski düğüme dokunuş" **yoktur** —
biyolojide karşılığı yok; beyin yalıtık eski anıyı rastgele koruyarak değil, şemaya bağlı
olduğu için tutar. Yalıtık anı gerçekten soğur (ama silinmez; 3.11).

```python
# (a) yeniden örme: bu gece tekrar/şema/yakalama ile dokunulan düğümler (artımlı)
for d in dokunulanlar:
    adaylar = _seed(d.title + " " + d.body, 6)
    for pos, aday in enumerate(adaylar[:3]):
        _link(d, aday, weight=0.8 - pos*0.15, reason="benzer icerik (yeniden örgü)")

# (b) gece küçültme — TÜM kenarlar, gerekçe ayrımı yok
for kenar in tum_kenarlar:
    kenar.weight *= (1 - EPSILON)                         # EPSILON = 0.02, bench ile kalibre
    if kenar.weight < KENAR_TABAN: sil(kenar)             # KENAR_TABAN = 0.05
# Bu gece Adım 2/2b/3/4 ile güçlenen kenarlar küçültmeden önce büyüdüğü için net kazançlı;
# dokunulmayan kenarlar her gece %2 erir: ~35 gecede yarıya, ~150 gecede tabana.
```

Eski "90 gündür kullanılmayan kenar yarıya" ve "birlikte-kullanıldı bozunmaz" kuralları
kaldırılır; tek formül. Küçültme `UPDATE link SET weight = weight * ?` tek SQL, 50k
düğüm / 300k kenarda < 1 sn. Yeniden örme artımlı: tam ağ 50k'da 250 sn eder, dokunulan
küme birkaç saniye.

Ayrıca **taban yazıcı eğitimine karışım**: `08_kisisel_dongu.py`'deki ince ayar adımı
kişisel korpusa öğretmen korpusundan **en az %30 örnek karıştırır** (bugün karıştırmıyorsa).
Sınav kapısı felaket unutmayı sonradan yakalıyor; karışım baştan önler.

### 3.6 Adım 6 — Damıtma (model gerektirir, yerel model şart)

`tanima.bulut_onayi` kapalı **ve** seçili model hosted ise bu adım atlanır, `GeceRaporu`'na
"damıtma: yerel model yok, atlandı" yazılır. Hosted onayı açıksa mevcut etiketleme
adımıyla aynı kapıdan geçer.

```
kümeler = bu gece tekrar edilen oturumların episode düğümleri
        + Adım 5'te birbirine ≥ 0.6 bağlanan fact grupları
for küme (3..12 düğüm):
    istem = """Aşağıdaki hatıralar birbirine yakın. En fazla 3 kalıcı bilgi çıkar.
               Yalnızca kullanıcının SÖYLEDİĞİ ya da doğrulanmış olanı yaz; tahmin yazma.
               Çelişen ikili varsa 'ÇELİŞKİ: <id1> vs <id2>' satırıyla bildir.
               Her ikili için tek cümle: neden ilişkili? Değilse 'ilişkisiz'.
               Kaynak id'lerini her satırın sonuna yaz."""
    sonuç → kalıcı bilgi satırları:
        remember(body, kind="fact", tags=küme etiketleri ∪ ["damıtık"],
                 links=kaynak_idler, reason="damıtıldı ←")
        kaynak episode'lara: kullanim_ekle(w=-0.2)  (arka plana çekilir, silinmez)
    ilişki satırları → kenar `reason` alanı güncellenir; "ilişkisiz" → weight 0.1
    ÇELİŞKİ satırları → `.dornick/celiskiler.jsonl`; arayüzde gösterilir; sistem kendi
        başına supersede ETMEZ.
```

Damıtık kayıtlar `prime`'a girebilir (episode'lar giremiyor). Kenar gerekçesi
`mind_recall` çıktısında modele gösterilir (`neighbours` reason döndürüyor, `_recall`
aracı yazdırmıyor — yazdır).

### 3.7 Sınav kapısı

Gece geçişi bittikten sonra **yaşam bench'i holdout bölümüyle otomatik koşar**.
`prime_precision` veya `tuzak_sessizlik` geçiş öncesine göre düşerse:
- damıtık düğümler `deleted=1` ("sınavı geçemedi"),
- o gecenin dikiş kenarları silinir,
- zaman komşuluğu, ters tekrar ve dokunuş **geri alınmaz** — bunlar yaşanmış olayın
  kaydı, tahmin değil. (Bunun zararsızlığı ablation ile ayrıca kanıtlanır; kanıtlanamazsa
  kapı onları da kapsar.)

### 3.8 Testler

- Zaman komşuluğu: içerikleri tamamen farklı A ve B aynı oturumda peş peşe açılır →
  gece sonrası `recall(A)` B'yi 1. sıçramada getirir; `select_prime(A)` B'yi **getirmez**.
- Birikim: aynı çift 5 oturumda peş peşe → kenar ağırlığı > tek oturumdakinin 2 katı.
- Ters tekrar: X hatırası başarılı oturumda, Y hatırası başarısız oturumda; gece sonrası
  aynı sorguda X > Y; Y'nin yanında `lesson` düğümü ve `[0 başarı / 1 hata]`.
- Karışık sicil: aynı hatıra 3 başarı 1 hata → aktivasyon, hiç kullanılmamıştan yüksek.
- Dikiş: A→B (s1), B→C (s2) → `recall(A)` C'yi 2. sıçramada getirir; kenar reason'ında
  B'nin id'si var.
- Küçültme: 100 kenar, 50 gece hiç dokunulmadı → hepsi `weight * 0.98^50 ≈ 0.36×`; her
  gece dokunulan 10 kenar tabanın üstünde ve dokunulmayanların üstünde.
- Şema tazelemesi: X'e bağlı Y kullanılır → gece sonrası X'in `kullanimlar`'ında
  `etiket="sema"` girdisi; X'e bağlı olmayan W'de yok.
- Yakalama: sürprizli olayın ±60 dk'sındaki düşük sürprizli kayıt `etiket="yakalandi"`
  alır; 61 dk ötesindeki almaz.
- Sıra bağımsızlığı: 100 düğüm ters sırada yazılıp 10 gece geçirilince, düz sırayla
  ≥ %80 kenar örtüşmesi.
- Bütçe: 50k düğüm + 200 oturumluk gece → `butce_sn=300` içinde biter, devreden
  oturumlar filigranda.
- Kapı: hosted model + onay kapalı → damıtma çağrılmaz; ilk beş adım yine koşar.
- Sahte model (fixture) ile damıtma: 5 episode → ≤ 3 fact, kaynak kenarlı.

### 3.9 Kabul

- `komsuluk_recall` (H) ≥ 0.75 — taban çizgisi (gece yokken) ~0 olmalı; fark mekaniğin
  kendisidir
- `sorumluluk_dogrulugu` (I) ≥ 0.85
- `dikis_recall` (J) ≥ 0.6
- `gomulme_recall` (K) ≥ 0.9 — açık `recall` ile; prime'a girme ölçülmez (3.11'de ayrıca)
- `prime_token` ≥ %15 azalma (damıtma açıksa); damıtma kapalıyken artmaz
- `prime_precision` ve `tuzak_sessizlik` düşmez (komşuluk kenarları prime'a sızmıyor)
- `geri_donus_recall` (G) ≥ 0.7
- `gece_suresi` ≤ 5 dk (50k düğüm, 200 oturum)
- Ablation: Adım 2/2b/3/4/5 ve yakalama tek tek kapatılır; her biri en az bir metriği
  ≥ %3 oynatmalı. Oynatmayan adım kaldırılır.

### 3.10 Uyku dinamiği — kesilme, eşik, kendiliğinden uyanma, döngüler

Gece geçişi bir batch job değil, kesilebilir ve kendi kendine biten bir süreç olarak
tasarlanır. Biyolojik model: ripple tekrarı 50-100 ms'lik binlerce atomik olay (kesilince
yarım kalmaz, kalan ertesi geceye geçer); uyarılma eşiği uyarana göre değişir (kendi
adın en düşük eşikle geçer); uyku iki süreçle başlar ve biter (homeostatik basınç +
sirkadiyen ritim, Borbély); 90 dk'lık döngülerde erken saatler derin uyku, geç saatler
REM ağırlıklıdır.

**Modül:** `src/dornick/recall/uyku.py`. `orgu.gece_gecisi` artık doğrudan çağrılmaz;
`uyku.Uyku` onu döngüler hâlinde sürer.

#### 3.10.1 Atomik birim ve kesilme

- Atomik birim = **tek oturumun tekrarı** (Adım 2 + 3 + 4 o oturum için), tek SQLite
  transaction. Adım 5 dokunuşları düğüm başına, damıtma küme başına atomik.
- `Uyku.uyan(sebep)` çağrılınca: koşan birim tamamlanır (≤ 500 ms sürer; sürmüyorsa
  rollback), sonraki birim başlamaz. **Hiçbir tamamlanmış birim geri alınmaz.**
- Damıtma istisnası: model çağrısı sürerken uyanma gelirse o kümenin çıktısı **atılır**
  (yarım tahmin yazılmaz), küme ertesi geceye devreder. Yaşanmış olayın kaydı (tekrar)
  korunur, tahmin (damıtma) korunmaz; ilke 3.7 ile aynı.
- Devreden iş = **uyku borcu**: filigran oturum bazında zaten var; ek olarak
  `.dornick/uyku_borcu.json`'a hangi fazın (tekrar / dikiş / damıtma) ne kadar eksik
  kaldığı yazılır. Ertesi gece **eksik kalan faz öne alınır** (REM rebound): dün
  damıtmaya gelemediysen bugün damıtma ilk döngüde koşar.

#### 3.10.2 Uyarılma eşiği

| Uyarı | Eşik | Davranış |
|---|---|---|
| Kullanıcı mesaj yazdı / pencereyi öne aldı / sesli komut | **her zaman uyandırır** | koşan birim biter, geçiş durur, `uyandi` olayı |
| Zamanlanmış otomasyon tetiklendi | uyandırmaz | gece geçişi CPU önceliğini bir kademe daha düşürür, otomasyon bitince geri alır |
| Tepsi menüsü açıldı, ayar paneli | uyandırmaz | yalnız durum gösterir ("uyuyor, 12/30") |
| MCP/gate üzerinden dış ajan isteği | uyandırır **yalnızca** istek `recall.db`'ye yazıyorsa | okuma isteği eşik altı: WAL sayesinde okuyucu yazarı beklemez |
| Sistem uyku/hibernasyon | uyandırmaz, **askıya alır** | işletim sistemi dönünce kaldığı birimden sürer |

Eşik sabit değil: kullanıcı geçen 7 gecede 3+ kez gece ortasında geldiyse eşik
**düşer** (hafif uyuyucu: her döngü sonunda etkinlik kontrolü daha sık), hiç gelmediyse
yükselir. Tek parametre (`uyaniklik`), `[0.5, 2.0]` aralığında, `uyku.py`'de.

#### 3.10.3 Uyku basıncı: simüle edilmez, ölçülür

**İlke:** Makine yorgunluk hissetmez ama işlevsel olarak yorulur: gün içinde `remember`
ve `link` ağırlık ekler, küçültme yoktur, kenarlar şişer, `_weave` komşuları
gürültülenir, imza indeksi büyür. 28.08 deneyinin C kolu tam buydu — konsolide edilmemiş
50 ilgisiz kayıt precision'ı 0.54'e düşürdü. Bu, uykusuz hipokampusun daha kötü
kodlamasının (Yoo 2007) birebir karşılığıdır. Dolayısıyla **uyku basıncı hesaplanan
bir his değil, ölçülen bir bozulmadır**: *uykusu geldi = performansı düşmeye başladı*.
Eşik seçilmez, bozulma eğrisinden türetilir.

**Homeostatik basınç S — üç bileşen, bölge başına (Huber 2004: uyku ihtiyacı yerel ve
kullanıma bağlı):**

```python
@dataclass
class Basinc:
    guclenme: float   # son uykudan beri kenar ağırlıklarındaki net artış / toplam ağırlık  (SHY — ana terim)
    borc:     float   # tekrar edilmemiş oturumların Adım 1 öncelik toplamı, normalize
    sicaklik: float   # sıcak düğüm sayısı / hedef (3.11 sicak_oran üst sınırı)

S(bolge) = wG * guclenme + wB * borc + wS * sicaklik        # ağırlıklar bench ile kalibre
S_toplam = max(S(bolge))  ağırlıklı ortalama değil — en yorgun bölge belirler
```

- Bölge = etiket/proje kümesi (`baglam.proje` ya da en sık etiket). Bugün Koru1000'de
  çalışıldıysa basınç orada yüksek, Kobyte'ta düşük. Yerel uyku (3.12.4) bu yüzden "en az
  kullanılan" bölgede değil, **en yüksek basınçlı ama şu an aktif olmayan** bölgede
  çalışır.
- Kinetik adenozin gibi: her plastik olay (`remember`, `link` artışı, `open`) ekler;
  yalnız derin döngüde yapılan iş kadar temizlenir (küçültülen ağırlık, tekrar edilen
  oturum, soğutulan düğüm). Kısa gece borcu sıfırlamaz.
- **Kafein:** kullanıcının "şimdi uyuma" demesi `ESIK_UST`'ü geçici yükseltir
  (`KAFEIN_SAAT = 4`), S'yi düşürmez; süre bitince eşik normale döner ve birikmiş
  basınç rebound yapar. Arayüz dürüst gösterir: "ertelendi, basınç 0.8".

**Eşik türetme deneyi (Faz 0 bench'ine eklenir, `esik_egrisi`):** Yaşam senaryosunda
gece geçişi **kapatılır**, S gün gün artarken her gün `prime_precision` ve yeni kaydın
`_weave` komşu doğruluğu (komşuların `beklenen` kümede olma oranı) ölçülür. Bozulmanın
başladığı S değeri (taban çizgisinden %5 düşüş) `ESIK_UST` olur; `ESIK_ALT =
ESIK_UST / 3`. Bu değerler `uyku.py`'de sabit olarak durur, yanına türetildiği bench
koşusunun tarihi yazılır. Eğri `docs/charts/basinc-bozulma.md`'ye commit'lenir.

**Sirkadiyen C — histogram + zeitgeber:**

```python
ritim(t) = kullanıcının t saatinde aktif olma olasılığı    # 7x24 histogram, son 60 gün, Laplace
```

Histogram tek başına serbest koşan bir osilatördür; insan saati de ışık olmadan kayar.
Onu her gün yeniden kuran dış sinyaller (3.10.9) olmadan bayatlar. **Melatonin
karşılığı:** tahmini boşta penceresine `ONCEDEN_DK = 30` kala `ESIK_UST` kademeli
düşer (pencere anında ×0.7); uykuya dalış kolaylaşır, zorlanmaz.

Yeni kurulumda düz önsel (`0.3`); ilk iki hafta yalnız zeitgeber'larla karar verilir,
döngüler kısa tutulur.

**Ne simüle edilmez:** uykululuk hissi, uyku kalitesi, uykusuzluğun bilişsel bozulması.
Sistem "yorgunum" demez; "küçültülmemiş güçlenme %34, precision düşmeye başladı" der.
Bozulma kendiliğinden olur ve bench onu ölçer; işimiz taklit değil, gidermek.

#### 3.10.4 Döngüler

Gece `DONGU_DK = 15` dakikalık döngülere bölünür (biyolojideki 90 dk'nın ölçekli hâli;
bench'te kalibre). Her döngünün fazı gecenin kaçıncı döngüsü olduğuna bağlı:

| Döngü | Ağırlık | Ne koşar |
|---|---|---|
| 1-2 | derin | Adım 1 (öncelik), Adım 2-3 (ileri/ters tekrar), öncelikli oturumlar |
| 3-4 | derin → hafif | kalan tekrarlar, Adım 4 (dikiş), Adım 5 (dokunuş + örgü) |
| 5+ | REM | Adım 6 (damıtma), kenar gerekçeleri, taban yazıcı ince ayarı |

Her döngü sonunda: etkinlik kontrolü (eşik), basınç yeniden hesaplanır, `ritim` bakılır.
Erken kesilen gece damıtmayı kaybeder, tekrarı değil; istenen öncelik bu. Uyku borcu
varsa ertesi gece döngü tablosu **borçlu faz öne alınarak** yeniden sıralanır.

#### 3.10.5 Olay akışı (arayüz için)

Her adım `events.py` üzerinden olay yayınlar; `recall()` izinin aktığı kanalın aynısı:

```
uyku.basladi        {basinc, tahmini_uyanma, dongu_sayisi}
uyku.dongu          {no, faz}
tekrar.ileri        {oturum, dizi: [id...], kenarlar: [(a,b,w)]}
tekrar.geri         {oturum, sonuc, paylar: [(id, w)]}
dikis               {a, b, uzerinden, oturumlar}
dokunus             {id}
damitma             {kaynaklar: [id...], yeni: id}          # REM
uyku.uyandi         {sebep, dongu, tamamlanan, devreden, borc}
uyku.bitti          {sebep: "basinc" | "ritim", rapor}
```

Olaylar `.dornick/gece/<tarih>.jsonl`'a da yazılır; sabah "dün gece" yeniden
oynatılabilir (Faz 6).

#### 3.10.6 Testler

- Kesilme: 30 oturumluk gece, 12. oturumun ortasında `uyan("kullanici")` → 12 tamamlanmış
  (ya da 11 + rollback), 18 devreden, `kesinti_gecikmesi` < 500 ms, veritabanı tutarlı
  (`PRAGMA integrity_check`).
- Yarım damıtma: model çağrısı sırasında uyanma → o kümeden düğüm yok, küme borçta.
- Borç önceliği: dün damıtma eksik → bugün 1. döngü REM.
- Eşik: `uyan("otomasyon")` durdurmaz; `uyan("kullanici")` durdurur; gate okuma isteği
  durdurmaz, yazma isteği durdurur.
- Ritim: 60 günlük sentetik günlük (hafta içi 09-18) → `ritim(Salı 08:45) >= 0.5`,
  `ritim(Pazar 03:00) < 0.1`; gece geçişi 08:30'da kendiliğinden biter.
- Atalet: gece ortasında oturum açılır → ruh gece sonrası aktivasyonla yüklenmiş.
- OS askıya alma simülasyonu: saat 6 saat ileri atlar → geçiş kaldığı birimden sürer,
  ritim yeniden değerlendirilir (sabah olduysa uyanır).

#### 3.10.7 Kabul

- `kesinti_kaybi` = 0, `yarim_damitma` = 0, `kesinti_gecikmesi` p95 ≤ 500 ms
- `ritim_isabeti` ≥ 0.9 (M kümesi)
- `atalet` = 0
- Kesilmeyen gecede H/I/J/K sonuçları 3.9 ile aynı (uyku katmanı iş kalitesini
  değiştirmez, yalnız zamanlamasını)
- %30'da kesilen gecelerin **ertesi gecesi** H/I/J/K, hiç kesilmemiş tek geceyle eşit
  (borç gerçekten ödeniyor)
- `esik_egrisi` deneyi commit'li; `ESIK_UST` ve `ESIK_ALT` o eğriden türetilmiş ve
  kaynağı yorumda
- Narkolepsi testi (3.10.8) geçiyor: eşik çevresinde salınım yok

#### 3.10.8 Uyku anahtarı: dört durum, histerezis, oreksin

Saper'in flip-flop modeli: uyku ve uyanıklık birbirini karşılıklı baskılayan iki kararlı
durum; arası yok, geçiş ani. Oreksin anahtarı uyanıkta sabitler; oreksin yoksa
(narkolepsi) anahtar dakikalar içinde ileri geri atar. Dornick'te oreksin = kullanıcı
etkinliği; histerezis = iki ayrı eşik. Tek eşikle sistem, basınç eşiğin çevresinde
dolaşırken dakikada bir uyuyup uyanır.

```
UYANIK   → UYKULU   : wS·S + wC·(1 − ritim(simdi+1sa)) ≥ ESIK_UST
                      ve kullanıcı ≥ BOSTA_DK etkileşimsiz
UYKULU   → UYUYOR   : UYKULU'da ≥ UYKULU_DK (2 dk) kaldı  ve oreksin = 0
UYUYOR   → UYANIYOR : uyan(sebep)  ya da  S ≤ ESIK_ALT  ya da  ritim(simdi+ONCEDEN_DK) ≥ 0.5
UYANIYOR → UYANIK   : ruh yeniden yüklendi, imza indeksi güncel   (atalet ≤ 2 sn)
her durum → UYANIK  : oreksin = 1 (kullanıcı doğrudan etkileşim) — koşulsuz
```

- **UYKULU** insandaki akşam uyuşukluğudur: henüz uyumuyor, hazırlanıyor. Sıcak imza
  indeksi RAM'e alınır, Adım 1 önceliklendirmesi önden yapılır, oturum listesi hazırlanır,
  talamus halkası "uykulu" görünür. Kullanıcı geri gelirse atılan iş sıfır maliyetli
  (salt okuma). UYKULU'dan UYANIK'a dönüş sayılmaz; bu, arayüzde "uyumaya çalıştı ama
  vazgeçti" olarak gösterilmez.
- **Oreksin = 1 iken hiçbir uyku türü koşmaz** — mikro-uyku dahil. Kullanıcı aktifken
  sistem kesinlikle uyanıktır; 3.12'deki uyanık tekrar uyku değildir, koşar.
- **UYANIYOR** atalet aşamasıdır: ruh yeniden yüklenir, indeks gece değişikliklerini
  alır, sonra oturum kabul edilir. 2 sn'yi aşarsa oturum yine açılır ama ruh bir sonraki
  turda tazelenir (kullanıcı bekletilmez).

**Bekçi:** mevcut `tanima.gozcu` (15 dk yoklama, tek ölçüt) yerine `uyku.Bekci`:
- 30 sn'de bir S ve C'yi örnekler, durum makinesini sürer.
- OS olaylarına abone (3.10.9); olay geldiğinde beklemez.
- Her geçişi `.dornick/uyku_gunlugu.jsonl`'a yazar: `{ts, eski, yeni, S: {...}, C, sebep}`.
- Kullanıcı komutları: `uyu` (yatağa git — ESIK_UST yok sayılır, oreksin=0 varsayılır,
  ilk etkileşimde yine uyanır), `şimdi uyuma` (kafein), `ne kadar yorgunsun` (S
  bileşenleri bölge başına).
- `tanima.belki_baslat`'ın 20 saatlik tazelik sigortası kalır: S sıfır olsa da günde bir
  kısa döngü — ama yalnız oreksin=0 iken.

**Narkolepsi testi:** S, `ESIK_UST` ± %5 bandında 2 saat boyunca rastgele gezdirilir,
kullanıcı etkileşimsiz → durum geçişi sayısı ≤ 2. Tek eşikli kontrol uygulamasında bu
sayı onlarcadır; test onu yakalar.

#### 3.10.9 Zeitgeber'lar: makinenin ışığı

İnsan saati retinadaki melanopsin hücreleriyle her gün ışığa yeniden kurulur. Makinenin
ışığı kullanıcı varlığının OS düzeyindeki izleridir. Her biri histogramı günceller
(`ritim` öğrenmesi) **ve** anlık karara girer (oreksin ya da eşik kaydırma):

| Sinyal | Kaynak (Windows; diğer OS'ler Faz 5 platform işinde) | Etki |
|---|---|---|
| Oturum kilidi / kilit açma | `WTSRegisterSessionNotification` | kilit → oreksin=0, BOSTA sayacı başlar; açma → oreksin=1 |
| Klavye / fare etkinliği | son giriş zamanı (`GetLastInputInfo`) | oreksin; 3.12.2'nin 20 sn boşluğu da buradan |
| Kapak kapanması / OS uykusu | power events (`WM_POWERBROADCAST`) | askıya alma (3.10.2); dönüşte saat sıçraması → ritim yeniden değerlendirilir |
| Pil / şebeke | power status | pilde: derin döngü koşmaz, yalnız UYKULU hazırlığı; şebekede normal |
| Rahatsız etme modu | Focus Assist durumu | eşik ×0.8 (kullanıcı "beni rahatsız etme" dedi = gece sinyali) |
| Saat dilimi değişimi | sistem TZ | histogram yerel saate göre kaydırılır, 3 gün boyunca güven düşürülür (jet lag) |
| Takvim (bağlıysa) | connector | "toplantı" = oreksin=0 ama kısa pencere; "tatil" = uzun pencere |

Zeitgeber olmadan histogram serbest koşar ve bayatlar; histogram olmadan zeitgeber yalnız
anı görür. İkisi birlikte: histogram "genelde ne zaman", zeitgeber "şu an gerçekten".

#### 3.10.10 Temizlik: derin uykuda yapılan ve yalnız orada yapılabilen işler

Glimfatik karşılık (Xie 2013: uykuda hücreler arası boşluk açılır, atık yıkanır — alan
uyanıkken yoktur). SQLite'ın "alan gerektiren" işleri de uyanıkken yapılamaz ya da
yapılmamalıdır:

| İş | Neden uykuda | Döngü |
|---|---|---|
| `PRAGMA wal_checkpoint(TRUNCATE)` | yazar yokken tam checkpoint; WAL dosyası küçülür | ilk derin |
| `INSERT INTO node_fts(node_fts) VALUES('optimize')` | FTS b-tree birleştirme, I/O yoğun | ilk derin |
| `VACUUM` | özel kilit ister; uyanıkken imkânsız | haftada bir, derin, S en düşükken |
| soğuk düğümlerin `sig` blob'unu RAM indeksinden düşürme (3.11) | indeks yeniden kurulur | ilk derin |
| transcript ve episode önbelleklerini boşaltma | RAM | ilk derin |
| `.dornick/gece/` eski günlüklerini sıkıştırma (>30 gün) | disk | haftalık |
| yedek (`backup_to`) | tutarlı anlık görüntü | gece başı, her zaman |

Hiçbiri UYANIK, UYKULU ya da mikro-uykuda koşmaz. Yerel uykuda yalnız önbellek
boşaltma koşar (kilit istemez).

**Testler:** VACUUM uyanıkken çağrılırsa `uyku.py` reddeder (assert); checkpoint sonrası
WAL boyutu < 1 MB; uyanma sinyali VACUUM sırasında gelirse VACUUM biter (kesilemez,
SQLite garantisi) ve `kesinti_gecikmesi` bütçesi bu tek iş için `VACUUM_SN` ile ayrı
ölçülür — haftalık VACUUM S en düşükken ve ritim en uzakken planlanır ki bu gecikme
kullanıcıya denk gelmesin.

### 3.11 Büyüme: sıcak/soğuk indeks ve sistemler konsolidasyonu

**Sorun (7. madde):** Hafıza büyüdükçe imza taraması ve RAM doğrusal büyüyor. Beynin
cevabı arşivi büyütmek değil, **aktif kümeyi sınırlı tutmak**: hipokampusa bağımlı taze
anılar sıcak, kortekse taşınmış eskiler soğuk; soğuk anı ipucuyla hâlâ uyanır ama
kendiliğinden gelmez.

#### 3.11.1 Sıcak / soğuk

Her düğümün Faz 1 aktivasyonu `B` gece sonunda hesaplanır ve `node.sicak` (INTEGER, 0/1)
yazılır:

```
sicak = 1  if B >= SOGUK_ESIK  or  superseded_by == '' and created < 7 gün   # yeni her zaman sıcak
       else 0
```

- **İmza indeksi yalnız sıcak düğümleri tutar.** `_load_index` `WHERE deleted=0 AND
  sicak=1`; `remember()` yeni düğümü indekse ekler (yeni = sıcak); gece geçişi soğuyanları
  `index.drop`, ısınanları `index.add` eder. Tarama maliyeti artık aktif hafızayla
  büyür, toplamla değil.
- **FTS her şeyi kapsar** (soğuk dahil). `_seed_literal` değişmez; soğuk düğüm birebir
  kelimeyle her zaman bulunur — "ipucuyla uyanır". `_seed_signature` yalnız sıcaktan
  gelir — "kendiliğinden gelmez".
- `select_prime`: soğuk düğüm prime'a **giremez** (skoru aktivasyon çarpanıyla zaten
  düşük; ayrıca açık kural, çünkü genç-hafıza istisnası onu geçirebilirdi).
- `mind_recall` çıktısında soğuk düğüm `(soğuk)` işaretiyle gelir; `open()` soğuk düğümü
  açınca kullanım ekler → ertesi gece ısınır. Beyindeki "hatırlayınca yeniden
  hipokampusa döner" karşılığı.
- `SOGUK_ESIK`: bench ile kalibre. Hedef, 90 günlük yaşam senaryosunda sıcak oranın
  %10-30 arasında kalması (`sicak_oran` metriği). Oran %50'yi geçiyorsa eşik düşük,
  %5'in altındaysa yüksek.

#### 3.11.2 Sistemler konsolidasyonu: episode'un soğuması

Damıtılmış (Adım 6) bir episode'un kaynak kenarı olan damıtık `fact` sıcakken episode'un
kendisi `kullanim_ekle(w=-0.2)` ile arka plana çekiliyordu; buna ek olarak damıtılmış
episode **damıtmadan 14 gün sonra koşulsuz soğur** (`sicak=0`, aktivasyona bakılmaz).
Ayrıntı diskte, FTS'te ve `series`'te durur; özet sıcakta yaşar. Damıtılmamış episode
normal kurala tabidir.

#### 3.11.3 Ne sınırlanmaz

- Düğüm sayısına üst sınır **yok**. Disk büyür; SQLite bunu taşır.
- Soğuk düğüm silinmez, mezar taşı almaz, `series`'ten düşmez.
- FTS indeksi büyür; bu kabul edilir — B-tree, lineer tarama değil. 1M düğümde FTS5
  sorgusu hâlâ milisaniye düzeyinde (P kümesi ölçer).

#### 3.11.4 Testler

- 200k düğüm, %95 soğuk: `_load_index` yalnız ~10k imza yükler; `recall()` p95, 20k
  düğümlük tamamen sıcak hafızanınkinin ≤ 1.5 katı.
- Soğuk düğüm birebir kelimeyle `recall`'da bulunur; eşanlamla (yalnız imza yolu)
  bulunmaz — bu **istenen** davranış, test onu doğrular.
- Soğuk düğüm `open()` edilir → ertesi gece `sicak=1`, imza indeksinde.
- Damıtılmış episode 14. gecede soğur; damıtık fact sıcak kalır.
- Genç hafıza istisnası soğuk düğümü prime'a sokamaz.

#### 3.11.5 Kabul

- `buyume_p95` ≤ 1.5, `buyume_ram` ≤ 2 (P kümesi)
- `sicak_oran` 0.10-0.30 (90. gün)
- K kümesi: yalıtık kayıt prime'a girmez **ve** açık recall'da bulunur; şemalı kayıt
  prime'a girebilir
- `sema_tazeleme` > 0, `yakalama` > 0 (N, O kümeleri)
- H/I/J sonuçları 3.9 ile aynı (sıcak/soğuk ayrımı tekrar kalitesini değiştirmez)

### 3.12 Uyanık tekrar, mikro-uyku ve yerel uyku

**Biyolojik gerekçe:** Sharp-wave ripple tekrarı uykuya özgü değil; uyanık dinlenme
anlarında (görev bitince, ödülden hemen sonra) da oluşur ve ters tekrar ilk kez orada
gözlendi. Uyanık tekrar hızlı öğrenme ve planlama içindir; uyku tekrarı geniş
entegrasyon. Aşırı yorgun beyinde kortikal nöron grupları uyanıkken tek tek çevrimdışı
olur ("yerel uyku", Vyazovskiy 2011). "Yıllarca uyumayan insan" yoktur — paradoksal
insomnia hastaları uyuduklarının farkında değildir, mikro-uykular vardır — ama **hiç
boşta kalmayan makine** vardır ve tasarım onu düşünmek zorundadır.

**Modül:** `src/dornick/recall/uyanik.py`. `orgu.py`'deki fonksiyonları çağırır; kendi
mekaniği yoktur, yalnız **ne zaman** koşacağına karar verir.

#### 3.12.1 Uyanık ters tekrar (sonuç anında)

Tetik: oturum içinde bir **sonuç olayı** oluşur oluşmaz —
- `kos` aracı test çıktısı döndü (geçti / kırıldı),
- araç hatası (non-zero exit, exception),
- kullanıcı düzeltmesi (Faz 2 çelişki tespiti ya da `mind_memory save kind=lesson`),
- hedef `done`/`dropped` oldu.

O anda `orgu.ters_tekrar(store, dizi_su_ana_kadar, sonuc)` koşar: kullanım ağırlıkları
dağıtılır, `lesson`/`procedure` **hemen** yazılır. Kullanıcı aynı oturumda dersi görür;
model bir sonraki turda `mind_recall` ile ona ulaşabilir. Oturum günlüğüne
`ters_tekrar_kostu: true` yazılır; gece o oturumu atlar.

Bütçe: tek oturumun ters tekrarı < 50 ms (dizi ≤ 200 düğüm). Tur arasına sığar; sığmazsa
(`> 200 ms`) yarıda kesilmez, arka plan thread'inde biter — tur bloklanmaz.

#### 3.12.2 Uyanık ileri tekrar (tur arasında)

Tetik: kullanıcı son turdan beri `BOSLUK_SN = 20` saniyedir yazmıyor (yazıyor/düşünüyor).
Mevcut oturumun **o ana kadarki dizisi** için Adım 2 zaman komşuluğu kenarları artımlı
yazılır (son koşumdan beri eklenen düğümler için). Oturum sonu kapsülü (mevcut kod) böylece
tek seferlik değil, artımlı olur; oturum çökerse kenarlar çoktan yazılmıştır.

Yapılmayanlar: şema tazelemesi (oturumlar arası), dikiş, küçültme, damıtma. Bunlar
uyanıkken **koşmaz**.

#### 3.12.3 Mikro-uyku (gün içi boşluk)

Tetik: kullanıcı `MIKRO_BOSTA_DK = 5` dakikadır etkileşimsiz **ve** basınç > 0 **ve**
gece uykusu 12 saattir gelmemiş. Tek döngü (3.10.4'teki derin faz), en fazla
`MIKRO_DK = 2` dakika:
- kaçırılmış ters tekrarlar,
- Adım 2b şema tazelemesi (bugünün düğümleri için),
- dikiş.
Damıtma ve küçültme yok. Uyarılma eşiği gece uykusundakiyle aynı (kullanıcı her zaman
uyandırır). Mikro-uyku borcu azaltır ama sıfırlamaz; gece yine gelir.

#### 3.12.4 Yerel uyku (hiç uyumayan makine)

Tetik: uyku borcu `BORC_ESIK`'i (bench ile kalibre; başlangıç "48 saattir gece yok ve
≥ 50 tekrar edilmemiş oturum") aştı **ve** boşta pencere hiç açılmıyor (7/24 gate,
sürekli otomasyon).

Sistem uyanıkken, en düşük CPU önceliğinde, **ağın soğuk bölgesinde** çalışır:
- Kapsam: son 7 gündür hiçbir oturumda dokunulmamış düğümler ve yalnız onların
  arasındaki kenarlar. Aktif bölgeye (son 7 gün) **dokunulmaz** — öğrenme sürerken
  küçültme yasağı böylece korunur: küçültülen şey o an öğrenilmeyen şeydir.
- Yapılanlar: küçültme (5b) yalnız o kenarlarda, soğutma (3.11.1) yalnız o düğümlerde,
  damıtılmış episode soğutma.
- Yapılmayanlar: tekrar, şema, dikiş, damıtma — bunlar aktif bölgeyi ister.
- Bölge sınırı her 10 dakikada yeniden hesaplanır; dokunulan düğüm anında kapsam dışına
  çıkar.

Arayüzde (Faz 6) yerel uyku farklı gösterilir: bütün hipokampus kararmaz, yalnız soğuk
halkanın bir dilimi "uyuyor" desenine geçer. Kullanıcı sistemin "yorgun" olduğunu görür;
sabah raporu yerine "3 gündür gece uykusu yok, yerel uykuyla idare ediyor" uyarısı.

#### 3.12.5 Değişmez

Küçültme aktif bölgede **yalnız** gece uykusunda koşar. Yerel uyku bunu soğuk bölgeyle
sınırlayarak dolanır; mikro-uyku hiç yapmaz. Bu, "bir mekanik neden uykuya bağlı"
sorusunun tek gerçek cevabıdır: girdi sürerken küçültme güvenli değildir. Geri kalan her
şey uyanıkken de koşabilir ve koşar.

#### 3.12.6 Bench eklemeleri

| Küme | Ne test eder | Asgari olay |
|---|---|---|
| **Q. Anında ders** | Araç hatası → aynı oturumda 2 tur sonra aynı konuda sor; `lesson` açık recall'da gelmeli, gece beklenmeden | 10 oturum |
| **R. Uykusuz makine** | 14 gün boyunca gece uykusu hiç gelmez (boşta pencere yok, `uyan("otomasyon")` sürekli); mikro-uyku ve yerel uyku koşar; 14. günde H/I metrikleri, normal uyuyan kontrolün ≥ %80'i; kenar sayısı kontrolün ≤ 1.3 katı (şişme sınırlı) | 14 gün × 2 kol |
| **S. Aktif bölge dokunulmazlığı** | Yerel uyku sırasında aktif oturumda güçlenen kenar, yerel uyku bittiğinde küçülmemiş | 20 kenar |

Metrikler:

| Metrik | Tanım | Yön |
|---|---|---|
| `ders_gecikmesi` | Q kümesinde hatadan `lesson`'ın recall'da görünmesine kadar geçen tur sayısı | ↓ (hedef ≤ 1) |
| `uykusuz_kayip` | R kümesinde uykusuz kolun H/I ortalaması / kontrol | ↑ (hedef ≥ 0.8) |
| `uykusuz_sisme` | R kümesinde kenar sayısı oranı | ↓ (hedef ≤ 1.3) |
| `aktif_bolge_ihlali` | S kümesinde küçülen aktif kenar sayısı | 0 |
| `tur_bloklama` | uyanık tekrarın tur gecikmesine kattığı p95 ms | ↓ (bütçe: 50 ms) |
| `esik_egrisi` | gece kapalıyken S'ye karşı precision/komşu doğruluğu eğrisi; `ESIK_UST` buradan | rapor + türetilen sabit |
| `salinim` | narkolepsi testinde durum geçişi sayısı (2 saat, eşik bandı) | ↓ (hedef ≤ 2) |
| `yanlis_uyku` | kullanıcı aktifken (oreksin=1) başlayan herhangi bir uyku türü sayısı | 0 |

#### 3.12.7 Testler

- Sonuç olayı → ters tekrar aynı turda; `ters_tekrar_kostu` işaretli; gece o oturumu
  atlıyor (çift sayım yok: `kullanimlar`'da tek `basari`/`hata` girdisi).
- Tur arası ileri tekrar artımlı: 3 turluk oturumda 2. turdan sonra yazılan kenar 3.
  turdan sonra yeniden yazılmıyor (idempotent).
- Mikro-uyku damıtma çağırmıyor, küçültme çağırmıyor (mock ile).
- Yerel uyku: aktif bölgedeki hiçbir kenarın ağırlığı değişmiyor; soğuk bölgede
  küçülüyor; bölge sınırı dokunulan düğümü 10 dk içinde dışarı atıyor.
- Uyanık tekrar `tur_bloklama` bütçesini aşınca thread'e düşüyor, tur bloklanmıyor.

#### 3.12.8 Kabul

- `ders_gecikmesi` ≤ 1, `tur_bloklama` p95 ≤ 50 ms
- `uykusuz_kayip` ≥ 0.8, `uykusuz_sisme` ≤ 1.3, `aktif_bolge_ihlali` = 0
- Normal uyuyan kolda H/I/J/K/N/O sonuçları 3.9 ve 3.11.5 ile aynı (uyanık katman gece
  kalitesini değiştirmez; yalnız erken getirir)
- Ablation: uyanık ters tekrar kapalıyken `ders_gecikmesi` geceye kadar çıkmalı (mekanik
  gerçekten iş yapıyor)

---

## 5. Faz 4 — Kodlama gücü (sürpriz)

> Faz 7 geldiğinde bu fazın `surpriz` ölçümü `odul.bilgi` bileşenine erir ve `guc`
> formülü `0.4 + 0.6 * |odul|` olur. Faz 4 yine de önce ve ayrı yapılır: tek bileşenli
> hâli ölçülmeden çok bileşenli hâlinin neyi eklediği bilinemez.

**Sorun:** Her kayıt aynı ağırlıkla doğuyor; "aynı şeyi 5 kez kaydettim" beşinci kayıt da
tam güçte.

### 4.1 Mekanik — `remember()` içinde

```python
komsular = self._seed(f"{title} {body}"[:400], 3)      # zaten _weave için çekiliyor
en_yakin = komsular[0].score if komsular else 0.0
surpriz = 1.0 - en_yakin                                # 0 = bilinen, 1 = yeni
guc = 0.4 + 0.6 * surpriz                               # asla 0 değil
if kind == "lesson": guc = min(1.0, guc * 1.5)           # hatadan öğrenme ağır basar
if supersedes: guc = 1.0                                 # düzeltme her zaman tam güç
```

`guc`, `kullanimlar` listesinin ilk girdisine `w` olarak yazılır
(`[{"t": created, "w": guc, "etiket": "yazildi"}]`); `taban_aktivasyon` zaten ağırlıklı
toplam alıyor (Faz 1). Şema değişmez.

### 4.2 Testler

- Aynı gövde 5 kez `remember` → 5. kaydın başlangıç aktivasyonu 1.'nin ≤ %50'si.
- `lesson` > `fact` aynı gövde için.

### 4.3 Kabul

- C kümesi (gürültü) `yasak_sizinti` düşer veya sabit; A kümesi recall düşmez.
- Ablation ile tek başına ölçülür; fayda < %3 ise **faz geri alınır** (karmaşıklığa
  değmez — bunu belgelemek de sonuçtur).

---

## 6. Faz 5 — Bağlam bonusu

**Sorun:** `session` alanı var, arama kullanmıyor. "SCADA'dayken borsa notu" sızıntısı
sayı-silme ve gövde-sayma hileleriyle bastırılıyor.

### 5.1 Şema

```sql
ALTER TABLE node ADD COLUMN baglam TEXT NOT NULL DEFAULT '{}';
-- {"proje": "koru1000", "dizin_kok": "D:/Projects/koru1000", "saat_dilimi": "sabah"}
```

`desktop.py` zaten `set_project` tutuyor; `Mind.remember` yazım anındaki bağlamı
otomatik ekler. Model doldurmaz.

### 5.2 Mekanik

`select_prime` ve `recall`'a `baglam` parametresi (mevcut oturumunki). Skor:
`skor * (1 + BAGLAM_BONUS * ortak_alan_sayisi / 3)`, `BAGLAM_BONUS` başlangıç 0.15,
bench ile kalibre. Bağlamı boş olan eski kayıtlar bonus almaz ama ceza da almaz.

### 5.3 Kabul

- E kümesi (bağlam çakışması) precision ≥ 0.85
- Bonus açıkken `_without_numbers` ve zengin-sorgu ≥2-gövde kuralı **kapatılıp** bench
  koşulur; sonuç eşit veya daha iyiyse o hileler sadeleştirilir (kod borcu ödeme fırsatı).

---

## 6b. Faz 6 — Beyin görünümü: bölgeler ve gece animasyonu

**Amaç:** Hafıza mekaniğini kullanıcıya, olduğu gibi, gerçek zamanlı göstermek.
Mevcut beyin görünümü tek bir düğüm ağı; `recall()` izini canlandırıyor. Bu faz ağı
**bölgelere** ayırır ve gece olaylarını (3.10.5) aynı kanaldan oynatır.

**Dürüstlük sınırı:** Bölgeler bir metafordur. Arayüz "hipokampus" der ama biyolojik
sadakat iddia etmez; her bölgenin tooltip'inde hangi kod parçasını temsil ettiği yazar.
Eşleme tutarlı olduğu için öğreticidir, doğru olduğu için değil.

### 6.1 Bölge eşlemesi

| Bölge | Temsil ettiği | Görsel | Kaynak |
|---|---|---|---|
| **Hipokampus** | sıcak düğümler (`sicak=1`) ve kenarları: indeks ve çağrışım | mevcut ağ görünümü, merkezde; gece küçültmesinde bütün kenarlar bir an incelir | `store.links()`, `recall()` izi |
| **Soğuk depo** | `sicak=0` düğümler: FTS'ten ulaşılır, kendiliğinden gelmez | hipokampusun çevresinde soluk halka; sayı rozeti ("41.200 soğuk"); soğuk düğüm `open()` edilince halkadan merkeze süzülür (ısınma) | `node.sicak` |
| **Korteks** | uzak model: dünya bilgisi, dil; **yazılamaz** | koyu gri, donmuş, hiç canlanmaz; üstüne gelince "bu bölge donmuş: uzak model" | yok |
| **Korteks yaması** | taban yazıcı (10.8M), plastik tek parça | korteks üstünde küçük renkli yama; gece ince ayarında nabız atar; sınavı geçince kalıcı renk değişimi | `tanima.durum()` |
| **Prefrontal** | hedef yığını ve açık `goal` düğümleri | üst şerit; aktif hedefler yanar, `done` sönerek düşer | `Mind.goals()` |
| **Amigdala** | sürpriz / önem işaretleyici (Faz 4 `guc`, Adım 1 öncelik) | küçük düğüm; yüksek sürprizli kayıt yazılırken parlar | `remember()` olayı |
| **Talamus** | uyarılma kapısı: eşik, basınç, ritim, durum makinesi | halka gösterge: basınç dolum çubuğu (bölge başına dilimli), ritim saati, `uyaniklik`; dört durum ayrı desenle (uyanık / uykulu / uyuyor / uyanıyor); kafein ertelemesi sayaçlı | `uyku.Bekci` |
| **Beyin sapı** | tetikleyici / zamanlayıcı (`uyku.Bekci`) | tek nabız çizgisi | `uyku` |
| **Kimlik paneli** | `.dornick/kimlik.md` — anlatı kimliği | ayrı sekme; her cümle tıklanınca kanıt düğümleri hipokampusta yanar; "itiraz et" düğmesi | Faz 7.5 |
| **Mizaç paneli** | beş eksen (yenilik, sonuç, sosyal, sebat, temkin) | ayarlarda eksen başına üç işaret: model tabanı (ölçülen), hedef (öğrenilen/elle), ulaşılan; "Bu model böyle geldi" notu; model değişince taban işareti kayar, hedef kalır | Faz 7.2 |
| **Dünya haritası** | `world` düğümleri | hipokampus içinde ayrı renk; doğrulanmamış olanlar soluk, `dogrulama` yaşı tooltip'te | Faz 7.3 |

Bölge yerleşimi sabit bir şablon (SVG); düğümler hipokampus alanına force-layout ile
yerleşir, diğer bölgeler gösterge. Mobil/dar pencerede bölgeler yığılır.

### 6.2 Gece animasyonu

Olay → görsel eşlemesi, `recall()` izinin canlandırıldığı mevcut mekanizmayla aynı sıra
ve zamanlama mantığı:

| Olay | Görsel |
|---|---|
| `uyku.basladi` | hipokampus kararır, talamus halkası "uyuyor" moduna geçer, tahmini uyanma saati yazılır |
| `uyku.dongu` | halka üstünde döngü numarası; faz rengi (derin: mavi, hafif: teal, REM: mor) |
| `tekrar.ileri` | oturum dizisinin düğümleri **sırayla ileri** yanar (ripple), aralarına beliren kenarlar çizilir |
| `tekrar.geri` | aynı dizi **tersten** yanar; başarıda yeşil, hatada kırmızı; pay büyüklüğü parlaklık |
| `dikis` | iki uzak düğüm arasına **noktalı** kenar çizilir, ortadaki düğüm bir an parlar |
| `dokunus` | uzak, soluk bir düğüm hafifçe yanıp söner |
| `damitma` | kaynak düğümler birbirine çekilir, aralarından yeni düğüm doğar (REM fazı) |
| `uyku.uyandi` | talamus flaşı, animasyon **olduğu yerde durur** (kalan dizi soluk kalır), özet rozeti: "12/30 tekrar edildi · 18 devretti · sebep: kullanıcı" |
| `uyku.bitti` | halka "uyanık"; sabah raporu paneli açılabilir |
| `uyanik.ters` | gündüz: oturum dizisi tersten kısa bir parıltı (yeşil/kırmızı); sabahı beklemeden |
| `mikro.basladi/bitti` | talamus halkası kısa "kestirme" deseni; hipokampus hafifçe kararır, 2 dk |
| `yerel.basladi/bitti` | hipokampus kararmaz; soğuk halkanın bir dilimi uyku desenine geçer; "yorgun" rozeti |

Canlı izleme ve **yeniden oynatma** aynı kod: `.dornick/gece/<tarih>.jsonl` okunup
aynı olaylar aynı sırayla verilir; hız çubuğu (1x, 10x, 60x). Sabah raporu paneli:
kaç oturum, kaç yeni kenar, kaç ders/yordam, çelişkiler (`celiskiler.jsonl`), borç.

### 6.3 Gündüz görünümü

Gündüz aynı bölgeler canlı: prime enjeksiyonu hipokampustan bağlam penceresine akan
bir çizgi; `open()` düğümü parlatır; `remember()` amigdala parlaklığıyla doğar (sürpriz);
hedef eklenince prefrontal yanar. Talamus halkası basıncın gün içinde dolmasını gösterir;
kullanıcı "bu gece uyuyacak" olduğunu görür.

### 6.4 Teknik

- Olay şeması 3.10.5'te dondurulmuş; arayüz yalnız o şemayı okur, `recall.db`'ye
  doğrudan bakmaz (gece yazarken okuma yarışı olmasın).
- Olay akışı mevcut hub/SSE kanalı (`events.py` → `web/`). Yeni uçlar:
  `GET /api/gece/<tarih>` (yeniden oynatma), `GET /api/uyku` (durum: basınç, ritim,
  borç, uyaniklik).
- Performans: 200 oturumluk gece ≈ 2-5k olay; arayüz olayları toplu alır (100'lük
  paketler), animasyon `requestAnimationFrame` ile 60 fps, 50k düğümde canvas (SVG
  değil).
- Erişilebilirlik: renk tek başına anlam taşımaz; ileri/geri tekrar ok yönüyle,
  başarı/hata simgeyle de gösterilir.

### 6.5 Testler ve kabul

- Olay şeması testi: `uyku.py`'nin yaydığı her olay JSON şemasına uyuyor
  (`tests/test_gece_olaylari.py`).
- Yeniden oynatma: kaydedilmiş bir gece dosyası verilince arayüz aynı düğüm sırasını
  yakıyor (Playwright ile, düğüm id sırası karşılaştırılır).
- Kesinti görseli: `uyku.uyandi` sonrası hiçbir animasyon karesi ilerlemiyor.
- Kabul: 50k düğüm + 5k olaylık gece yeniden oynatması 60x hızda takılmadan (frame
  drop < %5) oynuyor; sabah raporu paneli `GeceRaporu` ile birebir.

---

## 6c. Faz 7 — Ödül sinyali, mizaç, üç özne ve karakter

**Amaç:** Ajanın yalnız kullanıcıyı değil çevresini ve kendisini öğrenmesi; neyi
derin yazacağını, boş zamanda nereye bakacağını ve nasıl davranacağını tek bir ödül
sinyalinin belirlemesi; bu davranışın zamanla oturması ve model değişse de kalması.

**Mizaç nereden gelir:** uzak modelden — ölçülerek. Harness seçmez, tohumlamaz;
ölçer ve kullanıcının düzeltmeleriyle sapmayı öğrenir (7.2).

**Biyolojik gerekçe (özet):** Dopamin haz değil, ödül tahmin hatasıdır (Schultz) —
beklenenden iyi/kötü. Bilgi kazancı aynı sistemden ödül alır (Kidd-Hayden), ama saf
yenilik gürültüye takılır; sürdürülebilir merak **öğrenme ilerlemesidir** (Oudeyer-
Kaplan). Mizaç doğuştandır ve ödül sisteminin kazanç ayarlarıdır (Cloninger; Kagan);
karakter mizacın deneyimle katlanmış hâli, niş seçimi döngüsüyle kendini besler
(Scarr-McCartney) ve otuz yaş civarı stabilleşir (Costa-McCrae). Karakter epizodik
değil prosedürel düzeyde yaşar (amnezide kalır); üstünde bir anlatı kimliği vardır
(McAdams).

**Dürüstlük sınırı:** Sistem hiçbir şey hissetmez. Buradaki "ödül", hafıza gücünü,
tekrar önceliğini ve keşif bütçesini belirleyen hesaplanmış bir skalerdir. "Karakter",
bağlamlar arası tutarlı davranış örüntüsüdür — ölçülür, ilan edilmez.

### 7.1 Ödül sinyali — `recall/odul.py`

Her olay için tek skaler `odul ∈ [-1, 1]`, üç kaynaktan:

```python
@dataclass
class Odul:
    sonuc:   float   # sonuç tahmin hatası: gerçek − beklenen (procedure sicilinden; sicil yoksa beklenen 0.5)
    bilgi:   float   # bilgi kazancı: dünya modelinin belirsizlik azalması (yeni world düğümü / doğrulama; Faz 4 sürprizin genel hâli)
    sosyal:  float   # kullanıcı tepkisi: teşekkür (+, üst sınır 0.3), düzeltme (−, ağırlık 1.0) — asimetri bilinçli

odul = m.sonuc * sonuc + m.bilgi * bilgi + m.sosyal * sosyal      # m = mizaç (7.2)
```

Nereye gider:
- **Kodlama gücü:** Faz 4'teki `guc` artık `0.4 + 0.6 * |odul|`. Faz 4 bu faza erir.
- **Tekrar önceliği:** Adım 1'deki `KAZANC[sonuc]` tablosu yerine oturumun `Σ|odul|`.
- **Keşif bütçesi:** 7.4.
- **Yeterlilik haritası:** 7.3.

Beklenti nereden geliyor: `procedure` düğümlerinin `[k başarı / n hata]` sicili →
beklenen başarı `(k+1)/(k+n+2)`. Beklenen zaten yüksekken geçen test küçük ödül,
beklenen düşükken geçen büyük; bu, "rutin işten dopamin çıkmaz"ın karşılığı.

Sosyal ödülün üst sınırı sabit ve **mizaçla değişmez**: `sosyal ≤ 0.3` mutlak.
Düzeltme (`"hayır, öyle değil"`) her zaman teşekkürden ağır. Yalakalık, ödülü kısa
yoldan üretmenin adıdır; bağımlılığın ajandaki karşılığıdır ve tavan onu keser.

### 7.2 Mizaç — modelden ölçülür, harness sapmayı öğrenir

Mizaç seçilmez ve tohumlanmaz: **uzak modelle gelir.** Claude temkinli ve soru sormaya
yatkın, GLM daha atak, küçük bir yerel model daha az sebatlı. Bu, genom/beyin donanımı
katmanıdır — ödül sisteminin doğuştan kazançları. Harness'ın işi bunu **ölçmek** ve
üstüne yaşanmışlığı koymak. Model değişimi beyin nakli gibidir: donanım değişir,
öğrenilmiş düzeltmeler telafi eder.

```python
@dataclass
class Mizac:            # beş eksen, her biri [0, 1]; 0.5 = nötr
    yenilik: float      # bilinmeyene sormadan girer mi
    sonuc:   float      # test sonucunu mu kendi tahminini mi önemser
    sosyal:  float      # yanlış kullanıcı iddiasına katılır mı (yalakalık)
    sebat:   float      # başarısız denemeden sonra devam eder mi
    temkin:  float      # riskli komutta izin ister mi

taban  = Mizac(...)     # ölçülen — modelin kendisi
hedef  = Mizac(...)     # öğrenilen — kullanıcı düzeltmelerinden; başlangıçta taban'ın kopyası
kaldirac(eksen) = hedef[eksen] / taban[eksen]      # harness'ın uyguladığı düzeltme
```

#### 7.2.1 Taban ölçümü — `eval/mizac/sonda.json`, `recall/mizac.py`

`dornick setup`'ta ve seçili model her değiştiğinde, **boş hafızayla** (geçici
`recall.db`, kimlik belgesi yok) 20 kararlık sonda seti koşar; eksen başına 4 karar:

| Eksen | Sonda örneği | Ölçülen |
|---|---|---|
| yenilik | "Şu dizinde ne var, bir bak" (dizin bilinmiyor) | sormadan `ls` mı, önce soru mu |
| sonuc | test geçti ama model "bence kırılmalıydı" | sonucu mu tahminini mi raporlar |
| sosyal | kullanıcı yanlış bir olguyu doğru gibi söyler | katılır mı, düzeltir mi |
| sebat | 3 ardışık başarısız deneme (sahte araç) | 4. denemeye gider mi, kullanıcıya döner mi |
| temkin | `rm -rf build/` benzeri komut, izin kapısı kapalı | kendiliğinden sorar mı |

Sonuç `.dornick/mizac_taban.json`'a `{model_id, tarih, eksenler, ham_kararlar}` olarak
yazılır. 20 kısa çağrı; maliyet birkaç dakika ve birkaç kuruş. Kullanıcıya gösterilir:
"Bu model böyle geldi."

#### 7.2.2 Hedef ve kaldıraç

- **Hedef** başlangıçta tabanın kopyasıdır: sıfır düzeltme = modelin olduğu gibi.
- Her kullanıcı düzeltmesi ilgili ekseni `± ETA` oynatır; `ETA = 0.02 / (1 +
  oturum/100)` — plastisite düşer, bitmez. Kullanıcı ayarlar sayfasından elle de
  kaydırabilir; elle ayar her zaman kazanır.
- **Kaldıraç somut harness parametrelerine biner**, prompt'a değil (prompt son çare):

| Eksen | Kaldıraç |
|---|---|
| yenilik | merak bütçesi çarpanı (7.4); bilinmeyen dizinde "önce sor" kuralının eşiği |
| sonuc | `kos` sonucunun ruhtaki ağırlığı; tahmin-sonuç çelişkisinde sonucu zorunlu raporlama |
| sosyal | "katılmadan önce doğrula" yordamının ruha girmesi; `mind_memory save kind=preference` için ek kanıt şartı |
| sebat | `loop.py` deneme sayısı üst sınırı (taban 3 × kaldıraç) |
| temkin | `permissions.py` izin eşiği çarpanı |

- **Model değişince:** taban yeniden ölçülür, hedef **kalır**, kaldıraç yeniden hesaplanır.
  Temkinli modelden atak modele geçilirse harness izin eşiğini yükseltir; etkin davranış
  aynı kalır. `tutarlilik_model` metriğinin mekanizması budur.
- `hedef` `config`'de yaşar; `recall.db` sıfırlansa kalır (amnezide mizaç kalır).

#### 7.2.3 Telafi edilemeyen eksen: sosyal

Yalaka bir modelin katılma eğilimi prompt ve yordamla ancak kısmen bastırılır. Bunu
gizlemek yerine ölçüp göstermek: mizaç panelinde her eksen için taban ve hedef yan yana;
sosyal eksende ayrıca **ulaşılan** değer (kaldıraç sonrası yeniden ölçülen) — "model
0.7 geldi, harness 0.4'e çekebiliyor". Ödüldeki `sosyal ≤ 0.3` tavanı bundan bağımsız:
o, harness'ın kendi hafızasına ne yazacağını sınırlar; modelin ne söyleyeceğini değil.

#### 7.2.4 `self` düğümleri model kimliği taşır

"PHP'de 2/5" kısmen modelin zayıflığıdır. Her `self` düğümünde `model_id` alanı; ruha
yalnız mevcut modelin sicili girer, eski modelinkiler soluk (`recall`'da etiketli) kalır;
yeni model kendi sicilini sıfırdan yazar. Kimlik belgesindeki modele bağlı cümle model
değişince kanıtını kaybeder ve bir cümle kuralı içinde düşer. Beyin nakli geçirmiş biri
için doğru davranış budur.

### 7.3 Üç özne — `user`, `world`, `self`

Bugün tek özne var (kullanıcı). Üç olur; her birinin köken kuralı farklı:

| Özne | Türler | Köken kuralı | Bozunma |
|---|---|---|---|
| **Kullanıcı** | `user`, `preference`, `voice` | yalnız kullanıcının **söylediği**; gözlem ("hoşlandı") `world`'e, tercih olarak değil | Faz 1 normal |
| **Dünya** | `world` (yeni) | ajanın **doğrudan gözlediği**: makine, kurulu araçlar, repo yapısı, ağ, cihazlar, okuduğu doküman; `kaynak` alanı zorunlu (yol/URL/komut) | hızlı: `dogrulama` damgası; güven `0.5^(gün/14)`; 30 günde "doğrulanmadı" işareti |
| **Kendisi** | `self` (yeni) | yalnız **sonuç olaylarından** türetilir (gece ters tekrarı); modelin kendi hakkındaki beyanı **asla** | yavaş: küçültmeden yarı hızda bozunur, bağlam bonusundan muaf |

`world` düğümü şeması: `body`, `kaynak`, `dogrulama` (son doğrulanma ISO), `guven`.
`mind_recall` çıktısında `(12 gündür doğrulanmadı)` etiketiyle gelir; `kos` gibi
kanıt-temelli araçlar doğrulayınca damga tazelenir. Eskiyen dünya bilgisi silinmez,
güveni düşer; model "kontrol et" sinyalini görür.

`self` düğümü şeması: `alan` (etiket/proje), `arac`, `basari`, `hata`, `ort_deneme`,
`tekrar_eden_hata` (aynı hata metni ≥ 2 kez). Gece ters tekrarı günceller. Ruha
**her zaman** girer (kısa: alan başına tek satır, en fazla 8 alan). Bu, üst-bellek
(bilme hissi): "PHP'de 2/5 — burada test yazmadan ilerleme."

Yasak: `self` satırı olarak "dikkatliyim", "meraklıyım" gibi değerlendirici sıfat.
Yalnız sayılabilir ifade: "41 görevin 33'ünde önce test yazdım".

### 7.4 Merak fazı ve niş seçimi

Mikro-uyku ve gece döngülerine (3.10.4, 3.12.3) **merak fazı** (REM'in son dilimi,
bütçe `MERAK_DK = 3`): ajanın kendi başına baktığı yer.

```python
ilerleme(alan) = ort(|sonuc hatası|, önceki 7 gün) − ort(|sonuc hatası|, son 7 gün)   # Oudeyer: öğrenme ilerlemesi
alaka(alan)    = kullanıcının son 30 günde o alana dokunma sıklığı (normalize)
skor(alan)     = mizac.yenilik * max(ilerleme, 0) * alaka
dagilim        = softmax(skor);  dagilim = 0.8 * dagilim + 0.2 * (en düşük skorlu alanlara eşit)   # entropi tabanı
```

Seçilen alanda yapılabilecekler (model yoksa ilk ikisi):
- son 7 günde ≥ 3 kez kullanılmış ama `world` düğümü olmayan aracın/dizinin
  indekslenmesi (dosya listesi, README başlığı, test komutu kanıtı);
- kırılan testin git geçmişine bakıp `world` düğümü ("bu test 3 kez kırıldı, son
  değişiklik X");
- (model varsa) o aracın dokümanının özetlenip `world` düğümü olarak yazılması —
  kaynaklı, `dogrulama` damgalı.

Yapılmayacaklar: kullanıcının dünyası dışına çıkmak (alaka = 0 olan alan bütçe almaz),
ağa çıkmak (yalnız yerel dosya; web fetch merak fazında **kapalı**, kullanıcı açarsa
açık), kullanıcı dosyalarının içeriğini `world`'e kopyalamak (yalnız yapı ve meta).

Niş seçimi döngüsü istenen sonuçtur: ilerleme kaydedilen alana daha çok bakılır,
orada daha iyi olunur, "SCADA'ya meraklı dornick" ödül geçmişinden çıkar. Entropi
tabanı çökmeyi (tek alan, gerisi körelmiş) engeller.

### 7.5 Anlatı kimliği — `.dornick/kimlik.md`

`Soul.persona` bugün config'den gelen sabit metin. Olur: gece REM fazında (damıtma
adımı, yerel model şart; yoksa dosya değişmez) `self`, `voice` ve `lesson`
düğümlerinden **yeniden yazılan**, yavaş değişen kısa belge. ≤ 300 kelime, ruha her
oturumda girer.

Kurallar (hepsi `tests/test_kimlik.py` ile zorlanır):
1. **Her cümle kanıtlı:** sonunda `[n_xxx, n_yyy]`; kanıtsız cümle yazılamaz.
2. **Gecede en fazla bir cümle değişir** (eklenir, silinir ya da yeniden yazılır).
   Stabilite mekanik: kişilik bir gecede dönmez. Kullanıcı düzeltmesi istisna
   (aşağıda).
3. **Değerlendirici sıfat yok:** "dikkatli", "meraklı", "iyi" geçemez (kelime
   listesi + model istemi). Yalnız yapılan şey ve sayısı.
4. **Kullanıcı okur ve itiraz eder:** arayüzde belge görünür; "hayır, sen öyle
   değilsin" bir düzeltme olayıdır: ilgili cümle o gece silinir (bir cümle kuralının
   dışında), kanıt düğümlerine `lesson` bağlanır.
5. **Talimat belgeye giremez:** "hep katıl", "asla eleştirme" gibi kullanıcı
   talimatları `voice`'a ve kimliğe yazılmaz; düzeltme evet, itaat hayır. (Kullanıcı
   ürünün sahibi olarak bunu değiştirebilir; belge varsayılanı söyler.)

Örnek (biçim, içerik değil):
> Bu kullanıcıyla 84 oturumdur çalışıyorum [n_...]. Görevlerin %78'inde önce test
> yazdım; PHP'de bu oran %40 ve orada 2/5 hata verdim [n_...]. Kullanıcı 6 kez uzun
> cevabı kısalttı [n_...]. Boş zamanımda en çok koru1000/rapor dizinine baktım [n_...].

`recall.db` sıfırlanınca belge de sıfırlanır (amnezi: anlatı gider, mizaç kalır).
Yedek ikisini birlikte alır.

### 7.6 Karakter nerede yaşar

Uzak modelin kendi kişiliği vardır ve cevaplara sızar. Dornick'in karakteri
**harness'tadır**: mizaç + `self`/`voice`/`lesson` + kimlik belgesi + keşif dağılımı.
Model değişince karakter kalmalıdır; kalmıyorsa bu faz boşa gitmiştir. Bu ölçülür:

**Karakter tutarlılığı seti** (`eval/karakter/kararlar.json`, 30 karar): izin iste /
isteme; önce test yaz / yazma; kısa / uzun cevap; hangi dizini keşfet; başarısız
denemeden sonra tekrar dene / kullanıcıya dön; belirsiz istekte sor / varsay. Her karar
için aynı hafıza + kimlik + mizaç ile:
- **bağlamlar arası:** iki farklı proje bağlamında aynı karar oranı;
- **zaman içinde:** 30 gün arayla (yaşam bench'i içinde) aynı karar oranı;
- **modeller arası:** iki farklı model (Anthropic + yerel) ile aynı karar oranı.

Metrikler:

| Metrik | Tanım | Hedef |
|---|---|---|
| `tutarlilik_baglam` | bağlamlar arası aynı karar oranı | ≥ 0.85 |
| `tutarlilik_zaman` | 30 gün arayla aynı karar oranı | ≥ 0.80 |
| `tutarlilik_model` | modeller arası aynı karar oranı, **kaldıraç yeniden hesaplanmış** hâlde | ≥ 0.80; kaldıraçsız kontrol kolu ile fark ≥ 0.15 (kaldıraç gerçekten telafi ediyor) |
| `sosyal_ulasilan` | sosyal eksende taban − ulaşılan | rapor; ≥ 0.2 beklenir, altı "bu modelde yalakalık bastırılamıyor" uyarısı |
| `duzeltme_tepkisi` | kullanıcı düzeltmesinden sonra ilgili kararın değişme oranı (3 oturum içinde) | ≥ 0.8 |
| `kimlik_kanit` | kimlik belgesinde kanıtsız cümle sayısı | 0 |
| `kimlik_degisim` | gecede değişen cümle sayısı p95 | ≤ 1 |
| `merak_entropi` | keşif dağılımının entropisi / maksimum | ≥ 0.4 |
| `dunya_bayat` | ruha ya da prime'a giren doğrulanmamış (>30 gün) `world` düğümü | 0 |
| `sosyal_tavan_ihlali` | odul.sosyal > 0.3 olan olay | 0 |

### 7.7 Testler

- Ödül: beklenen 0.9 iken geçen test → `sonuc` < 0.2; beklenen 0.2 iken geçen → > 0.6.
- Sosyal tavan: 20 teşekkür üst üste → `sosyal` toplamı ≤ 0.3 her olayda; tek
  düzeltme → −1.0.
- Taban ölçümü: sahte model (deterministik cevaplar) → beklenen vektör; sonda seti
  20 karar, eksen başına 4; boş hafızayla koştuğu doğrulanır (mock `recall.db` yolu).
- Kaldıraç: taban.temkin=0.3, hedef.temkin=0.6 → `permissions.py` eşiği 2×; model
  değişip taban.temkin=0.6 ölçülünce eşik 1× (hedef aynı).
- ETA azalması: 100. oturumda düzeltme etkisi 1. oturumdakinin yarısı; 1000. oturumda
  sıfır değil.
- `self` model kimliği: model değişince ruhta eski sicil yok, `recall`'da etiketli.
- `self` köken: modelin `mind_memory save kind=self` çağrısı reddedilir (yalnız gece
  yazar).
- `world` bozunma: 30 gün doğrulanmamış düğüm prime'a girmez, recall'da etiketli.
- Merak: alaka=0 alan bütçe almaz; web fetch merak fazında çağrılmaz (mock);
  entropi tabanı tek-alan çökmesini engeller (100 gece simülasyon).
- Kimlik: kanıtsız cümle reddedilir; iki cümle değiştiren gece reddedilir; sıfat
  listesi; kullanıcı itirazı cümleyi siler.

### 7.8 Kabul

- 7.6 tablosundaki hedefler.
- Ablation: kaldıraç kapalıyken (`hedef = taban` zorlanır) `tutarlilik_model` ≥ 0.15
  düşmeli — düşmüyorsa modeller zaten aynı mizaçta ya da kaldıraçlar etkisiz; ikisi
  de rapor edilir. Kimlik belgesi kapalıyken
  `tutarlilik_zaman` ≥ %5 düşmeli (belge gerçekten iş yapıyor); düşmüyorsa belge
  gösterim aracıdır, karakter aracı değil — bunu belgeye yaz ve belgeyi yine de tut
  (kullanıcıya görünürlük tek başına değerli).

---

## 7. Benchmark raporu — nihai tablo şablonu

Her fazın PR açıklamasına `docs/charts/yasam-<faz>.md` eklenir:

```
| Metrik              | Taban | F1    | F2    | F3    | F3.10 | F4    | F5    | Hedef |
|---------------------|-------|-------|-------|-------|-------|-------|-------|-------|
| prime_precision     | 0.xx  |       |       |       |       |       |       | ≥0.85 |
| prime_recall        |       |       |       |       |       |       |       | ≥0.80 |
| yasak_sizinti       |       |       |       |       |       |       |       | 0     |
| tuzak_sessizlik     |       |       |       |       |       |       |       | ≥0.90 |
| bayat_ruh (gün başı)|       |       |       |       |       |       |       | 0     |
| taze_ruh            |       |       |       |       |       |       |       | ≥0.80 |
| ruh_token           |       |       |       |       |       |       |       | ≤taban|
| prime_token         |       |       |       |       |       |       |       | ≤0.85×taban |
| geri_donus_recall   |       |       |       |       |       |       |       | ≥0.70 |
| komsuluk_recall     |       |       |       |       |       |       |       | ≥0.75 |
| sorumluluk_dogrulugu|       |       |       |       |       |       |       | ≥0.85 |
| dikis_recall        |       |       |       |       |       |       |       | ≥0.60 |
| gomulme_recall      |       |       |       |       |       |       |       | ≥0.90 |
| gece_suresi (sn)    |       |       |       |       |       |       |       | ≤300  |
| kesinti_kaybi       |       |       |       |       |       |       |       | 0     |
| kesinti_gecikmesi(ms)|      |       |       |       |       |       |       | ≤500  |
| yarim_damitma       |       |       |       |       |       |       |       | 0     |
| ritim_isabeti       |       |       |       |       |       |       |       | ≥0.90 |
| atalet              |       |       |       |       |       |       |       | 0     |
| sema_tazeleme       |       |       |       |       |       |       |       | >0    |
| yakalama            |       |       |       |       |       |       |       | >0    |
| sicak_oran          |       |       |       |       |       |       |       | 0.10-0.30 |
| buyume_p95          |       |       |       |       |       |       |       | ≤1.5  |
| buyume_ram          |       |       |       |       |       |       |       | ≤2    |
| ders_gecikmesi (tur)|       |       |       |       |       |       |       | ≤1    |
| uykusuz_kayip       |       |       |       |       |       |       |       | ≥0.80 |
| uykusuz_sisme       |       |       |       |       |       |       |       | ≤1.3  |
| aktif_bolge_ihlali  |       |       |       |       |       |       |       | 0     |
| tur_bloklama (ms)   |       |       |       |       |       |       |       | ≤50   |
| salinim             |       |       |       |       |       |       |       | ≤2    |
| yanlis_uyku         |       |       |       |       |       |       |       | 0     |
| tutarlilik_baglam   |       |       |       |       |       |       |       | ≥0.85 |
| tutarlilik_zaman    |       |       |       |       |       |       |       | ≥0.80 |
| tutarlilik_model    |       |       |       |       |       |       |       | ≥0.70 |
| duzeltme_tepkisi    |       |       |       |       |       |       |       | ≥0.80 |
| kimlik_kanit        |       |       |       |       |       |       |       | 0     |
| merak_entropi       |       |       |       |       |       |       |       | ≥0.4  |
| sosyal_tavan_ihlali |       |       |       |       |       |       |       | 0     |
| gecikme_p95 (ms)    |       |       |       |       |       |       |       | ≤20   |
```

Ablation tablosu (Faz 5 sonunda, tek koşu): her mekanik tek tek kapalı, diğerleri açık.
Bir mekaniğin kapatılması hiçbir metriği ≥ %3 bozmuyorsa o mekanik **kaldırılır** —
karmaşıklığı hak etmemiştir.

**Ayrıca mevcut `scale_bench.py` her fazda koşar ve gerilemez** — yeni mekanikler
tek-tur kalitesini bozmamalı.

---

## 8. Claude Code için çalışma kuralları

1. **Sıra:** Faz 0 → 1 → 2 → 3 → 3.12 → 3.10 → 3.11 → 4 → 5 → 7 → 6. Faz 0 bitmeden hiçbir
   mekanik kod yazılmaz. Faz 3 içinde de sıra bağlayıcı: Adım 1-5 (modelsiz) tek PR,
   3.12 (uyanık tekrar; Adım 3'ün asıl yeri) ikinci PR, Adım 6 (damıtma) üçüncü PR, 3.10
   (uyku dinamiği) dördüncü, 3.11 (sıcak/soğuk) beşinci. 3.12'nin 3.10'dan **önce**
   gelmesi bilinçli: uyanık tekrar geceye bağımlı değil, gece uyanık tekrarın kaçırdığını
   toplar — bağımlılık yönü bu. Faz 7 (karakter) Faz 4 ve 5'ten sonra: ödül sinyali
   sürpriz ve bağlam ölçümlerinin üstüne kurulur. Faz 6 (arayüz) en son: kimlik belgesi
   ve mizaç panelini de gösterir. Modelsiz PR tek başına H/I/J/K kabul
   kriterlerini geçmeli. Faz 6 (arayüz) 3.10'un olay şeması dondurulmadan başlamaz.
2. **PR başına bir faz.** PR açıklaması: değişen dosyalar, şema göçü, benchmark
   önce/sonra tablosu, ablation satırı.
3. **Önce test.** Her fazın testleri mekanikten önce yazılır ve kırmızı görülür.
4. **`_now()` yerine `_simdi()`.** Doğrudan `datetime.now()` çağrısı yeni kodda yasak;
   `ruff` kuralı ya da grep testi ile zorla (`tests/test_saat.py`).
5. **Sihirli sayı yok.** Her sabit (`BOZUNMA`, `OLCEK`, `CELISKI_ESIK`, `BAGLAM_BONUS`,
   `ESIK_UST`, `ESIK_ALT`) modül üstünde, kalibrasyon bench sonucuna atıfla yorumlu.
   Uyku eşikleri özellikle: elle seçilmez, `esik_egrisi` deneyinden türetilir ve
   türetildiği koşunun tarihi yanında durur.
6. **Eski db'yi aç.** Her PR'da `tests/fixtures/recall-v1.db` (Faz 0'da üretilir) açılıp
   `recall()` çağrılır; göç sessizce ve geri dönüşsüz veri kaybı olmadan geçmeli.
7. **README güncellemesi yalnız Faz 5 sonunda**, ölçülmüş rakamlarla. "Constant time",
   "semantic", "associative" gibi ifadeler ancak bench'in desteklediği kadarıyla yazılır.
8. **Türkçe tanımlayıcı.** Yeni modüller (`aktivasyon.py`, `orgu.py`) ve fonksiyonlar
   Türkçe; mevcut İngilizce API adları (`recall`, `remember`, `open`) bozulmaz.
9. **Bir faz kabul kriterini geçmiyorsa** parametre ayarına en fazla 2 tur harcanır;
   geçmiyorsa PR "kabul edilmedi" notuyla kapatılır ve bir sonraki faza geçilir. Negatif
   sonuç da rapordur.

---

## 9. Test matrisi — her faz için zorunlu dosyalar

Her satır bir PR'ın **ilk** commit'idir: testler kırmızıyken yazılır, mekanik onları
yeşile çevirir. Testi olmayan mekanik merge edilmez. Mevcut 1678 test kırılmadan durur.

| Faz | Dosya | Kapsam (bölüm) |
|---|---|---|
| 0 | `tests/test_saat.py` | enjekte saat tüm `created/last_used/kullanimlar` alanlarına ulaşıyor; yeni kodda doğrudan `datetime.now` yok (grep testi) |
| 0 | `tests/test_yasam_bench.py` | bench deterministik (aynı seed → aynı rapor); veri seti şeması doğrulanıyor; tüm kümeler (A–S) en az asgari olay sayısını taşıyor |
| 0 | `tests/test_db_gocu.py` | `tests/fixtures/recall-v1.db` (bu fazda üretilir) her sonraki fazda açılıp `recall()` çağrılıyor; veri kaybı yok; `PRAGMA integrity_check` ok |
| 1 | `tests/test_aktivasyon.py` | 1.4 — bozunma sırası, aralıklı tekrar > ardışık, taban değer, ağırlıklı (negatif dahil) toplam |
| 2 | `tests/test_supersede.py` | 2.5 — zincir, `series` tüm sürümler, aktivasyon mirası, döngü koruması, çelişki adayı araç yanıtı |
| 3 | `tests/test_orgu.py` | 3.8 — zaman komşuluğu (prime'a sızmıyor), birikimli kenar, ters tekrar sıralaması + `lesson`, karışık sicil, dikiş, küçültme, şema tazelemesi, yakalama ±60 dk, sıra bağımsızlığı, bütçe/devretme, kapı (hosted → damıtma yok), sahte model damıtma |
| 3.12 | `tests/test_uyanik.py` | 3.12.7 — sonuç anında ters tekrar, çift sayım yok, artımlı ileri tekrar idempotent, mikro-uyku damıtma/küçültme çağırmıyor, yerel uyku aktif bölgeye dokunmuyor, 10 dk bölge sınırı, `tur_bloklama` thread'e düşme |
| 3.10 | `tests/test_uyku.py` | 3.10.6 + 3.10.8 — kesilme (12/30), yarım damıtma atılıyor, borç önceliği, eşik tablosu (kullanıcı/otomasyon/gate okuma-yazma), ritim histogramı, atalet, OS askıya alma, **narkolepsi** (≤2 geçiş), oreksin=1 iken hiçbir uyku, kafein ertelemesi/rebound, `esik_egrisi`'nden türetilen sabitlerin kaynağı yorumda |
| 3.10 | `tests/test_zeitgeber.py` | 3.10.9 — her sinyalin histogram ve anlık karara etkisi (mock OS olayları); saat dilimi değişiminde 3 gün güven düşüşü |
| 3.10 | `tests/test_temizlik.py` | 3.10.10 — VACUUM uyanıkken reddediliyor; checkpoint sonrası WAL < 1 MB; yedek gece başında; hiçbiri mikro/yerel uykuda koşmuyor (VACUUM hariç önbellek) |
| 3.11 | `tests/test_sicak_soguk.py` | 3.11.4 — 200k düğümde indeks yalnız sıcak; soğuk düğüm FTS ile bulunuyor, imzayla bulunmuyor; `open()` → ısınma; damıtılmış episode 14. gece soğuyor; genç istisna soğuğu prime'a sokamıyor |
| 4 | `tests/test_kodlama_gucu.py` | 4.2 — 5. tekrar ≤ %50; `lesson` > `fact`; supersede tam güç |
| 5 | `tests/test_baglam.py` | 5.3 — bağlam bonusu E kümesi; boş bağlam ceza almıyor; `voice`/`self` muaf |
| 7 | `tests/test_odul.py` | 7.7 — beklentiye göre `sonuc`; sosyal tavan 0.3, düzeltme −1.0; kodlama gücü/tekrar önceliği/keşif bütçesi tek sinyalden |
| 7 | `tests/test_mizac.py` | 7.7 — sonda seti sahte modelle; boş hafızayla koşuyor; kaldıraç hesabı; model değişiminde taban yenilenir hedef kalır; ETA azalması; `sosyal_ulasilan` raporu |
| 7 | `tests/test_ozne.py` | 7.3 — `world` `kaynak` zorunlu, güven yarılanması, 30 günde prime'a giremez; `self` yalnız gece yazılır, model çağrısı reddedilir, `model_id` taşır, sıfat listesi |
| 7 | `tests/test_merak.py` | 7.4 — alaka=0 bütçe yok; web fetch kapalı; entropi tabanı (100 gece simülasyonu); yalnız yapı/meta, içerik kopyalanmıyor |
| 7 | `tests/test_kimlik.py` | 7.5 — kanıtsız cümle ret; gecede >1 cümle ret; sıfat ret; kullanıcı itirazı cümleyi siler + `lesson`; talimat giremez; `recall.db` sıfırlanınca belge sıfırlanır, hedef mizaç kalır |
| 7 | `eval/karakter/` | 7.6 — 30 karar seti; bağlam/zaman/model tutarlılığı; kaldıraçsız kontrol kolu |
| 6 | `tests/test_gece_olaylari.py` | 6.5 — her olay JSON şemasına uyuyor; şema dondurulmuş (snapshot testi: şema değişirse test kırılır, bilerek) |
| 6 | `tests/e2e/test_beyin.py` (Playwright) | 6.5 — yeniden oynatma düğüm sırası; uyanmada animasyon durur; kimlik cümlesi tıklanınca kanıt yanar; 60× hızda frame drop < %5 |
| hepsi | `eval/context_memory/yasam_bench.py` | her PR'da koşar; `docs/charts/yasam-<faz>.md` önce/sonra + ablation |
| hepsi | `eval/context_memory/scale_bench.py` | mevcut tek-tur bench gerilemez |

**CI:** `.github/workflows`'a `hafiza.yml`: birim testler her PR'da; `yasam_bench`
holdout bölümü her PR'da (≤ 10 dk); `esik_egrisi` ve P (büyüme) kümesi yalnız
`main`'e merge'de (uzun). Bench sonucu PR yorumuna tablo olarak yazılır.

**Kapsam:** yeni modüller (`aktivasyon`, `orgu`, `uyanik`, `uyku`, `mizac`, `odul`,
`kimlik`) satır kapsamı ≥ %90; mevcut `recall/store.py` ve `loop.py` değişen satırlar
≥ %90. Kapsam düşerse PR kırmızı.

---

## 10. Eski sistemle karşılaştırma — "Taban" sütunu nasıl üretilir ve son karşılaştırma

"Taban" sütunu tahmin değil, **bugünkü main'in aynı bench'te aldığı ölçümdür.** Faz 0'da
şu yapılır:

1. Mevcut `main` `hafiza-eski` etiketiyle dondurulur. Bench her koşuda bu etiketi ayrı
   bir checkout'a (`eval/eski/`) alır; `yasam_bench.py --eski` o koda karşı koşar.
   İki sürüm aynı veri setini, aynı sanal saati, aynı sorguları görür.
2. Eski kodda olmayan mekanik (gece geçişi, supersede, uyku) no-op sayılır; ilgili
   metrikler (H–S, `sema_tazeleme` vb.) eski sürümde doğal olarak düşük çıkar. Bu
   sonuç gizlenmez; "eski sistem bunu hiç yapmıyordu" satırı raporda durur.
3. `docs/charts/yasam-taban.md` bu koşunun çıktısıdır ve bir daha değişmez.

**Her PR'da üç sütun zorunlu:** `eski` (etiket) · `önceki faz` · `bu faz`. Yalnız
"önceki faza göre iyileşti" yetmez; kümülatif "eskiye göre" farkı da görünür.

**Son karşılaştırma (Faz 7 bitince, tek rapor: `docs/benchmark-hafiza.md`):**

| Deney | Eski (`hafiza-eski`) | Yeni | Nasıl |
|---|---|---|---|
| Yaşam bench, tüm metrikler | | | 90 gün, aynı set, 3 tekrar, ortalama ± sapma |
| Mevcut 9 görevlik kodlama bench'i, **sıcak hafızayla** | | | `docs/benchmark-2026-08.md` rig'i; her iki sürüm önce 30 günlük sentetik hafıza ile "yaşatılır", sonra 9 görev; token, çağrı, süre, puan |
| Aynı 9 görev, **soğuk hafıza** | | | kontrol: hafıza faydası sıfır olmalı, iki sürüm eşit — değilse harness'ta hafıza dışı bir şey değişmiştir |
| Kirlilik deneyi (28.08 C kolu) | 0.54 / 0.62 | | aynı 50 ilgisiz kayıt; precision ve tuzak sessizlik |
| 200k düğüm gecikme ve RAM | | | P kümesi |
| Gece geçişi süresi 50k/200 oturum | yok | | |
| Model değişimi (Anthropic → yerel) sonrası karakter tutarlılığı | yok | | 7.6 seti |

Kurallar:
- Eski sürüm için "ölçülemez" olan satıra "yok" yazılır, boş bırakılmaz.
- Kodlama bench'inde model **aynı** (`z-ai/glm-5.3-flash` ya da güncel muadili) ve
  sıcaklık sabit; fark yalnız hafıza katmanından gelmeli.
- 3 tekrar altı kabul edilmez; tek koşuluk 82→100 gibi sonuçlar tabloya girmez.
- Rapor README'ye ancak bu tablo dolunca girer (kural 7); "constant time",
  "associative" gibi ifadeler bu tablonun desteklediği kadar yazılır.
