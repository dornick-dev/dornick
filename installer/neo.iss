; neo — Windows kurulum sihirbazı (Inno Setup 6).
;
; Önce installer\build.ps1 çalıştırılır: gömülü Python + bağımlılıklar +
; kaynak + eğitim düzeneği dist\paket altına dizilir; bu betik yalnız o
; ağacı paketler. Kurulan ağaç geliştirici deposunun düzenini birebir
; taklit eder (src\, eval\, egitim\, .neocp\) — ürün kodu tek bir düzen
; tanır, "kurulumda başka yol" diye ikinci bir gerçek yoktur.
;
; GÜNCELLEME: AppId sabit; önceki kurulum registry'den (DisplayVersion)
; tanınır ve sihirbaz "kurulu sürüm → yeni sürüm" diyerek üç yol sunar:
; güncelle (varsayılan; veriler korunur), temiz kurulum (kod sıfırdan,
; veriler yine korunur), verileri de sıfırla (onay kutusu + Belgeler'e
; zip yedeği önerisiyle). Sessiz kurulumda varsayılan "güncelle";
; /TEMIZLE=temiz ya da /TEMIZLE=veri anahtarı sessizde de diğer yolları
; seçer (/YEDEK=0 yedeği kapatır — test/otomasyon için).
;
; GÜVENLİK AĞLARI (sahada yaşanan üç yaraya karşı):
;   1. Açık kopya tespiti: "-m neocp" koşan HER python(w) süreci bulunur
;      (kurulum dizini şartı yok), liste gösterilir; [Kapat ve devam]
;      nazik taskkill + doğrulama. Sessizde /KAPAT=1 ile kapatılır.
;   2. Farklı dizin uyarısı: kayıtta kurulum yeri varken başka dizin
;      seçilirse açık uyarı sayfası — önerilen "eski konuma güncelle".
;   3. HER yolda hafıza yedeği: .neocp varsa kurulumdan önce
;      Belgeler\neo-backups\neo-backup-<tarih>.zip (son 5 tutulur);
;      başarısızlık kurulumu durdurmaz ama kullanıcıya söylenir.
;      /YEDEKDIZIN=<klasör> testte hedefi değiştirir.
; Test kancaları: /SADECE_TARA=1 + /SUREC_RAPOR=<dosya> süreç taramasını
; kanıtlar ve kurulum yapmadan çıkar (installer\test_install.ps1).
;
; Kaldırıcı .neocp'ye (anılar, anahtarlar, oturumlar) ve egitim\veri'de
; sonradan biriken kişisel dosyalara DOKUNMAZ — kullanıcı verisi kalır.

; Ad, paket yolu ve kimlik /D ile ezilebilir: kurulum mantığının sandbox
; testleri gerçek kurulumun kayıt anahtarına ve kısayollarına dokunmadan
; ayrı bir kimlikle (neo-test) koşuyor — bkz. installer\test_install.ps1.
#ifndef Ad
  #define Ad "neo"
#endif
; Sürüm tek yerden: build.ps1 pyproject.toml'dan okuyup /DSurum=... ile
; geçer; elle derlemede buradaki yedek değer geçerli.
#ifndef Surum
  #define Surum "0.1.0"
#endif
#ifndef Paket
  #define Paket "dist\paket"
#endif
#ifndef KimlikGuid
  #define KimlikGuid "7E2F4B7A-9C1D-4E5B-A9D3-1F2E3D4C5B6A"
#endif

[Setup]
AppId={{{#KimlikGuid}}
AppName={#Ad}
AppVersion={#Surum}
AppPublisher=Fatih
DefaultDirName={localappdata}\{#Ad}
DisableProgramGroupPage=yes
; Önceki kurulum varsa dizin sorulmaz: güncelleme yerine kurulur.
DisableDirPage=auto
; Yönetici gerektirmez: her şey kullanıcının kendi klasörüne gider.
PrivilegesRequired=lowest
; Çalışan neo'yu Restart Manager'la kendiliğinden kapatmayı DENEME —
; nazik uyarıyı [Code] soruyor (NeoAcik), kapatma kararı kullanıcının.
CloseApplications=no
OutputDir=dist
OutputBaseFilename=neo-setup-{#Surum}
Compression=lzma2/fast
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\src\neocp\assets\neo.ico
UninstallDisplayIcon={app}\src\neocp\assets\neo.ico
WizardStyle=modern

[Languages]
; Sihirbazın dili buradan; seçim ayrıca setup.json'a yazılır ve
; uygulamanın arayüz dili ilk açılışta oradan gelir (/api/dil → dil.js).
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
tr.AnaBilesen=neo (gerekli)
en.AnaBilesen=neo (required)
tr.EgitimBileseni=Beni tanı eğitimi (gece kişisel öğrenme, ~1,5 GB)
en.EgitimBileseni=Know-me training (nightly personal learning, ~1.5 GB)
tr.DinlemeBileseni=Dinleme (mikrofon) — yerel tanıma, ~250 MB
en.DinlemeBileseni=Listening (microphone) — local recognition, ~250 MB
tr.KameraBileseni=Kamera izleme
en.KameraBileseni=Camera watching
tr.OtomatikBaslat=Windows ile başlat
en.OtomatikBaslat=Start with Windows
tr.TamKurulum=Tam kurulum (eğitim dahil)
en.TamKurulum=Full installation (with training)
tr.KucukKurulum=Yalın kurulum (yalnız uygulama)
en.KucukKurulum=Compact installation (app only)
tr.OzelKurulum=Özel kurulum
en.OzelKurulum=Custom installation
tr.GuncellemeBaslik=Önceki kurulum bulundu
en.GuncellemeBaslik=Previous installation found
tr.GuncellemeMesaj=Kurulu sürüm: %1 → Yeni sürüm: %2. Güncelleme yapılacak; anıların, ayarların, görevlerin ve otomasyonların korunur.
en.GuncellemeMesaj=Installed version: %1 → New version: %2. This will update neo; your memories, settings, tasks and automations are kept.
tr.GuncellemeAciklama=Eski kurulum bulundu. Verilerin (anılar, görevler, otomasyonlar) ne olacak?
en.GuncellemeAciklama=An existing install was found. What should happen to your data (memories, tasks, automations)?
tr.SecGuncelle=Güncelle (önerilen) — uygulama yenilenir; anılar, görevler ve otomasyonlar aynen kalır
en.SecGuncelle=Update (recommended) — app is refreshed; memories, tasks and automations stay untouched
tr.SecTemiz=Temiz kurulum — uygulama klasörleri sıfırdan yazılır; anılar/görevler/otomasyonlar yine korunur
en.SecTemiz=Clean install — app folders are rewritten; memories/tasks/automations are still kept
tr.SecVeri=Verileri de sıfırla — .neocp (anılar, görevler, otomasyonlar), atölye ve eğitim verisi silinir
en.SecVeri=Reset data too — deletes .neocp (memories, tasks, automations), workshop and training data
tr.OnayBaslik=Verileri sıfırlama onayı
en.OnayBaslik=Confirm data reset
tr.OnayAlt=Bu adım geri alınamaz
en.OnayAlt=This step cannot be undone
tr.OnayAciklama=Devam etmek için ilk kutuyu işaretle. Yedek almak istersen ikinci kutu işaretli kalsın.
en.OnayAciklama=Check the first box to continue. Keep the second box checked if you want a backup.
tr.OnayAnladim=Anılarım, görevlerim ve kişisel verilerim kalıcı olarak silinecek — anladım
en.OnayAnladim=My memories, tasks and personal data will be permanently deleted — I understand
tr.OnayYedek=Silmeden önce yedek al: Belgeler\neo-backup-<tarih>.zip
en.OnayYedek=Back up before deleting: Documents\neo-backup-<date>.zip
tr.YedekHata=Yedek alınamadı; hiçbir şey silinmedi. Diskte yer aç ya da yedek seçeneğini kaldırıp yeniden dene.
en.YedekHata=Backup failed; nothing was deleted. Free some disk space or untick the backup option and try again.
tr.NeoAcikBaslik=Açık neo kopyaları var
en.NeoAcikBaslik=neo is currently running
tr.NeoAcikListe=Şu neo kopyaları açık:%n%n%1%nDosyalar kullanımdayken kurulum sağlıklı ilerleyemez. "Kapat ve devam" bu kopyaları nazikçe kapatır; kaydedilmemiş bir konuşma varsa yarıda kalabilir.
en.NeoAcikListe=These neo copies are open:%n%n%1%nSetup cannot proceed safely while files are in use. "Close and continue" closes these copies gently; an unsaved conversation may be cut short.
tr.KapatVeDevam=Kapat ve devam
en.KapatVeDevam=Close and continue
tr.IptalEt=İptal
en.IptalEt=Cancel
tr.KurulumIptalMesaj=Kurulum kullanıcı isteğiyle iptal edildi.
en.KurulumIptalMesaj=Setup was cancelled at the user's request.
tr.DizinBaslik=neo zaten başka bir konumda kurulu
en.DizinBaslik=neo is already installed elsewhere
tr.DizinMesaj=neo zaten şurada kurulu: %1%nAynı yere güncellemek yerine %2 içine İKİNCİ bir kopya kurmak üzeresin. İki kopya kafa karıştırır: hangisi açık, anılar hangisinde — sahada bunu yaşadık.
en.DizinMesaj=neo is already installed at: %1%nInstead of updating in place, you are about to install a SECOND copy into %2. Two copies get confusing: which one is open, which one holds the memories.
tr.DizinSoru=Nasıl devam edilsin?
en.DizinSoru=How should we proceed?
tr.SecEskiKonum=Eski konuma güncelle (önerilen) — %1
en.SecEskiKonum=Update the existing location (recommended) — %1
tr.SecIkinciKopya=Bilerek ikinci kopya kur — %1
en.SecIkinciKopya=Install a second copy on purpose — %1
tr.OtoYedekHata=Hafıza yedeği alınamadı. Kurulum sürüyor (bu adımda hiçbir veri silinmez); istersen kurulumdan önce %1 klasörünü elle yedekle.
en.OtoYedekHata=The memory backup could not be created. Setup continues (nothing is deleted in this step); you may back up %1 by hand first if you wish.
tr.YedekMemo=Hafıza yedeği (.neocp)
en.YedekMemo=Memory backup (.neocp)
tr.YedekMemoSatir=Belgeler\neo-backups içine otomatik zip alınacak (son 5 yedek tutulur)
en.YedekMemoSatir=An automatic zip will be written to Documents\neo-backups (last 5 backups are kept)

[Types]
Name: "full"; Description: "{cm:TamKurulum}"
Name: "compact"; Description: "{cm:KucukKurulum}"
Name: "custom"; Description: "{cm:OzelKurulum}"; Flags: iscustom

[Components]
Name: "ana"; Description: "{cm:AnaBilesen}"; Types: full compact custom; Flags: fixed
Name: "egitim"; Description: "{cm:EgitimBileseni}"; Types: full
Name: "dinleme"; Description: "{cm:DinlemeBileseni}"; Types: full
Name: "kamera"; Description: "{cm:KameraBileseni}"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"
Name: "autostart"; Description: "{cm:OtomatikBaslat}"; Flags: unchecked

[Files]
Source: "{#Paket}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion; Components: ana
Source: "{#Paket}\src\*"; DestDir: "{app}\src"; Flags: recursesubdirs ignoreversion; Components: ana
Source: "{#Paket}\neo.cmd"; DestDir: "{app}"; Flags: ignoreversion; Components: ana
; Sürümün tek gerçek kaynağı: ortam.surum() çalışma zamanında kökteki
; pyproject.toml'u okur — kurulu ağaç da depo gibi kökünde taşır.
Source: "{#Paket}\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion; Components: ana
Source: "{#Paket}\egitim\*"; DestDir: "{app}\egitim"; Flags: recursesubdirs ignoreversion; Components: egitim
Source: "{#Paket}\listen\*"; DestDir: "{app}\listen"; Flags: recursesubdirs ignoreversion; Components: dinleme
Source: "{#Paket}\watch\*"; DestDir: "{app}\watch"; Flags: recursesubdirs ignoreversion; Components: kamera
Source: "{#Paket}\eval\*"; DestDir: "{app}\eval"; Flags: recursesubdirs ignoreversion; Components: egitim

[Icons]
; Konsolsuz açılış: hedef pythonw, pencere webview'ın kendisi. -C "{app}"
; evi kuruluma sabitler — .neocp ve atolye hep kurulumun içinde yaşar.
Name: "{autoprograms}\{#Ad}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m neocp --app -C ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\neocp\assets\neo.ico"
Name: "{autodesktop}\{#Ad}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m neocp --app -C ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\neocp\assets\neo.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#Ad}"; ValueData: """{app}\python\pythonw.exe"" -m neocp --app -C ""{app}"""; Tasks: autostart; Flags: uninsdeletevalue
; Explorer sağ tık: Neo ile aç (dosya / klasör / masaüstü arka planı)
Root: HKCU; Subkey: "Software\Classes\*\shell\NeoOpen"; ValueType: string; ValueName: ""; ValueData: "Neo ile aç"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\NeoOpen"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\src\neocp\assets\neo.ico"
Root: HKCU; Subkey: "Software\Classes\*\shell\NeoOpen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\pythonw.exe"" -m neocp.cli --app -C ""{app}"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\Directory\shell\NeoOpen"; ValueType: string; ValueName: ""; ValueData: "Neo ile aç"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\NeoOpen"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\src\neocp\assets\neo.ico"
Root: HKCU; Subkey: "Software\Classes\Directory\shell\NeoOpen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\pythonw.exe"" -m neocp.cli --app -C ""{app}"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\NeoOpen"; ValueType: string; ValueName: ""; ValueData: "Neo ile aç"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\NeoOpen"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\src\neocp\assets\neo.ico"
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\NeoOpen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\pythonw.exe"" -m neocp.cli --app -C ""{app}"" --open ""%V"""

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m neocp --app -C ""{app}"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#Ad}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Bizim ürettiğimiz kalıntılar: dil seçimi ve çalışma sırasında oluşan
; bytecode önbellekleri (__pycache__ iç içe her pakette türüyor, o yüzden
; SALT KOD içeren klasörler bütünüyle siliniyor). .neocp ile egitim\veri
; (kişisel korpus/filigran) bilerek listede YOK — kullanıcı verisi kalır.
Type: files; Name: "{app}\setup.json"
Type: files; Name: "{app}\pyproject.toml"
; Eski sürümlerin bıraktığı ad — güncellenmiş kurulumlarda kalıntı kalmasın.
Type: files; Name: "{app}\kurulum.json"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\src"
Type: filesandordirs; Name: "{app}\eval"
Type: filesandordirs; Name: "{app}\egitim\sitepaket"
Type: filesandordirs; Name: "{app}\listen"
Type: filesandordirs; Name: "{app}\watch"
Type: filesandordirs; Name: "{app}\egitim\betikler\__pycache__"
Type: filesandordirs; Name: "{app}\egitim\model\__pycache__"
Type: filesandordirs; Name: "{app}\egitim\__pycache__"

[Code]
var
  EskiSurum: string;
  EskiYol: string;
  SecimSayfasi: TInputOptionWizardPage;
  OnaySayfasi: TInputOptionWizardPage;
  DizinSayfasi: TInputOptionWizardPage;

{ PowerShell tek-tırnaklı dizgi: yol içine tırnak gömme derdi olmadan. }
function PsT(S: string): string;
begin
  Result := '''' + S + '''';
end;

{ Komut satırında "-m neocp" geçen TÜM python(w) süreçleri — kurulum
  dizinine bakılmaz: sahada dosya-kullanımda hatası tam da "başka"
  kopyalar (geliştirici deposu, ikinci kurulum) açıkken yaşandı.
  Satır biçimi: "pid|çalıştırılabilir-yolu". Exec çıktı veremediği için
  sonuç geçici dosyadan okunuyor. }
function NeoSurecleri(): string;
var
  Kod: Integer;
  Cikti: AnsiString;
  Gecici, Komut: string;
begin
  Result := '';
  Gecici := ExpandConstant('{tmp}\neo-surec-listesi.txt');
  Komut := '/C powershell -NoProfile -Command "Get-CimInstance Win32_Process | ' +
    'Where-Object { ($_.Name -eq ''python.exe'' -or $_.Name -eq ''pythonw.exe'') ' +
    '-and $_.CommandLine -match ''-m neocp'' } | ' +
    'ForEach-Object { [string]$_.ProcessId + ''|'' + $_.ExecutablePath }" > "' +
    Gecici + '"';
  if not Exec(ExpandConstant('{cmd}'), Komut, '', SW_HIDE, ewWaitUntilTerminated, Kod) then
    exit;
  if LoadStringFromFile(Gecici, Cikti) then
    Result := Trim(string(Cikti));
  DeleteFile(Gecici);
end;

{ "pid|yol" satırlarını kullanıcıya okunur hale getirir: "yol (PID pid)". }
function ListeGoster(Liste: string): string;
var
  Satir: string;
  Ayrac: Integer;
begin
  Result := '';
  while Liste <> '' do
  begin
    Ayrac := Pos(#10, Liste);
    if Ayrac > 0 then
    begin
      Satir := Trim(Copy(Liste, 1, Ayrac - 1));
      Liste := Copy(Liste, Ayrac + 1, MaxInt);
    end
    else
    begin
      Satir := Trim(Liste);
      Liste := '';
    end;
    if Satir = '' then continue;
    Ayrac := Pos('|', Satir);
    if Ayrac > 0 then
      Result := Result + Copy(Satir, Ayrac + 1, MaxInt) +
        ' (PID ' + Copy(Satir, 1, Ayrac - 1) + ')' + #13#10
    else
      Result := Result + Satir + #13#10;
  end;
end;

{ Listedeki süreçlere taskkill. Zorla=False nazik kapatma sinyali (pencere
  kapanır gibi), Zorla=True /F — yalnız nazik deneme sonuçsuz kaldıysa. }
procedure SurecleriKapat(Liste: string; Zorla: Boolean);
var
  Satir, Pid, Anahtar: string;
  Ayrac, Kod: Integer;
begin
  Anahtar := '';
  if Zorla then Anahtar := ' /F';
  while Liste <> '' do
  begin
    Ayrac := Pos(#10, Liste);
    if Ayrac > 0 then
    begin
      Satir := Trim(Copy(Liste, 1, Ayrac - 1));
      Liste := Copy(Liste, Ayrac + 1, MaxInt);
    end
    else
    begin
      Satir := Trim(Liste);
      Liste := '';
    end;
    if Satir = '' then continue;
    Ayrac := Pos('|', Satir);
    if Ayrac > 0 then Pid := Copy(Satir, 1, Ayrac - 1) else Pid := Satir;
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/PID ' + Pid + Anahtar,
      '', SW_HIDE, ewWaitUntilTerminated, Kod);
  end;
end;

function InitializeSetup(): Boolean;
var
  Rapor: string;
begin
  { Önceki kurulumun sürümü ve yeri: sabit AppId'nin kaldırma anahtarından.
    PrivilegesRequired=lowest olduğu için anahtar HKCU'da. }
  if not RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#KimlikGuid}}_is1',
      'DisplayVersion', EskiSurum) then
    EskiSurum := '';
  if not RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#KimlikGuid}}_is1',
      'InstallLocation', EskiYol) then
    EskiYol := '';
  EskiYol := RemoveBackslash(Trim(EskiYol));
  Result := True;

  { Test kancası: /SADECE_TARA=1 açık neo süreçlerini tarar, sonucu
    /SUREC_RAPOR dosyasına yazar ve HİÇBİR ŞEY kurmadan çıkar. Sihirbaz
    sayfaları otomasyonla sürülemediği için tespit mantığı böyle
    kanıtlanıyor (bkz. installer\test_install.ps1). }
  if ExpandConstant('{param:SADECE_TARA|0}') = '1' then
  begin
    Rapor := ExpandConstant('{param:SUREC_RAPOR|}');
    if Rapor <> '' then
      SaveStringToFile(Rapor, NeoSurecleri(), False);
    Result := False;
  end;
end;

procedure OnayDegisti(Sender: TObject);
begin
  { "Anladım" işaretlenmeden İleri kapalı. }
  WizardForm.NextButton.Enabled := OnaySayfasi.Values[0];
end;

procedure InitializeWizard();
begin
  { Farklı dizin uyarısı: kayıtta bir kurulum yeri varken kullanıcı BAŞKA
    bir dizin seçtiyse ikinci kopya doğar — sahada iki kopya, "hangisi
    açık, anılar hangisinde" karmaşası yaşattı. Sayfa yalnız uyuşmazlıkta
    görünür (bkz. ShouldSkipPage); metinler sayfaya girerken gerçek
    yollarla tazelenir (bkz. CurPageChanged). }
  if (EskiYol <> '') and DirExists(EskiYol) then
  begin
    DizinSayfasi := CreateInputOptionPage(wpSelectDir,
      CustomMessage('DizinBaslik'),
      CustomMessage('DizinSoru'),
      FmtMessage(CustomMessage('DizinMesaj'), [EskiYol, '…']),
      True, False);
    DizinSayfasi.Add(FmtMessage(CustomMessage('SecEskiKonum'), [EskiYol]));
    DizinSayfasi.Add(FmtMessage(CustomMessage('SecIkinciKopya'), ['…']));
    DizinSayfasi.Values[0] := True;   { önerilen: eski konuma güncelle }
  end;

  if EskiSurum = '' then
    exit;

  { Güncelleme yolu: kurulu → yeni sürüm mesajı + üç seçenek. }
  SecimSayfasi := CreateInputOptionPage(wpSelectDir,
    CustomMessage('GuncellemeBaslik'),
    FmtMessage(CustomMessage('GuncellemeMesaj'), [EskiSurum, '{#Surum}']),
    CustomMessage('GuncellemeAciklama'), True, False);
  SecimSayfasi.Add(CustomMessage('SecGuncelle'));
  SecimSayfasi.Add(CustomMessage('SecTemiz'));
  SecimSayfasi.Add(CustomMessage('SecVeri'));
  SecimSayfasi.Values[0] := True;

  { "Verileri de sıfırla" seçilirse görünen onay sayfası. }
  OnaySayfasi := CreateInputOptionPage(SecimSayfasi.ID,
    CustomMessage('OnayBaslik'), CustomMessage('OnayAlt'),
    CustomMessage('OnayAciklama'), False, False);
  OnaySayfasi.Add(CustomMessage('OnayAnladim'));
  OnaySayfasi.Add(CustomMessage('OnayYedek'));
  OnaySayfasi.Values[1] := True;   { yedek varsayılan işaretli }
  OnaySayfasi.CheckListBox.OnClickCheck := @OnayDegisti;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (OnaySayfasi <> nil) and (PageID = OnaySayfasi.ID) then
    Result := not SecimSayfasi.Values[2];
  { Dizin uyarısı yalnız gerçek bir uyuşmazlıkta: seçilen dizin kayıttaki
    kurulum yerinden farklıysa. Aynı yer (olağan güncelleme) → sayfa yok. }
  if (DizinSayfasi <> nil) and (PageID = DizinSayfasi.ID) then
    Result := CompareText(RemoveBackslash(Trim(WizardDirValue)), EskiYol) = 0;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (OnaySayfasi <> nil) and (CurPageID = OnaySayfasi.ID) then
    WizardForm.NextButton.Enabled := OnaySayfasi.Values[0]
  else
    WizardForm.NextButton.Enabled := True;
  { Dizin uyarısına girerken metinler gerçek yollarla tazelenir: yeni
    dizin ancak kullanıcı seçince belli oluyor. }
  if (DizinSayfasi <> nil) and (CurPageID = DizinSayfasi.ID) then
  begin
    DizinSayfasi.SubCaptionLabel.Caption :=
      FmtMessage(CustomMessage('DizinMesaj'), [EskiYol, WizardDirValue]);
    DizinSayfasi.CheckListBox.ItemCaption[1] :=
      FmtMessage(CustomMessage('SecIkinciKopya'), [WizardDirValue]);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  { "Eski konuma güncelle" seçildiyse hedef dizin sessizce eskiye çevrilir
    — ikinci kopya doğmaz, olağan güncelleme yoluna girilir. }
  if (DizinSayfasi <> nil) and (CurPageID = DizinSayfasi.ID)
     and DizinSayfasi.Values[0] then
    WizardForm.DirEdit.Text := EskiYol;
end;

{ Kurulum kipi: 'guncelle' | 'temiz' | 'veri'.
  /TEMIZLE anahtarı her şeyi ezer (sessiz test/otomasyon); yoksa sihirbaz
  seçimi; sessizde sayfalar hiç görünmediği için varsayılan 'guncelle'. }
function Kip(): string;
var
  P: string;
begin
  P := LowerCase(ExpandConstant('{param:TEMIZLE|}'));
  if (P = 'veri') or (P = 'temiz') then
  begin
    Result := P;
    exit;
  end;
  Result := 'guncelle';
  if (SecimSayfasi <> nil) then
  begin
    if SecimSayfasi.Values[2] then
      Result := 'veri'
    else if SecimSayfasi.Values[1] then
      Result := 'temiz';
  end;
end;

function YedekIstendi(): Boolean;
begin
  { /YEDEK=0 kapatır; sayfa görünmediyse (sessiz) varsayılan açık. }
  if ExpandConstant('{param:YEDEK|1}') = '0' then
    Result := False
  else if OnaySayfasi <> nil then
    Result := OnaySayfasi.Values[1]
  else
    Result := True;
end;

{ HER kurulum yolunda (güncelle/temiz/yeni) hafıza yedeği: .neocp varsa
  Belgeler\neo-backups\neo-backup-<tarih>.zip. Yalnız .neocp — anıların
  ta kendisi; sahada "sıfırdan kur" yolunda anılar bir kez kaybedildi,
  bir daha olmayacak. Son 5 yedek tutulur, eskiler silinir. /YEDEKDIZIN
  testler için hedef klasörü değiştirir; /YEDEK=0 tümden kapatır. }
function OtoYedekDizin(): string;
begin
  Result := ExpandConstant('{param:YEDEKDIZIN|}');
  if Result = '' then
    Result := ExpandConstant('{userdocs}') + '\neo-backups';
end;

function OtoYedekAl(): Boolean;
var
  Kod: Integer;
  Dizin, Zip, Komut: string;
begin
  Dizin := OtoYedekDizin();
  Zip := Dizin + '\neo-backup-' +
    GetDateTimeString('yyyymmdd-hhnnss', #0, #0) + '.zip';
  Komut := '-NoProfile -ExecutionPolicy Bypass -Command "' +
    'New-Item -ItemType Directory -Force ' + PsT(Dizin) + ' | Out-Null; ' +
    'Compress-Archive -Path ' + PsT(ExpandConstant('{app}\.neocp')) +
    ' -DestinationPath ' + PsT(Zip) + ' -Force; ' +
    'if (-not (Test-Path ' + PsT(Zip) + ')) { exit 5 }; ' +
    'Get-ChildItem -Path ' + PsT(Dizin) + ' -Filter ''neo-backup-*.zip'' | ' +
    'Sort-Object Name -Descending | Select-Object -Skip 5 | Remove-Item -Force"';
  Result := Exec('powershell.exe', Komut, '', SW_HIDE, ewWaitUntilTerminated, Kod)
    and (Kod = 0);
end;

{ Belgeler'e zip yedeği: .neocp + egitim\veri + atolye (var olanlar).
  Başarısızsa boş dönmez, hata verir — yedek istenmişken sessizce
  yedeksiz silmek olmaz. }
function YedekAl(var Hata: string): Boolean;
var
  Kod: Integer;
  Uygulama, Zip, Komut: string;
begin
  Uygulama := ExpandConstant('{app}');
  Zip := ExpandConstant('{userdocs}') + '\neo-backup-' +
    GetDateTimeString('yyyymmdd-hhnnss', #0, #0) + '.zip';
  Komut := '-NoProfile -ExecutionPolicy Bypass -Command "' +
    '$k = @(' + PsT(Uygulama + '\.neocp') + ', ' +
                PsT(Uygulama + '\egitim\veri') + ', ' +
                PsT(Uygulama + '\atolye') + ') | Where-Object { Test-Path $_ }; ' +
    'if ($k) { Compress-Archive -Path $k -DestinationPath ' + PsT(Zip) + ' -Force }; ' +
    'if (($k) -and -not (Test-Path ' + PsT(Zip) + ')) { exit 5 }"';
  Result := Exec('powershell.exe', Komut, '', SW_HIDE, ewWaitUntilTerminated, Kod)
    and (Kod = 0);
  if not Result then
    Hata := CustomMessage('YedekHata');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  K, Hata, Liste, Rapor: string;
  Cevap, Deneme: Integer;
begin
  Result := '';

  { Çalışan neo kopyaları: yalnız bu kurulumun değil, "-m neocp" koşan
    HER python(w) — dosya-kullanımda hatası tam da öteki kopyalar açıkken
    yaşandı. Liste kullanıcıya gösterilir: [Kapat ve devam] nazik
    taskkill + 5 sn bekleme + doğrulama; hâlâ ayakta kalan olursa liste
    yeniden gelir ve ikinci "Kapat ve devam" zorla kapatır. [İptal]
    kurulumu durdurur. Sessizde soru soracak ekran yok: /KAPAT=1
    verildiyse kapatılır, verilmediyse eski davranış — devam. }
  Rapor := ExpandConstant('{param:SUREC_RAPOR|}');
  Liste := NeoSurecleri();
  if Rapor <> '' then
    SaveStringToFile(Rapor, Liste, False);

  Deneme := 0;
  while Liste <> '' do
  begin
    if WizardSilent() then
    begin
      if ExpandConstant('{param:KAPAT|0}') <> '1' then
        break;
    end
    else
    begin
      { Not: köşeli parantez satır başına gelmemeli — Inno satırı bölüm
        başlığı sanıyor. }
      Cevap := TaskDialogMsgBox(CustomMessage('NeoAcikBaslik'),
        FmtMessage(CustomMessage('NeoAcikListe'), [ListeGoster(Liste)]),
        mbConfirmation, MB_YESNO, [CustomMessage('KapatVeDevam'),
          CustomMessage('IptalEt')], 0);
      if Cevap <> IDYES then
      begin
        Result := CustomMessage('KurulumIptalMesaj');
        exit;
      end;
    end;
    SurecleriKapat(Liste, Deneme > 0);   { ilk tur nazik, sonrası zorla }
    Sleep(5000);
    Liste := NeoSurecleri();             { doğrulama }
    Deneme := Deneme + 1;
    { Sessizde sonsuz döngü olmaz: nazik + zorla birer kez denenir. }
    if WizardSilent() and (Deneme >= 2) then
      break;
  end;

  { Her yolda hafıza yedeği. Başarısızlık kurulumu DURDURMAZ: bu adımda
    veri silinmiyor, blokaj gereksiz — ama kullanıcıya söylenir. }
  if (ExpandConstant('{param:YEDEK|1}') <> '0')
     and DirExists(ExpandConstant('{app}\.neocp')) then
    if not OtoYedekAl() then
      SuppressibleMsgBox(FmtMessage(CustomMessage('OtoYedekHata'), [
        ExpandConstant('{app}\.neocp')]), mbError, MB_OK, IDOK);

  K := Kip();
  if K = 'veri' then
  begin
    if YedekIstendi() then
      if not YedekAl(Hata) then
      begin
        Result := Hata;   { yedek alınamadıysa HİÇBİR ŞEY silinmez }
        exit;
      end;
    DelTree(ExpandConstant('{app}\.neocp'), True, True, True);
    DelTree(ExpandConstant('{app}\atolye'), True, True, True);
    DelTree(ExpandConstant('{app}\egitim'), True, True, True);
  end;
  if (K = 'temiz') or (K = 'veri') then
  begin
    { Kod klasörleri sıfırdan; 'temiz'de egitim\veri (kişisel korpus)
      yerinde kalır, yalnız düzeneğin kod/model/çıktı kısmı gider. }
    DelTree(ExpandConstant('{app}\python'), True, True, True);
    DelTree(ExpandConstant('{app}\src'), True, True, True);
    DelTree(ExpandConstant('{app}\eval'), True, True, True);
    { Dinleme ve kamera salt kod: temiz kurulumda sıfırdan yazılır. }
    DelTree(ExpandConstant('{app}\listen'), True, True, True);
    DelTree(ExpandConstant('{app}\watch'), True, True, True);
    if K = 'temiz' then
    begin
      DelTree(ExpandConstant('{app}\egitim\sitepaket'), True, True, True);
      DelTree(ExpandConstant('{app}\egitim\betikler'), True, True, True);
      DelTree(ExpandConstant('{app}\egitim\model'), True, True, True);
      DelTree(ExpandConstant('{app}\egitim\out'), True, True, True);
      DelTree(ExpandConstant('{app}\egitim\__pycache__'), True, True, True);
      DeleteFile(ExpandConstant('{app}\egitim\ayarlar.py'));
    end;
  end;
end;

{ Özet sayfasına tek satır: kuruluma girmeden önce hafıza yedeğinin
  alınacağı görünsün — kullanıcı "anılarıma ne olacak" diye tedirgin
  olmasın. Yalnız gerçekten yedek alınacaksa yazılır. }
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := '';
  if MemoUserInfoInfo <> '' then Result := Result + MemoUserInfoInfo + NewLine + NewLine;
  if MemoDirInfo <> '' then Result := Result + MemoDirInfo + NewLine + NewLine;
  if MemoTypeInfo <> '' then Result := Result + MemoTypeInfo + NewLine + NewLine;
  if MemoComponentsInfo <> '' then Result := Result + MemoComponentsInfo + NewLine + NewLine;
  if MemoGroupInfo <> '' then Result := Result + MemoGroupInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then Result := Result + MemoTasksInfo + NewLine + NewLine;
  if (ExpandConstant('{param:YEDEK|1}') <> '0')
     and DirExists(ExpandConstant('{app}\.neocp')) then
    Result := Result + CustomMessage('YedekMemo') + NewLine +
      Space + CustomMessage('YedekMemoSatir') + NewLine;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Dil: string;
begin
  { Sihirbazda seçilen dil arayüze taşınır: localStorage kurulumdan
    yazılamaz; uygulama ilk açılışta /api/dil ile bu dosyayı okur. }
  if CurStep = ssPostInstall then
  begin
    if ActiveLanguage = 'en' then Dil := 'en' else Dil := 'tr';
    SaveStringToFile(ExpandConstant('{app}\setup.json'),
      '{"dil": "' + Dil + '"}', False);
  end;
end;
