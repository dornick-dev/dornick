# Kurulum sihirbazının güvenlik ağlarını sandbox'ta kanıtlar.
#
# Gerçek kuruluma DOKUNMAZ: test derlemesi ayrı bir AppId (KimlikGuid) ve
# ayrı bir ad (neo-test) ile yapılır — kayıt anahtarı, kısayollar ve dosya
# ağacı tamamen izole. Paket içeriği de saplama (stub): sınanan şey
# neo.iss'in [Code] mantığı — dosya kopyalamanın kendisi değil.
#
# Senaryolar:
#   1. Temiz kurulum (0.2.1) — .neocp yokken yedek zip'i OLUŞMAZ.
#   2. Sahte .neocp koy → üstüne 0.2.2 güncelle — yedek zip'i OLUŞUR,
#      içinde .neocp\anilar.json vardır, kurulumdaki veriler yerindedir,
#      kayıtta DisplayVersion 0.2.2 olur.
#   3. Yedek rotasyonu — klasörde 6 eski zip varken bir güncelleme daha:
#      yalnız en yeni 5 kalır, en eskiler silinir.
#   4. Açık kopya tespiti — gerçek bir "-m neocp" süreci başlatılır
#      (recall-mcp: modelsiz, penceresiz, stdin'de bekler); kurulum
#      /SADECE_TARA=1 /SUREC_RAPOR=<dosya> ile çağrılır ve raporda o
#      PID'nin listelendiği kanıtlanır. (Sihirbaz sayfası otomasyonla
#      sürülemediği için [Code] mantığı parametreyle sınanıyor.)
#   5. Nazik/zorla kapatma zinciri — konsol sürecine nazik taskkill'in
#      yetmediği, /F'nin öldürdüğü kanıtlanır (kurulumdaki Deneme>0
#      tırmanışının gerekçesi).
#   6. Kaldırma — .neocp kaldırmadan SONRA da yerindedir.
#
# Kullanım: powershell -ExecutionPolicy Bypass -File installer\test_kurulum.ps1

param(
    # Sandbox kökü. Belgeler'e ve gerçek kuruluma bulaşmaz.
    [string]$Kok = (Join-Path $env:TEMP "neo-kurulum-test")
)

$ErrorActionPreference = "Stop"
$Depo = Split-Path -Parent $PSScriptRoot
$TestGuid = "5A5A5A5A-1111-4222-8333-444455556666"
$KayitYolu = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{$TestGuid}_is1"
# Gerçek bir Python 3.11+ (WindowsApps saplaması değil): py başlatıcısından.
$Py = ""
try { $Py = (& py -3.11 -c "import sys; print(sys.executable)").Trim() } catch { }
if (-not $Py) {
    $aday = Get-Command python -ErrorAction SilentlyContinue
    if ($aday) { $Py = $aday.Source }
}
if (-not $Py) { throw "Python bulunamadı — açık kopya senaryosu için gerekli" }

$Basarisiz = @()
function Dogrula([bool]$kosul, [string]$mesaj) {
    if ($kosul) { Write-Host "  OK   $mesaj" -ForegroundColor Green }
    else { Write-Host "  FAIL $mesaj" -ForegroundColor Red; $script:Basarisiz += $mesaj }
}

# -- iscc ---------------------------------------------------------------
$iscc = $null
foreach ($p in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
                 "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                 "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
    if (Test-Path $p) { $iscc = $p; break }
}
if (-not $iscc) { throw "ISCC bulunamadı — Inno Setup 6 gerekli" }

# -- 0) temiz sandbox ---------------------------------------------------
if (Test-Path $Kok) { Remove-Item -Recurse -Force $Kok }
foreach ($alt in @("paket", "cikti", "kurulum", "yedek", "calisma")) {
    New-Item -ItemType Directory -Force (Join-Path $Kok $alt) | Out-Null
}
$Paket = Join-Path $Kok "paket"
$Cikti = Join-Path $Kok "cikti"
$Hedef = Join-Path $Kok "kurulum"
$Yedek = Join-Path $Kok "yedek"

# -- 1) saplama paket ---------------------------------------------------
# [Files] bölümündeki her kaynak dizin var olmalı; içerik önemsiz.
foreach ($d in @("python", "src\neocp\assets", "egitim", "listen", "watch", "eval")) {
    New-Item -ItemType Directory -Force (Join-Path $Paket $d) | Out-Null
}
"saplama" | Set-Content (Join-Path $Paket "python\bos.txt")
"saplama" | Set-Content (Join-Path $Paket "egitim\bos.txt")
"saplama" | Set-Content (Join-Path $Paket "listen\bos.txt")
"saplama" | Set-Content (Join-Path $Paket "watch\bos.txt")
"saplama" | Set-Content (Join-Path $Paket "eval\bos.txt")
"@echo off" | Set-Content (Join-Path $Paket "neo.cmd")
Copy-Item (Join-Path $Depo "pyproject.toml") $Paket
Copy-Item (Join-Path $Depo "src\neocp\assets\neo.ico") (Join-Path $Paket "src\neocp\assets")

# -- 2) test derlemeleri (0.2.1 ve 0.2.2) --------------------------------
Write-Host "`n== Derleme (izole kimlik: neo-test / $TestGuid)" -ForegroundColor Cyan
foreach ($v in @("0.2.1", "0.2.2")) {
    & $iscc /Qp "/DSurum=$v" "/DAd=neo-test" "/DKimlikGuid=$TestGuid" `
        "/DPaket=$Paket" "/O$Cikti" (Join-Path $PSScriptRoot "neo.iss")
    if ($LASTEXITCODE -ne 0) { throw "iscc başarısız (sürüm $v)" }
}
$Kur021 = Join-Path $Cikti "neo-setup-0.2.1.exe"
$Kur022 = Join-Path $Cikti "neo-setup-0.2.2.exe"

function Kur([string]$exe, [string[]]$ekstra) {
    $argListe = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                  "/DIR=$Hedef", "/MERGETASKS=!desktopicon",
                  "/YEDEKDIZIN=$Yedek") + $ekstra
    $p = Start-Process -FilePath $exe -ArgumentList $argListe -Wait -PassThru
    return $p.ExitCode
}

# -- 3) senaryo: temiz kurulum ------------------------------------------
Write-Host "`n== Senaryo 1: temiz kurulum (0.2.1), .neocp yok" -ForegroundColor Cyan
$kod = Kur $Kur021 @()
Dogrula ($kod -eq 0) "kurulum çıkış kodu 0 (gerçek: $kod)"
Dogrula (Test-Path (Join-Path $Hedef "pyproject.toml")) "pyproject.toml kuruluma gitti (sürümün tek kaynağı)"
$ds = (Get-ItemProperty $KayitYolu -ErrorAction SilentlyContinue).DisplayVersion
Dogrula ($ds -eq "0.2.1") "kayıtta DisplayVersion 0.2.1 (gerçek: $ds)"
Dogrula (@(Get-ChildItem $Yedek -Filter "neo-backup-*.zip" -ErrorAction SilentlyContinue).Count -eq 0) ".neocp yokken yedek zip'i oluşmadı"

# -- 4) senaryo: sahte .neocp + güncelleme -------------------------------
Write-Host "`n== Senaryo 2: sahte .neocp koy, üstüne 0.2.2 güncelle" -ForegroundColor Cyan
$Neocp = Join-Path $Hedef ".neocp"
New-Item -ItemType Directory -Force (Join-Path $Neocp "mind") | Out-Null
'{"ani": "kıymetli hatıra"}' | Set-Content (Join-Path $Neocp "anilar.json") -Encoding utf8
"sqlite-saplama" | Set-Content (Join-Path $Neocp "mind\recall.db")

$kod = Kur $Kur022 @()
Dogrula ($kod -eq 0) "güncelleme çıkış kodu 0 (gerçek: $kod)"
$ds = (Get-ItemProperty $KayitYolu -ErrorAction SilentlyContinue).DisplayVersion
Dogrula ($ds -eq "0.2.2") "kayıtta DisplayVersion 0.2.2 oldu (gerçek: $ds)"
$zipler = @(Get-ChildItem $Yedek -Filter "neo-backup-*.zip" | Sort-Object Name)
Dogrula ($zipler.Count -eq 1) "yedek zip'i OLUŞTU (adet: $($zipler.Count))"
Dogrula ((Get-Content (Join-Path $Neocp "anilar.json") -Raw) -match "kıymetli") "kurulumdaki .neocp verisi yerinde"

# Zip'in içinde gerçekten anılar var mı?
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipler[0].FullName)
try {
    $girdiler = @($zip.Entries | ForEach-Object { $_.FullName })
} finally { $zip.Dispose() }
Dogrula (($girdiler -join "`n") -match "anilar\.json") "zip .neocp\anilar.json içeriyor"
Dogrula (($girdiler -join "`n") -match "recall\.db") "zip .neocp\mind\recall.db içeriyor"

# -- 5) senaryo: yedek rotasyonu ----------------------------------------
Write-Host "`n== Senaryo 3: 6 eski yedek varken güncelleme — son 5 kalır" -ForegroundColor Cyan
foreach ($n in 1..6) {
    "eski" | Set-Content (Join-Path $Yedek ("neo-backup-20200101-00000$n.zip"))
}
$kod = Kur $Kur022 @()
Dogrula ($kod -eq 0) "yeniden kurulum çıkış kodu 0 (gerçek: $kod)"
$kalan = @(Get-ChildItem $Yedek -Filter "neo-backup-*.zip" | Sort-Object Name)
Dogrula ($kalan.Count -eq 5) "yalnız 5 yedek kaldı (gerçek: $($kalan.Count))"
Dogrula (-not (Test-Path (Join-Path $Yedek "neo-backup-20200101-000001.zip"))) "en eski yedek silindi"
Dogrula (($kalan[-1].Name) -match "neo-backup-2") "en yeni yedek duruyor ($($kalan[-1].Name))"

# -- 6) senaryo: açık kopya tespiti -------------------------------------
Write-Host "`n== Senaryo 4: açık '-m neocp' süreci kurulumca tespit edilir" -ForegroundColor Cyan
# recall-mcp: modelsiz ve penceresiz gerçek bir neocp süreci; stdio
# protokolü stdin'de beklediği için stdin'i açık tutarak yaşatıyoruz.
$Calisma = Join-Path $Kok "calisma"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Py
$psi.Arguments = "-m neocp recall-mcp -C `"$Calisma`""
$psi.WorkingDirectory = $Depo
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$surec = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Seconds 3
try {
    Dogrula (-not $surec.HasExited) "sandbox neocp süreci ayakta (PID $($surec.Id))"
    $Rapor = Join-Path $Kok "surec-raporu.txt"
    $p = Start-Process -FilePath $Kur022 -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SADECE_TARA=1",
        "/SUREC_RAPOR=$Rapor") -Wait -PassThru
    Dogrula ($p.ExitCode -ne 0) "/SADECE_TARA kurulum yapmadan çıktı (kod: $($p.ExitCode))"
    $icerik = ""
    if (Test-Path $Rapor) { $icerik = Get-Content $Rapor -Raw }
    Dogrula ($icerik -match [regex]::Escape("$($surec.Id)|")) "rapor sandbox sürecinin PID'sini listeliyor"
    Write-Host "  rapor içeriği:`n$(($icerik -split "`n" | ForEach-Object { '    ' + $_ }) -join "`n")"

    # -- 7) senaryo: nazik → zorla kapatma zinciri ----------------------
    Write-Host "`n== Senaryo 5: nazik taskkill yetmez, /F öldürür (Deneme>0 gerekçesi)" -ForegroundColor Cyan
    cmd /c "taskkill /PID $($surec.Id) >nul 2>&1"
    Start-Sleep -Seconds 2
    $nazikYetti = $surec.HasExited
    if (-not $nazikYetti) {
        cmd /c "taskkill /PID $($surec.Id) /F >nul 2>&1"
        Start-Sleep -Seconds 2
    }
    Dogrula $surec.HasExited "süreç kapatıldı (nazik yetti: $nazikYetti; kurulumda aynı tırmanış var)"
} finally {
    if (-not $surec.HasExited) { $surec.Kill() }
}

# -- 8) senaryo: kaldırma .neocp'ye dokunmaz ----------------------------
Write-Host "`n== Senaryo 7: TEMİZ KURULUM — kod sıfırdan, VERİ DURUR" -ForegroundColor Cyan
# Kullanıcının "temiz kur" dediğinde beklediği şey: bozulmuş bir kurulumun
# kodu gitsin ama anıları/görevleri KALSIN. İkisi karışırsa kullanıcı
# "temiz kurulum" derken hafızasını siliyor demektir.
New-Item -ItemType Directory -Force (Join-Path $Neocp "mind") | Out-Null
'{"n":"temiz-senaryo"}' | Set-Content (Join-Path $Neocp "anilar.json") -Encoding utf8
'gorev' | Set-Content (Join-Path $Neocp "tasks.json") -Encoding utf8
$sahteKod = Join-Path (Join-Path $Hedef 'src') 'artik.py'
New-Item -ItemType Directory -Force (Join-Path $Hedef 'src') | Out-Null
'eski surumden kalan' | Set-Content $sahteKod -Encoding utf8

$kod = Kur $Kur022 @("/TEMIZLE=temiz")
Dogrula ($kod -eq 0) "temiz kurulum çıkış kodu 0 (gerçek: $kod)"
Dogrula (Test-Path (Join-Path $Neocp "anilar.json")) "TEMİZ kurulumda anılar DURUYOR"
Dogrula (Test-Path (Join-Path $Neocp "tasks.json")) "TEMİZ kurulumda görevler DURUYOR"
Dogrula (-not (Test-Path $sahteKod)) "eski sürümden kalan kod dosyası silindi"
Dogrula (Test-Path (Join-Path $Hedef "pyproject.toml")) "yeni kod yerine kondu"

Write-Host "`n== Senaryo 8: VERİLERİ DE SIFIRLA — önce yedek, sonra silme" -ForegroundColor Cyan
# En tehlikeli yol. İki şey birden doğru olmalı: veri GERÇEKTEN gitmeli
# (yoksa "sıfırla" yalan olur) ve gitmeden ÖNCE yedeklenmiş olmalı.
# Yedek adedi 5'te tavanlı (Senaryo 3): "sayı arttı mı" yanlış ölçüt olurdu.
# Doğru ölçüt, EN YENİ yedeğin değişmiş olması.
$oncekiEnYeni = (Get-ChildItem $Yedek -Filter "neo-backup-*.zip" -ErrorAction SilentlyContinue |
                 Sort-Object LastWriteTime | Select-Object -Last 1).Name
Start-Sleep -Seconds 1   # yedek adı saniye damgalı: aynı saniyeye düşmesin
$kod = Kur $Kur022 @("/TEMIZLE=veri")
Dogrula ($kod -eq 0) "veri sıfırlama çıkış kodu 0 (gerçek: $kod)"
$sonYedek = @(Get-ChildItem $Yedek -Filter "neo-backup-*.zip" -ErrorAction SilentlyContinue)
$sonEnYeni = ($sonYedek | Sort-Object LastWriteTime | Select-Object -Last 1).Name
Dogrula ($sonEnYeni -ne $oncekiEnYeni) "silmeden ÖNCE yeni yedek alındı ($sonEnYeni)"
Dogrula (-not (Test-Path (Join-Path $Neocp "anilar.json"))) "anılar gerçekten silindi"
Dogrula (-not (Test-Path (Join-Path $Neocp "tasks.json"))) "görevler gerçekten silindi"
Dogrula (Test-Path (Join-Path $Hedef "pyproject.toml")) "silme sonrası kurulum yine sağlam"
# Yedeğin İÇİNDE silinen veri olmalı — boş bir zip, yedek değildir.
$enYeni = $sonYedek | Sort-Object LastWriteTime | Select-Object -Last 1
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($enYeni.FullName)
$icerik = @($zip.Entries | ForEach-Object { $_.FullName })
$zip.Dispose()
Dogrula (($icerik -join [char]10) -match 'anilar') "yedeğin içinde silinen anılar var"

Write-Host "`n== Senaryo 6: kaldırma sonrası .neocp yerinde" -ForegroundColor Cyan
# Kendi ön koşulunu kuruyor: Senaryo 8 veriyi bilerek sildi, buradaki soru
# ise "kaldırma veriyi siler mi" — o yüzden taze veri konuyor.
New-Item -ItemType Directory -Force $Neocp | Out-Null
'{"n":"kaldirma-senaryosu"}' | Set-Content (Join-Path $Neocp "anilar.json") -Encoding utf8
$unins = Join-Path $Hedef "unins000.exe"
if (Test-Path $unins) {
    Start-Process -FilePath $unins -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES") -Wait
    Start-Sleep -Seconds 2
    Dogrula (Test-Path (Join-Path $Neocp "anilar.json")) "kaldırma .neocp'yi bıraktı"
    Dogrula (-not (Test-Path (Join-Path $Hedef "pyproject.toml"))) "kod dosyaları (pyproject dahil) kaldırıldı"
} else {
    Dogrula $false "kaldırıcı bulunamadı: $unins"
}

# -- temizlik -----------------------------------------------------------
if (Test-Path $KayitYolu) { Remove-Item $KayitYolu -Recurse -Force }
$kisayol = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\neo-test.lnk"
if (Test-Path $kisayol) { Remove-Item $kisayol -Force }

# -- özet ---------------------------------------------------------------
Write-Host ""
if ($Basarisiz.Count -eq 0) {
    Write-Host "TÜM KURULUM SENARYOLARI GEÇTİ" -ForegroundColor Green
    Write-Host "(sandbox: $Kok — incelemek istersen duruyor)"
    exit 0
}
Write-Host "BAŞARISIZ: $($Basarisiz.Count)" -ForegroundColor Red
$Basarisiz | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
exit 1
