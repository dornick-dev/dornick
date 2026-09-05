; dornick — Windows install wizard (Inno Setup 6).
;
; installer\build.ps1 runs first: embedded Python + dependencies + source +
; training rig are laid out under dist\paket; this script only packages that
; tree. The installed tree mimics the developer repo's layout exactly
; (src\, eval\, egitim\, .dornick\) — the product code knows a single layout,
; there is no second truth called "a different path when installed".
;
; UPDATE: AppId is fixed; a previous installation is recognized from the
; registry (DisplayVersion) and the wizard says "installed version → new
; version", offering three paths: update (default; data is kept), clean
; install (code from scratch, data still kept), reset data too (with a
; confirmation checkbox + an offer of a zip backup to Documents). In silent
; mode the default is "update"; the /TEMIZLE=temiz or /TEMIZLE=veri switch
; selects the other paths in silent mode too (/YEDEK=0 disables the backup —
; for tests/automation).
;
; SAFETY NETS (against three wounds experienced in the field):
;   1. Running-copy detection: EVERY python(w)/dornick.exe process running
;      "-m dornick" is found (no install-directory requirement), the list is
;      shown; [Close and continue] does a gentle taskkill + verification.
;      In silent mode /KAPAT=1 closes them.
;   2. Different-directory warning: if the registry has an install location
;      and another directory is chosen, an explicit warning page appears —
;      the recommendation is "update the existing location".
;   3. Memory backup on EVERY path: if .dornick exists, before installing,
;      Documents\dornick-backups\dornick-backup-<date>.zip (last 5 are kept);
;      a failure does not stop the install but the user is told.
;      /YEDEKDIZIN=<folder> changes the target in tests.
; Test hooks: /SADECE_TARA=1 + /SUREC_RAPOR=<file> proves the process scan
; and exits without installing (installer\test_install.ps1).
;
; The uninstaller does NOT touch .dornick (memories, keys, sessions) or the
; personal files that accumulate later in egitim\veri — user data remains.

; Name, package path and identity can be overridden with /D: the sandbox
; tests of the install logic run under a separate identity (dornick-test)
; without touching the real installation's registry key and shortcuts —
; see installer\test_install.ps1.
#ifndef AppName
  #define AppName "dornick"
#endif
; Version from a single place: build.ps1 reads pyproject.toml and passes it
; via /DVersion=...; in a manual compile the fallback value here applies.
#ifndef Version
  #define Version "0.1.0"
#endif
#ifndef Package
  #define Package "dist\paket"
#endif
#ifndef AppIdGuid
  #define AppIdGuid "17DD852A-5114-4A29-B628-75754DFA4500"  ; rebrand 01.09: fresh identity — must not replace the old neo installation
#endif

[Setup]
AppId={{{#AppIdGuid}}
AppName={#AppName}
AppVersion={#Version}
AppPublisher=Fatih
DefaultDirName={localappdata}\{#AppName}
DisableProgramGroupPage=yes
; If a previous installation exists the directory is not asked: install as update.
DisableDirPage=auto
; No administrator required: everything goes into the user's own folder.
PrivilegesRequired=lowest
; Do NOT try to close a running dornick automatically via Restart Manager —
; the gentle prompt is asked by [Code] (NeoAcik), closing is the user's call.
CloseApplications=no
OutputDir=dist
OutputBaseFilename=dornick-setup-{#Version}
Compression=lzma2/fast
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\src\dornick\assets\dornick.ico
UninstallDisplayIcon={app}\src\dornick\assets\dornick.ico
WizardStyle=modern

[Languages]
; The wizard's language comes from here; the choice is also written to
; setup.json and the app's UI language comes from there on first launch
; (/api/dil → dil.js).
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
tr.AnaBilesen=dornick (gerekli)
en.AnaBilesen=dornick (required)
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
en.GuncellemeMesaj=Installed version: %1 → New version: %2. This will update dornick; your memories, settings, tasks and automations are kept.
tr.GuncellemeAciklama=Eski kurulum bulundu. Verilerin (anılar, görevler, otomasyonlar) ne olacak?
en.GuncellemeAciklama=An existing install was found. What should happen to your data (memories, tasks, automations)?
tr.SecGuncelle=Güncelle (önerilen) — uygulama yenilenir; anılar, görevler ve otomasyonlar aynen kalır
en.SecGuncelle=Update (recommended) — app is refreshed; memories, tasks and automations stay untouched
tr.SecTemiz=Temiz kurulum — uygulama klasörleri sıfırdan yazılır; anılar/görevler/otomasyonlar yine korunur
en.SecTemiz=Clean install — app folders are rewritten; memories/tasks/automations are still kept
tr.SecVeri=Verileri de sıfırla — .dornick (anılar, görevler, otomasyonlar), atölye ve eğitim verisi silinir
en.SecVeri=Reset data too — deletes .dornick (memories, tasks, automations), workshop and training data
tr.OnayBaslik=Verileri sıfırlama onayı
en.OnayBaslik=Confirm data reset
tr.OnayAlt=Bu adım geri alınamaz
en.OnayAlt=This step cannot be undone
tr.OnayAciklama=Devam etmek için ilk kutuyu işaretle. Yedek almak istersen ikinci kutu işaretli kalsın.
en.OnayAciklama=Check the first box to continue. Keep the second box checked if you want a backup.
tr.OnayAnladim=Anılarım, görevlerim ve kişisel verilerim kalıcı olarak silinecek — anladım
en.OnayAnladim=My memories, tasks and personal data will be permanently deleted — I understand
tr.OnayYedek=Silmeden önce yedek al: Belgeler\dornick-backup-<tarih>.zip
en.OnayYedek=Back up before deleting: Documents\dornick-backup-<date>.zip
tr.YedekHata=Yedek alınamadı; hiçbir şey silinmedi. Diskte yer aç ya da yedek seçeneğini kaldırıp yeniden dene.
en.YedekHata=Backup failed; nothing was deleted. Free some disk space or untick the backup option and try again.
tr.NeoAcikBaslik=Açık dornick kopyaları var
en.NeoAcikBaslik=dornick is currently running
tr.NeoAcikListe=Şu dornick kopyaları açık:%n%n%1%nDosyalar kullanımdayken kurulum sağlıklı ilerleyemez. "Kapat ve devam" bu kopyaları nazikçe kapatır; kaydedilmemiş bir konuşma varsa yarıda kalabilir.
en.NeoAcikListe=These dornick copies are open:%n%n%1%nSetup cannot proceed safely while files are in use. "Close and continue" closes these copies gently; an unsaved conversation may be cut short.
tr.KapatVeDevam=Kapat ve devam
en.KapatVeDevam=Close and continue
tr.IptalEt=İptal
en.IptalEt=Cancel
tr.KurulumIptalMesaj=Kurulum kullanıcı isteğiyle iptal edildi.
en.KurulumIptalMesaj=Setup was cancelled at the user's request.
tr.DizinBaslik=dornick zaten başka bir konumda kurulu
en.DizinBaslik=dornick is already installed elsewhere
tr.DizinMesaj=dornick zaten şurada kurulu: %1%nAynı yere güncellemek yerine %2 içine İKİNCİ bir kopya kurmak üzeresin. İki kopya kafa karıştırır: hangisi açık, anılar hangisinde — sahada bunu yaşadık.
en.DizinMesaj=dornick is already installed at: %1%nInstead of updating in place, you are about to install a SECOND copy into %2. Two copies get confusing: which one is open, which one holds the memories.
tr.DizinSoru=Nasıl devam edilsin?
en.DizinSoru=How should we proceed?
tr.SecEskiKonum=Eski konuma güncelle (önerilen) — %1
en.SecEskiKonum=Update the existing location (recommended) — %1
tr.SecIkinciKopya=Bilerek ikinci kopya kur — %1
en.SecIkinciKopya=Install a second copy on purpose — %1
tr.OtoYedekHata=Hafıza yedeği alınamadı. Kurulum sürüyor (bu adımda hiçbir veri silinmez); istersen kurulumdan önce %1 klasörünü elle yedekle.
en.OtoYedekHata=The memory backup could not be created. Setup continues (nothing is deleted in this step); you may back up %1 by hand first if you wish.
tr.YedekMemo=Hafıza yedeği (.dornick)
en.YedekMemo=Memory backup (.dornick)
tr.YedekMemoSatir=Belgeler\dornick-backups içine otomatik zip alınacak (son 5 yedek tutulur)
en.YedekMemoSatir=An automatic zip will be written to Documents\dornick-backups (last 5 backups are kept)

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
Source: "{#Package}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion; Components: ana
Source: "{#Package}\src\*"; DestDir: "{app}\src"; Flags: recursesubdirs ignoreversion; Components: ana
Source: "{#Package}\dornick.cmd"; DestDir: "{app}"; Flags: ignoreversion; Components: ana
; The single source of truth for the version: environment.surum() reads the
; pyproject.toml at the root at runtime — the installed tree carries it at
; its root just like the repo.
Source: "{#Package}\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion; Components: ana
; skipifsourcedoesntexist: a -SkipTorch build ships no training tree; the component then installs nothing.
Source: "{#Package}\egitim\*"; DestDir: "{app}\egitim"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist; Components: egitim
Source: "{#Package}\listen\*"; DestDir: "{app}\listen"; Flags: recursesubdirs ignoreversion; Components: dinleme
Source: "{#Package}\watch\*"; DestDir: "{app}\watch"; Flags: recursesubdirs ignoreversion; Components: kamera
Source: "{#Package}\eval\*"; DestDir: "{app}\eval"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist; Components: egitim

[Icons]
; Console-less launch: the target is the stamped dornick.exe (pythonw copy).
; Task Manager looks at the PE icon; a pythonw target would leave the snake.
; -C "{app}" pins the home to the installation — .dornick and atolye always
; live inside the install.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\python\dornick.exe"; Parameters: "-m dornick --app -C ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\dornick\assets\dornick.ico"; AppUserModelID: "fatih.dornick.app"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\dornick.exe"; Parameters: "-m dornick --app -C ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\src\dornick\assets\dornick.ico"; AppUserModelID: "fatih.dornick.app"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\python\dornick.exe"" -m dornick --app -C ""{app}"""; Tasks: autostart; Flags: uninsdeletevalue
; Explorer right click: open with Dornick (file / folder / desktop background)
Root: HKCU; Subkey: "Software\Classes\*\shell\DornickOpen"; ValueType: string; ValueName: ""; ValueData: "Dornick ile aç"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\DornickOpen"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\src\dornick\assets\dornick.ico"
Root: HKCU; Subkey: "Software\Classes\*\shell\DornickOpen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\dornick.exe"" -m dornick.cli --app -C ""{app}"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\Directory\shell\DornickOpen"; ValueType: string; ValueName: ""; ValueData: "Dornick ile aç"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\DornickOpen"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\src\dornick\assets\dornick.ico"
Root: HKCU; Subkey: "Software\Classes\Directory\shell\DornickOpen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\dornick.exe"" -m dornick.cli --app -C ""{app}"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\DornickOpen"; ValueType: string; ValueName: ""; ValueData: "Dornick ile aç"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\DornickOpen"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\src\dornick\assets\dornick.ico"
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\DornickOpen\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\dornick.exe"" -m dornick.cli --app -C ""{app}"" --open ""%V"""

[Run]
; Stamp: the shortcut targets dornick.exe; if the file is missing or the ico
; version changed, python.exe (not locked) refreshes the copy, then the
; window opens.
Filename: "{app}\python\python.exe"; Parameters: "-c ""from dornick.winicon import ensure_host; ensure_host()"""; WorkingDir: "{app}"; Flags: runhidden waituntilterminated
Filename: "{app}\python\dornick.exe"; Parameters: "-m dornick --app -C ""{app}"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent skipifdoesntexist

[UninstallDelete]
; Leftovers we produce ourselves: the language choice and the bytecode
; caches created while running (__pycache__ sprouts nested in every package,
; which is why folders containing PURE CODE are deleted wholesale). .dornick
; and egitim\veri (personal corpus/watermark) are deliberately NOT listed —
; user data remains.
Type: files; Name: "{app}\setup.json"
Type: files; Name: "{app}\pyproject.toml"
; Name left behind by old versions — no leftovers in updated installs.
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
  OldVersion: string;
  OldPath: string;
  ChoicePage: TInputOptionWizardPage;
  ConfirmPage: TInputOptionWizardPage;
  DirWarnPage: TInputOptionWizardPage;

{ PowerShell single-quoted string: no quote-embedding trouble for paths. }
function PsQuote(S: string): string;
begin
  Result := '''' + S + '''';
end;

{ ALL python(w)/dornick.exe processes whose command line contains "-m dornick" —
  the install directory is not checked: in the field the file-in-use error
  happened exactly when "other" copies (developer repo, second install) were
  open. Line format: "pid|executable-path". Exec cannot return output, so
  the result is read from a temporary file. }
function DornickProcesses(): string;
var
  ResultCode: Integer;
  Output: AnsiString;
  TmpFile, Cmd: string;
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\dornick-process-list.txt');
  Cmd := '/C powershell -NoProfile -Command "Get-CimInstance Win32_Process | ' +
    'Where-Object { ($_.Name -eq ''python.exe'' -or $_.Name -eq ''pythonw.exe'' -or $_.Name -eq ''dornick.exe'') ' +
    '-and $_.CommandLine -match ''-m dornick'' } | ' +
    'ForEach-Object { [string]$_.ProcessId + ''|'' + $_.ExecutablePath }" > "' +
    TmpFile + '"';
  if not Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    exit;
  if LoadStringFromFile(TmpFile, Output) then
    Result := Trim(string(Output));
  DeleteFile(TmpFile);
end;

{ Makes "pid|path" lines readable for the user: "path (PID pid)". }
function FormatList(List: string): string;
var
  Line: string;
  Sep: Integer;
begin
  Result := '';
  while List <> '' do
  begin
    Sep := Pos(#10, List);
    if Sep > 0 then
    begin
      Line := Trim(Copy(List, 1, Sep - 1));
      List := Copy(List, Sep + 1, MaxInt);
    end
    else
    begin
      Line := Trim(List);
      List := '';
    end;
    if Line = '' then continue;
    Sep := Pos('|', Line);
    if Sep > 0 then
      Result := Result + Copy(Line, Sep + 1, MaxInt) +
        ' (PID ' + Copy(Line, 1, Sep - 1) + ')' + #13#10
    else
      Result := Result + Line + #13#10;
  end;
end;

{ taskkill for the processes in the list. Force=False is the gentle close
  signal (like closing the window), Force=True is /F — only after the
  gentle attempt came up empty. }
procedure KillProcesses(List: string; Force: Boolean);
var
  Line, Pid, Flag: string;
  Sep, ResultCode: Integer;
begin
  Flag := '';
  if Force then Flag := ' /F';
  while List <> '' do
  begin
    Sep := Pos(#10, List);
    if Sep > 0 then
    begin
      Line := Trim(Copy(List, 1, Sep - 1));
      List := Copy(List, Sep + 1, MaxInt);
    end
    else
    begin
      Line := Trim(List);
      List := '';
    end;
    if Line = '' then continue;
    Sep := Pos('|', Line);
    if Sep > 0 then Pid := Copy(Line, 1, Sep - 1) else Pid := Line;
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/PID ' + Pid + Flag,
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

function InitializeSetup(): Boolean;
var
  Report: string;
begin
  { Version and location of the previous install: from the fixed AppId's
    uninstall key. The key is under HKCU because PrivilegesRequired=lowest. }
  if not RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#AppIdGuid}}_is1',
      'DisplayVersion', OldVersion) then
    OldVersion := '';
  if not RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#AppIdGuid}}_is1',
      'InstallLocation', OldPath) then
    OldPath := '';
  OldPath := RemoveBackslash(Trim(OldPath));
  Result := True;

  { Test hook: /SADECE_TARA=1 scans running dornick processes, writes the
    result to the /SUREC_RAPOR file and exits WITHOUT installing anything.
    The wizard pages cannot be driven by automation, so the detection logic
    is proven this way (see installer\test_install.ps1). }
  if ExpandConstant('{param:SADECE_TARA|0}') = '1' then
  begin
    Report := ExpandConstant('{param:SUREC_RAPOR|}');
    if Report <> '' then
      SaveStringToFile(Report, DornickProcesses(), False);
    Result := False;
  end;
end;

procedure ConfirmChanged(Sender: TObject);
begin
  { Next stays disabled until "I understand" is checked. }
  WizardForm.NextButton.Enabled := ConfirmPage.Values[0];
end;

procedure InitializeWizard();
begin
  { Different-directory warning: if the registry holds an install location
    and the user picked ANOTHER directory, a second copy is born — in the
    field two copies caused the "which one is open, which one holds the
    memories" confusion. The page only appears on a mismatch (see
    ShouldSkipPage); the texts are refreshed with the real paths when
    entering the page (see CurPageChanged). }
  if (OldPath <> '') and DirExists(OldPath) then
  begin
    DirWarnPage := CreateInputOptionPage(wpSelectDir,
      CustomMessage('DizinBaslik'),
      CustomMessage('DizinSoru'),
      FmtMessage(CustomMessage('DizinMesaj'), [OldPath, '…']),
      True, False);
    DirWarnPage.Add(FmtMessage(CustomMessage('SecEskiKonum'), [OldPath]));
    DirWarnPage.Add(FmtMessage(CustomMessage('SecIkinciKopya'), ['…']));
    DirWarnPage.Values[0] := True;   { recommended: update the existing location }
  end;

  if OldVersion = '' then
    exit;

  { Update path: installed → new version message + three options. }
  ChoicePage := CreateInputOptionPage(wpSelectDir,
    CustomMessage('GuncellemeBaslik'),
    FmtMessage(CustomMessage('GuncellemeMesaj'), [OldVersion, '{#Version}']),
    CustomMessage('GuncellemeAciklama'), True, False);
  ChoicePage.Add(CustomMessage('SecGuncelle'));
  ChoicePage.Add(CustomMessage('SecTemiz'));
  ChoicePage.Add(CustomMessage('SecVeri'));
  ChoicePage.Values[0] := True;

  { Confirmation page shown when "Reset data too" is selected. }
  ConfirmPage := CreateInputOptionPage(ChoicePage.ID,
    CustomMessage('OnayBaslik'), CustomMessage('OnayAlt'),
    CustomMessage('OnayAciklama'), False, False);
  ConfirmPage.Add(CustomMessage('OnayAnladim'));
  ConfirmPage.Add(CustomMessage('OnayYedek'));
  ConfirmPage.Values[1] := True;   { backup checked by default }
  ConfirmPage.CheckListBox.OnClickCheck := @ConfirmChanged;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (ConfirmPage <> nil) and (PageID = ConfirmPage.ID) then
    Result := not ChoicePage.Values[2];
  { The directory warning only on a real mismatch: the selected directory
    differs from the install location in the registry. Same place (a normal
    update) → no page. }
  if (DirWarnPage <> nil) and (PageID = DirWarnPage.ID) then
    Result := CompareText(RemoveBackslash(Trim(WizardDirValue)), OldPath) = 0;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (ConfirmPage <> nil) and (CurPageID = ConfirmPage.ID) then
    WizardForm.NextButton.Enabled := ConfirmPage.Values[0]
  else
    WizardForm.NextButton.Enabled := True;
  { Entering the directory warning, the texts are refreshed with the real
    paths: the new directory only becomes known once the user picks it. }
  if (DirWarnPage <> nil) and (CurPageID = DirWarnPage.ID) then
  begin
    DirWarnPage.SubCaptionLabel.Caption :=
      FmtMessage(CustomMessage('DizinMesaj'), [OldPath, WizardDirValue]);
    DirWarnPage.CheckListBox.ItemCaption[1] :=
      FmtMessage(CustomMessage('SecIkinciKopya'), [WizardDirValue]);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  { If "update the existing location" was chosen, the target directory is
    silently switched back to the old one — no second copy is born, the
    normal update path is taken. }
  if (DirWarnPage <> nil) and (CurPageID = DirWarnPage.ID)
     and DirWarnPage.Values[0] then
    WizardForm.DirEdit.Text := OldPath;
end;

{ Install mode: 'guncelle' | 'temiz' | 'veri'.
  The /TEMIZLE switch overrides everything (silent test/automation);
  otherwise the wizard choice; in silent mode the pages never appear so the
  default is 'guncelle'. }
function InstallMode(): string;
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
  if (ChoicePage <> nil) then
  begin
    if ChoicePage.Values[2] then
      Result := 'veri'
    else if ChoicePage.Values[1] then
      Result := 'temiz';
  end;
end;

function BackupWanted(): Boolean;
begin
  { /YEDEK=0 disables it; if the page never showed (silent), default is on. }
  if ExpandConstant('{param:YEDEK|1}') = '0' then
    Result := False
  else if ConfirmPage <> nil then
    Result := ConfirmPage.Values[1]
  else
    Result := True;
end;

{ Memory backup on EVERY install path (update/clean/new): if .dornick exists,
  Documents\dornick-backups\dornick-backup-<date>.zip. Only .dornick — the
  memories themselves; in the field the memories were lost once on the
  "install from scratch" path, never again. The last 5 backups are kept,
  older ones are deleted. /YEDEKDIZIN changes the target folder for tests;
  /YEDEK=0 disables it entirely. }
function AutoBackupDir(): string;
begin
  Result := ExpandConstant('{param:YEDEKDIZIN|}');
  if Result = '' then
    Result := ExpandConstant('{userdocs}') + '\dornick-backups';
end;

function AutoBackup(): Boolean;
var
  ResultCode: Integer;
  BackupDir, Zip, Cmd: string;
begin
  BackupDir := AutoBackupDir();
  Zip := BackupDir + '\dornick-backup-' +
    GetDateTimeString('yyyymmdd-hhnnss', #0, #0) + '.zip';
  Cmd := '-NoProfile -ExecutionPolicy Bypass -Command "' +
    'New-Item -ItemType Directory -Force ' + PsQuote(BackupDir) + ' | Out-Null; ' +
    'Compress-Archive -Path ' + PsQuote(ExpandConstant('{app}\.dornick')) +
    ' -DestinationPath ' + PsQuote(Zip) + ' -Force; ' +
    'if (-not (Test-Path ' + PsQuote(Zip) + ')) { exit 5 }; ' +
    'Get-ChildItem -Path ' + PsQuote(BackupDir) + ' -Filter ''dornick-backup-*.zip'' | ' +
    'Sort-Object Name -Descending | Select-Object -Skip 5 | Remove-Item -Force"';
  Result := Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
    and (ResultCode = 0);
end;

{ Zip backup to Documents: .dornick + egitim\veri + atolye (those that exist).
  On failure it does not return empty-handed, it raises the error — deleting
  without a backup, silently, when a backup was requested, is not on. }
function TakeBackup(var Err: string): Boolean;
var
  ResultCode: Integer;
  AppDir, Zip, Cmd: string;
begin
  AppDir := ExpandConstant('{app}');
  Zip := ExpandConstant('{userdocs}') + '\dornick-backup-' +
    GetDateTimeString('yyyymmdd-hhnnss', #0, #0) + '.zip';
  Cmd := '-NoProfile -ExecutionPolicy Bypass -Command "' +
    '$k = @(' + PsQuote(AppDir + '\.dornick') + ', ' +
                PsQuote(AppDir + '\egitim\veri') + ', ' +
                PsQuote(AppDir + '\atolye') + ') | Where-Object { Test-Path $_ }; ' +
    'if ($k) { Compress-Archive -Path $k -DestinationPath ' + PsQuote(Zip) + ' -Force }; ' +
    'if (($k) -and -not (Test-Path ' + PsQuote(Zip) + ')) { exit 5 }"';
  Result := Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
    and (ResultCode = 0);
  if not Result then
    Err := CustomMessage('YedekHata');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  M, Err, List, Report: string;
  Answer, Attempt: Integer;
begin
  Result := '';

  { Running dornick copies: not just this installation's — EVERY python(w)
    running "-m dornick"; the file-in-use error happened exactly when the
    other copies were open. The list is shown to the user: [Close and
    continue] is a gentle taskkill + 5 s wait + verification; if any are
    still standing the list comes back and a second "Close and continue"
    force-kills. [Cancel] stops the install. In silent mode there is no
    screen to ask on: with /KAPAT=1 they are closed, without it the old
    behaviour — continue. }
  Report := ExpandConstant('{param:SUREC_RAPOR|}');
  List := DornickProcesses();
  if Report <> '' then
    SaveStringToFile(Report, List, False);

  Attempt := 0;
  while List <> '' do
  begin
    if WizardSilent() then
    begin
      if ExpandConstant('{param:KAPAT|0}') <> '1' then
        break;
    end
    else
    begin
      { Note: the square bracket must not start a line — Inno would take the
        line for a section header. }
      Answer := TaskDialogMsgBox(CustomMessage('NeoAcikBaslik'),
        FmtMessage(CustomMessage('NeoAcikListe'), [FormatList(List)]),
        mbConfirmation, MB_YESNO, [CustomMessage('KapatVeDevam'),
          CustomMessage('IptalEt')], 0);
      if Answer <> IDYES then
      begin
        Result := CustomMessage('KurulumIptalMesaj');
        exit;
      end;
    end;
    KillProcesses(List, Attempt > 0);   { first round gentle, then forced }
    Sleep(5000);
    List := DornickProcesses();         { verification }
    Attempt := Attempt + 1;
    { No endless loop in silent mode: gentle + forced are tried once each. }
    if WizardSilent() and (Attempt >= 2) then
      break;
  end;

  { Memory backup on every path. A failure does NOT stop the install: no
    data is deleted in this step, blocking would be pointless — but the
    user is told. }
  if (ExpandConstant('{param:YEDEK|1}') <> '0')
     and DirExists(ExpandConstant('{app}\.dornick')) then
    if not AutoBackup() then
      SuppressibleMsgBox(FmtMessage(CustomMessage('OtoYedekHata'), [
        ExpandConstant('{app}\.dornick')]), mbError, MB_OK, IDOK);

  M := InstallMode();
  if M = 'veri' then
  begin
    if BackupWanted() then
      if not TakeBackup(Err) then
      begin
        Result := Err;   { if the backup failed, NOTHING is deleted }
        exit;
      end;
    DelTree(ExpandConstant('{app}\.dornick'), True, True, True);
    DelTree(ExpandConstant('{app}\atolye'), True, True, True);
    DelTree(ExpandConstant('{app}\egitim'), True, True, True);
  end;
  if (M = 'temiz') or (M = 'veri') then
  begin
    { Code folders from scratch; in 'temiz', egitim\veri (personal corpus)
      stays in place, only the rig's code/model/output part goes. }
    DelTree(ExpandConstant('{app}\python'), True, True, True);
    DelTree(ExpandConstant('{app}\src'), True, True, True);
    DelTree(ExpandConstant('{app}\eval'), True, True, True);
    { Listening and camera are pure code: rewritten from scratch in a clean install. }
    DelTree(ExpandConstant('{app}\listen'), True, True, True);
    DelTree(ExpandConstant('{app}\watch'), True, True, True);
    if M = 'temiz' then
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

{ One line on the summary page: make it visible before installing that a
  memory backup will be taken — the user should not fret "what happens to
  my memories". Written only when a backup will actually be taken. }
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
     and DirExists(ExpandConstant('{app}\.dornick')) then
    Result := Result + CustomMessage('YedekMemo') + NewLine +
      Space + CustomMessage('YedekMemoSatir') + NewLine;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lang: string;
begin
  { The language chosen in the wizard is carried to the UI: localStorage
    cannot be written from the installer; the app reads this file on first
    launch via /api/dil. }
  if CurStep = ssPostInstall then
  begin
    if ActiveLanguage = 'en' then Lang := 'en' else Lang := 'tr';
    SaveStringToFile(ExpandConstant('{app}\setup.json'),
      '{"dil": "' + Lang + '"}', False);
  end;
end;
