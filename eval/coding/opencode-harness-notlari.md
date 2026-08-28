# OpenCode harness incelemesi — neo'ya uygulama haritası (28.08.2026)

Kaynak: github.com/sst/opencode, sığ klon; okunan yerler:
`packages/opencode/src/session/system.ts`, `session/prompt/*.txt`,
`tool/*.txt`, `provider/transform.ts`. Kıyas bağlamı:
[kiyas-opencode-2608.md](kiyas-opencode-2608.md) — aynı model (glm-5.3-flash),
OpenCode 5 adım/0 hata/140 sn/%77 önbellek; neo 16 tur/6 hatalı araç/671 sn.

## Bulgular

1. **Model başına ayrı sistem istemi.** `system.ts:provider()` model
   kimliğine bakıp 10 istemden birini seçiyor (anthropic/gpt/codex/gemini/
   kimi/beast/…). GLM `default.txt`e düşüyor: **8,6 KB** — kısa, emir
   kipinde, örnekli. neo tek istemle her modele aynı metni taşıyor.
2. **İstem önbelleği: ilk 2 sistem + son 2 mesaj, her sağlayıcıda.**
   `transform.ts:applyCaching()` — OpenRouter dahil `cache_control:
   ephemeral` içerik parçasına konuyor. %77 isabetin ve ~6,7× maliyet
   farkının ana kaynağı. → **neo'ya işlendi** (openai_backend:
   `_cache_isaretle`, yalnız OpenRouter, redde bir-kez-öğren geri çekilme,
   3 testli).
3. **Ortam bloğu minimal.** Model kimliği + `<env>` (cwd, git mi, platform,
   tarih) — hepsi bu. Dizin dökümü, uzun yetenek listesi yok; keşif modele
   bırakılmış (arama araçlarını "extensively, in parallel" kullan emriyle).
4. **Kısalık sözleşmesi çok sert.** "≤4 satır, tek kelime en iyisi,
   önsöz/özet yok" + 6 örnek. Flash sınıfı modellde gevezeliği kesen şey
   bu — neo'daki ara anlatım turlarının ("Düzeltiyorum:") panzehiri.
5. **Todo aracı davranış sözleşmesi gibi yazılmış.** `todowrite.txt`:
   "TEK in_progress", "completed'i niyetle değil DOĞRULAMADAN sonra
   işaretle", "engellendiyse in_progress bırak + engel maddesi ekle".
   Kabul-listesi kapımızın istem tarafı buradan uyarlanabilir.
6. **Araç hataları öğretici metin.** `edit.txt` hatanın TAM metnini ve
   çıkışını önceden anlatıyor ("oldString not found…", "Found multiple
   matches… provide more surrounding lines / use replaceAll"). Hata mesajı
   = sonraki turun düzeltme ipucu. → bizim "hata ipucu normalize" işi.
7. **Teslim kapısı istemde:** "bitirince lint/typecheck KOŞ; komutu
   bulamazsan kullanıcıya sor ve AGENTS.md'ye yazmayı öner". Yeşilse-dur
   refleksimizin kardeşi.

## neo uygulama sırası

- [x] (2) Önbellek işaretleri — bu commit'te, testli. Ölçü: bir sonraki
  kıyas koşusunda cache_read oranı davranış tablosuna girecek.
- [ ] (4)+(3) İstem diyeti: neo sisteminin bayt dökümü çıkarılıp OpenCode
  default'uyla yan yana konacak; hedef tur başına ≤16k giren token ve
  bayt-bayt kararlı önek (tarih/dinamik parçalar önekten sona).
- [ ] (1) Model-aile istem seçimi: en azından "flash/küçük" ailesi için
  sert-kısalık varyantı.
- [ ] (5) Kabul-listesi kapısı (loop.py refleksi) — todowrite sözleşmesi
  istem dili olarak temel.
- [ ] (6) Araç hatalarını öğretici kalıba çevirme (shell tırnak/kaçış
  hataları başta).
- [ ] (7) Yeşilse-dur + lint/test teslim kapısı.
