# Claude Code'a verilecek talimat

Aşağıdaki metni olduğu gibi yapıştır. `dornick-hafiza-yol-haritasi.md` dosyasını
repo köküne `docs/hafiza-yol-haritasi.md` olarak koymuş ol.

---

Repo: dornick (github.com/dornick-dev/dornick). Görev: `docs/hafiza-yol-haritasi.md`
belgesini uygulamak. Belge bağlayıcıdır; kendi tasarımını üstüne koyma, belgede
olmayan bir şeye ihtiyaç duyarsan önce sor.

## Çalışma düzeni

1. **Sıra:** Faz 0 → 1 → 2 → 3 (Adım 1-5) → 3.12 → 3 (Adım 6) → 3.10 → 3.11 → 4 → 5 → 7 → 6.
   Bir faz, belgedeki kabul kriterini geçmeden sonrakine geçme. Faz 0 bitmeden hiçbir
   mekanik kod yazma.
2. **Her faz tek PR** (Faz 3 dört PR). PR açıklaması şablonu:
   - değişen dosyalar ve şema göçü,
   - `docs/charts/yasam-<faz>.md`: bench önce/sonra tablosu + ablation satırı,
   - kabul kriteri listesi, her biri ✓/✗ ve sayısıyla,
   - geçmeyen kriter varsa "kabul edilmedi" notu ve neden.
3. **Önce test.** Her fazın ilk commit'i belgenin 9. bölümündeki test dosyalarıdır;
   kırmızı görülmeden mekanik yazılmaz. Testi olmayan fonksiyon merge edilmez.
   Kapsam: yeni modüller ≥ %90, değişen satırlar ≥ %90. Mevcut 1678 test kırılmaz.
4. **Bench her PR'da koşar:** `eval/context_memory/life_bench.py` (holdout) ve mevcut
   `scale_bench.py`. İkisinden biri gerilerse PR açılmaz. Ölçülen yol ürünün kendisidir
   (`select_prime`, `RecallStore.recall`, `orgu.gece_gecisi`); kopya mantık yasak.
   **Her tabloda üç sütun:** `eski` (`hafiza-eski` etiketi, belge bölüm 10) · önceki faz ·
   bu faz. Eskiye göre kümülatif fark her PR'da görünür; eski sürümün yapmadığı şey
   "yok" diye yazılır, boş bırakılmaz.
5. **Sabitler türetilir.** `BOZUNMA`, `OLCEK`, `CELISKI_ESIK`, `BAGLAM_BONUS`, `EPSILON`,
   `SOGUK_ESIK`, `ESIK_UST/ALT`: modül üstünde, yanında türetildiği bench koşusunun
   tarihi. Elle seçilmiş sayı görürsem PR'ı geri çeviririm. Uyku eşikleri özellikle:
   yalnız `esik_egrisi` deneyinden.
6. **Saat:** yeni kodda `datetime.now` yasak, `_simdi()`; `tests/test_saat.py` bunu
   grep ile zorlar.
7. **Eski db açılır:** her PR'da `tests/fixtures/recall-v1.db` açılıp `recall()`
   çağrılır; göç sessiz ve kayıpsız.
8. **Tanımlayıcılar Türkçe**, mevcut İngilizce API adları (`recall`, `remember`, `open`,
   `Mind`, `Node`) bozulmaz. Yorumlar Türkçe, kısa, "neden" anlatır.
9. **Bir faz kabul kriterini geçmiyorsa:** parametre ayarına en fazla 2 tur; geçmezse
   PR "kabul edilmedi" notuyla kapanır, belgeye sonuç yazılır, sonraki faza geçilir.
   Negatif sonuç da rapordur; gizlenmez.
10. **README'ye dokunma.** Faz 5 sonuna kadar hiçbir README/doküman iddiası değişmez;
    değişince yalnız ölçülmüş rakamla ve belgedeki dürüstlük sınırlarıyla.
11. **Gizlilik:** damıtma ve kimlik belgesi hosted modele veri göndermez; `bulut_onayi`
    kapalıysa atlanır ve raporda "atlandı" yazar. Merak fazı web'e çıkmaz.
12. **Dürüstlük sınırları koddadır:** `self` düğümü modelin kendi beyanından yazılamaz;
    kimlik belgesine kanıtsız cümle ve değerlendirici sıfat giremez; sosyal ödül tavanı
    0.3 sabittir. Bunlar test edilir, talimatla bırakılmaz.

## İlk adım

Faz 0'ı aç:
- `RecallStore` ve `Mind`'a saat enjeksiyonu,
- `eval/context_memory/yasam_dataset.json` (90 gün, A–S kümeleri, asgari olay sayıları
  belgede) — el yazımı, Türkçe, `holdout` ayrı,
- `life_bench.py` (tüm metrikler, ablation bayrakları, gece geçişi çağrısı — henüz
  yokken no-op),
- `esik_egrisi` deneyi (gece kapalı, S'ye karşı bozulma),
- `tests/fixtures/recall-v1.db` üretimi,
- `main`'i `hafiza-eski` olarak etiketle; `life_bench.py --old` o etiketi ayrı
  checkout'ta koşturur,
- `docs/charts/yasam-taban.md`: **eski sistemin** bench sonucu — bu dosya bir daha
  değişmez.

Taban çizgisi commit'lenmeden Faz 1 PR'ı açma. Bitince PR linkini ve taban tablosunu
ver; sonra Faz 1'e geç.

Faz 7 bittiğinde belge bölüm 10'daki son karşılaştırmayı koş: yaşam bench + mevcut 9
görevlik kodlama bench'i sıcak ve soğuk hafızayla, eski ve yeni sürüm, aynı model, 3
tekrar. Tek dosya: `docs/benchmark-hafiza.md`. README ancak bundan sonra.

Her fazın sonunda bana şunu yaz: kabul kriterleri tablosu (sayılarla), ablation
sonucu, ve "kaldırılması gereken mekanik" varsa hangisi. Yorum yapma, tablo ver.
