# Uygulamalar + sohbet geçişi

- [x] WinExe/.NET → `desktop` (betik değil); Başlat gerçek .exe açar
- [x] Manifest `tool` yumuşak düzeltme → masaüstü
- [x] Aç = masaüstünde Başlat; süzgeçlere Masaüstü eklendi
- [x] Sohbet geçişi: batch paint + tek history load (takılma ↓)
- [x] Geçmişte dosya/görsel önizleme (reviveUserMedia)
- [x] test_apps 32 geçti

## Review

NeoScada sınıfı artık masaüstü; Başlat `os.startfile` ile pencere açıyor. Sohbet yeniden açılışında medya çipleri ve görseller geri geliyor.
