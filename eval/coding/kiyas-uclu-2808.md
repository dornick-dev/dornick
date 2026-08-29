# Üçlü kıyas — Claude Code / OpenCode / neo (28.08.2026 akşamı)

Aynı üç görev, üç ayrı harness. OpenCode ve neo **aynı model** ile koştu
(`z-ai/glm-5.3-flash`, OpenRouter, görev başına taze/sıfır-hafızalı ortam,
kullanıcının verdiği ayrı anahtarlar). Claude Code şeridi = bu oturumdaki
Claude'un kendisi; **kendi modeliyle** çalışır (Fable), OpenRouter'a
bağlanamaz — o şerit model kıyası değil, harness+model referans çizgisi.
Verilen üçüncü anahtar hiç kullanılmadı ($0).

Puanlama: üç şeridin çıktısı da neo'nun bağımsız puanlayıcısıyla
(`eval/coding/gorevler/*/olcut.py`) aynı ölçütten notlandı. neo kaynak
ağaçtan koştu (kurulu sürüm değil); koşudan önce açık neo pencereleri
kapatıldı.

## Sonuç tablosu

### Puan (0–100)

| Görev | Claude Code | OpenCode | neo |
|---|---|---|---|
| k2-cli (kolay) | 100,0 | 100,0 | 100,0 |
| o1-rapor (orta) | 100,0 | 100,0 | 100,0 |
| z1-arama (zor) | 98,7 | **0,0** | 82,0 |
| **Toplam** | **298,7** | 200,0 | 282,0 |

### Süre (sn)

| Görev | Claude Code | OpenCode | neo |
|---|---|---|---|
| k2-cli | 31 | 39 | 35 |
| o1-rapor | 30 | 262 | 853 † |
| z1-arama | 86 | 683 | 735 |
| **Toplam** | **147** | 984 | 1623 |

### Token ve maliyet (glm şeritleri)

| Görev | OpenCode giren (cache) | neo giren (cache) | OpenCode $ | neo $* |
|---|---|---|---|---|
| k2-cli | 34.514 (22.464) | 46.696 (30.336 · %65) | 0,0016 | 0,0037 |
| o1-rapor | 238.059 (180.224) | 143.236 (121.216 · %85) | 0,0132 | 0,0110 |
| z1-arama | 42.799 (0) | 1.312.166 (1.208.704 · %92) | 0,0168 | 0,1027 |
| **Anahtar gerçek harcama** | | | **$0,0247** | **$0,0372** |

\* neo'nun görev-başı doları fiyat tablosundan tahmin; önbellek indirimini
saymaz. Sağlayıcı ucundan okunan gerçek harcama satır sonunda — neo'nun üç
görevi toplam **3,7 cent**.
† o1 süresi canlıda yakalanan stdin-asılma hatasını içerir (aşağıda);
düzeltme o koşunun ortasında yazıldı, z1 düzeltmeli koştu.

## Ne öğrenildi

**1. Zor işte fark model değil, harness freni.** Aynı model OpenCode'da
z1'e tek adımda 32.000 tokenlik akıl-yürütme sarmalıyla girdi
(`step-finish reason: length`, 31.996/32.000 token reasoning), tek dosya
bile yazamadan kesildi ve 683 sn + 1,7 cent'i çöpe attı. neo'da aynı model
aynı görevde 82 aldı çünkü (a) küçük ailede çaba tavanı `medium` (bugün
eklendi), (b) tur devam mekanizması var. Kalite ile "düşünme bütçesi" ayrı
şeyler — dün ölçülen "kalite kapılardan geliyor" bulgusunun ikinci kanıtı.

**2. Canlıda yakalanan neo yarası: stdin mirası + yarım öldürme.** o1'de
ajanın kendi yazdığı `rapor.py` stdin'den okumaya kalktı; çocuk süreç
neo'nun stdin'ini miras aldığı için 180 sn'lik üst kapağa kadar asıldı ve
"durduruldu" denen sarmalayıcının torunu 7,5 dk yaşadı. İki düzeltme aynı
oturumda commit'lendi (`ba84170`): çocuk `stdin=DEVNULL` (input() anında
EOFError → model görüp düzeltiyor), zaman aşımında `taskkill /T /F` ile
süreç AĞACI iner. Kanıt: stdin denemesi 0,2 sn'de düşüyor, timeout 3,3
sn'de ağacı öldürüyor (test_refleksler'de iki kalıcı test).

**3. Önbellek işaretleri OpenRouter'da gerçek.** neo'nun cache_read oranı
k2 %65 → o1 %85 → z1 %92. Gerçek harcama, fiyat-tablosu tahmininin
~1/3'ü. Dünkü "OpenCode %77 ile 6,7 kat ucuz" farkı kapandı: gerçek dolar
farkı artık 1,5 kat ve z1'i teslim EDEN taraf neo.

**4. neo'nun kalan israfı: edit anchor'ı.** z1'deki 18 hatalı aracın 7'si
`edit_file` "aranan metin dosyada yok" (girinti/satır-sonu birebir
tutmuyor). Sıradaki kaldıraç: düzenleme aracına daha bağışlayıcı eşleşme
ya da satır-aralığı kipi. 1 heredoc denemesi (PowerShell'de `<<EOF`) hâlâ
görüldü — tanımdaki uyarı ilk denemeyi engellemedi ama ipucu tek seferde
düzelttirdi.

**5. Plan dürtüsü eşiği geniş.** 10 satırlık o1 bile "[Plan] Bu iş büyük
görünüyor" notu yedi. `buyuk_is` kalibre edilmeli (todo'da).

**6. Referans çizgisi.** Claude Code şeridi üç görevi 147 sn'de, hepsi
kendi testiyle yeşil teslim etti (z1 98,7 — test-adedi ekseninden kırpıldı).
Model gücü ayrı konu; neo'nun hedefi aynı disiplin refleksleriyle o
çizgiye yaklaşmak — z1'de 0 değil 82 üretmesi bu reflekslerin işi.

## Ham veri

- neo: `sonuclar/20260828T155549Z-z-ai-glm-5.3-flash.json` (davranış
  sütunları dahil; alanlar `--sakla` ile geçici dizinde bırakıldı)
- OpenCode: scratchpad `kiyas/sonuc-opencode.json` + `oc-*-olaylar.jsonl`
- Claude: scratchpad `kiyas/sonuc-claude.json` (aynı ölçütle notlandı)

---

## İkinci koşu — onarımlar sonrası (28.08 akşam, yalnız neo şeridi)

Edit boşluk toleransı + kabuk stdin/ağaç düzeltmeleri commit'lendikten
sonra neo şeridi AYNI üç görevle yeniden koşuldu (taze evler, aynı model).
OpenCode ve Claude şeritleri değişmedi — onların satırları ilk koşudan.

| Görev | puan | süre | çağrı | hatalı araç | giren token (cache) | $ (tahmin) |
|---|---|---|---|---|---|---|
| k2-cli | 100 | 54 sn | 3 | 0 | 46.759 (3.456) | 0,0037 |
| o1-rapor | 100 | 38 sn | 4 | 0 | 63.941 (39.936) | 0,0050 |
| z1-arama | **100** | **178 sn** | 14 | 4 | 248.122 (225.728 · %91) | 0,0197 |
| **Toplam** | **300/300** | **270 sn** | 21 | 4 | 358.822 | ~0,0284 |

Anahtar ucundan okunan gerçek harcama (iki neo koşusu toplam): $0,0495 —
bu koşunun payı ≈ **$0,012**.

İlk koşuya göre z1: 82→100 puan, 735→178 sn, 50→14 çağrı, 18→4 hata,
1,31M→248k token, 10,3→2,0 cent. o1: stdin yarası kapandığı için 853→38 sn.

Dürüst dipnotlar:
- Toleranslı eşleşme bu koşuda hiç TETİKLENMEDİ (0 iz): kazanım kabuk
  düzeltmeleri + çaba tavanı + koşu varyansının bileşkesi. Kalan 4 hata:
  2 kırmızı test iterasyonu (normal geliştirme döngüsü), 1 gerçek içerik
  farkı olan anchor (tolerans doğru şekilde zorlamadı), 1 çakışan-madde
  belirsizliği (koruma çalıştı).
- Tek koşu; flash modelde varyans var. Eğilim (süre/token/hata çöküşü)
  yine de üç bağımsız metrikte aynı yönde.

### Güncel toplam sıralama (300 üzerinden)

| Şerit | Puan | Toplam süre | Gerçek maliyet |
|---|---|---|---|
| Claude Code (referans, kendi modeli) | 298,7 | 147 sn | — |
| **neo (onarımlar sonrası)** | **300,0** | 270 sn | ~$0,012 |
| neo (ilk koşu) | 282,0 | 1623 sn | ~$0,037 |
| OpenCode | 200,0 | 984 sn | $0,025 |

---

## Dokuz görevlik final (29.08 gecesi) — tam rapor yayın deposunda

Üç şerit dokuz görevin tamamında koşturuldu (neo ×2 tekrar ortalaması):
**Claude Code 897,3 · neo 896,7 · OpenCode 894,9** (900 üzerinden) —
tepe istatistiksel beraberlik; neo aynı modeldeki rakibinin önünde.
Test kapısı + olumsuz-şart kuralı z2'yi 55,9→100 taşıdı. Hafıza deneyleri
(tohumlu −%24, kapsül −%38, kirlilik mühürlü) dahil tam metod ve ham veri:
yayın deposunda `docs/benchmark-2026-08.md`; ham JSON'lar `sonuclar/`.
