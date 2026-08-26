; neo — Windows kurulum sihirbazı (Inno Setup 6).
;
; Önce installeruild.ps1 çalıştırılır: gömülü Python + bağımlılıklar +
; kaynak + eğitim düzeneği dist\paket altına dizilir; bu betik yalnız o
; ağacı paketler. Kurulan ağaç geliştirici deposunun düzenini birebir
; taklit eder (src\, eval\, training\, .neocp\) — ürün kodu tek bir düzen
; tanır, "kurulumda başka yol" diye ikinci bir gerçek yoktur.
;
; Kaldırıcı .neocp'ye (anılar, anahtarlar, oturumlar) ve training\data'da
; sonradan biriken kişisel dosyalara DOKUNMAZ — kullanıcı verisi kalır.

#define Ad "neo"
#define Surum "0.1.0"
#define Paket "dist\paket"

[Setup]
AppId={{7E2F4B7A-9C1D-4E5B-A9D3-1F2E3D4C5B6A}
AppName={#Ad}
AppVersion={#Surum}
AppPublisher=Fatih
DefaultDirName={localappdata}\{#Ad}
DisableProgramGroupPage=yes
; Yönetici gerektirmez: her şey kullanıcının kendi klasörüne gider.
PrivilegesRequired=lowest
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
tr.OtomatikBaslat=Windows ile başlat
en.OtomatikBaslat=Start with Windows
tr.TamKurulum=Tam kurulum (eğitim dahil)
en.TamKurulum=Full installation (with training)
tr.KucukKurulum=Yalın kurulum (yalnız uygulama)
en.KucukKurulum=Compact installation (app only)
tr.OzelKurulum=Özel kurulum
en.OzelKurulum=Custom installation

[Types]
Name: "full"; Description: "{cm:TamKurulum}"
Name: "compact"; Description: "{cm:KucukKurulum}"
Name: "custom"; Description: "{cm:OzelKurulum}"; Flags: iscustom

[Components]
Name: "ana"; Description: "{cm:AnaBilesen}"; Types: full compact custom; Flags: fixed
Name: "egitim"; Description: "{cm:EgitimBileseni}"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"
Name: "autostart"; Description: "{cm:OtomatikBaslat}"; Flags: unchecked

[Files]
Source: "{#Paket}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion; Components: ana
Source: "{#Paket}\src\*"; DestDir: "{app}\src"; Flags: recursesubdirs ignoreversion; Components: ana
Source: "{#Paket}\neo.cmd"; DestDir: "{app}"; Flags: ignoreversion; Components: ana
Source: "{#Paket}\training\*"; DestDir: "{app}\training"; Flags: recursesubdirs ignoreversion; Components: egitim
Source: "{#Paket}\eval\*"; DestDir: "{app}\eval"; Flags: recursesubdirs ignoreversion; Components: egitim

[Icons]
; Konsolsuz açılış: hedef pythonw, pencere webview'ın kendisi. -C "{app}"
; evi kuruluma sabitler — .neocp ve atolye hep kurulumun içinde yaşar.
Name: "{autoprograms}\{#Ad}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m neocp --app -C ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\neocp\assets\neo.ico"
Name: "{autodesktop}\{#Ad}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m neocp --app -C ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\neocp\assets\neo.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#Ad}"; ValueData: """{app}\python\pythonw.exe"" -m neocp --app -C ""{app}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m neocp --app -C ""{app}"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#Ad}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Bizim ürettiğimiz kalıntılar: dil seçimi ve çalışma sırasında oluşan
; bytecode önbellekleri (__pycache__ iç içe her pakette türüyor, o yüzden
; SALT KOD içeren klasörler bütünüyle siliniyor). .neocp ile training\data
; (kişisel korpus/filigran) bilerek listede YOK — kullanıcı verisi kalır.
Type: files; Name: "{app}\setup.json"
; Eski sürümlerin bıraktığı ad — güncellenmiş kurulumlarda kalıntı kalmasın.
Type: files; Name: "{app}\kurulum.json"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\src"
Type: filesandordirs; Name: "{app}\eval"
Type: filesandordirs; Name: "{app}\training\site"
Type: filesandordirs; Name: "{app}\training\scripts\__pycache__"
Type: filesandordirs; Name: "{app}\training\model\__pycache__"
Type: filesandordirs; Name: "{app}\training\__pycache__"

[Code]
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
