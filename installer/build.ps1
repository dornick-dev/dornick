# Kurulum paketini hazırlar ve (iscc varsa) sihirbazı derler.
#
# Ne yapar:
#   1. python.org'un gömülü (embeddable) Python 3.11'ini indirir ve açar —
#      hedef makinede Python kurulu olması gerekmez.
#   2. get-pip ile pip kurar, uygulamanın bağımlılıklarını O python'a yükler.
#   3. src/neocp kaynağını ve (eğitim bileşeni için) neocp-base-model
#      düzeneğini çıktı klasörüne kopyalar. .neocp'deki anahtar/veri ASLA
#      pakete girmez — yalnız kod, varlıklar ve eğitim dosyaları.
#   4. Torch'un CPU tekerleğini eğitim bileşeninin kendi site klasörüne
#      (egitim\sitepaket) kurar: bileşen seçilmezse klasör hedefe hiç
#      gitmez ve python311._pth'teki yol sessizce boş kalır — kurulum
#      sırasında pip koşturmaya gerek kalmıyor.
#   5. Inno Setup (iscc) bulunursa neo.iss'i derler.
#
# Kullanım:
#   powershell -ExecutionPolicy Bypass -File installeruild.ps1
#   ... -AtlaTorch    : eğitim bileşenini (torch + düzenek) paketleme
#   ... -AtlaDerleme  : iscc'yi çağırma, yalnız paketi hazırla

param(
    [switch]$AtlaTorch,
    [switch]$AtlaDerleme
)

$ErrorActionPreference = "Stop"

# -- yollar -------------------------------------------------------------------
$Kok      = Split-Path -Parent $PSScriptRoot          # depo kökü
$Cikti    = Join-Path $PSScriptRoot "dist"
$Indirme  = Join-Path $Cikti "indirme"                # arşivler burada önbelleklenir
$Paket    = Join-Path $Cikti "paket"                  # kurulacak ağacın birebir kopyası
$TabanDepo = Join-Path $Kok "training"                # eğitim düzeneği depo içinde

$PySurum  = "3.11.9"
$PyZip    = "python-$PySurum-embed-amd64.zip"
$PyUrl    = "https://www.python.org/ftp/python/$PySurum/$PyZip"

# Uygulamanın gerçekten kullandığı üçüncü partiler (src/neocp import taraması):
#   zorunlu : anthropic, rich, numpy (taban.npz çıkarımı), pywebview (pencere)
#   pratik  : pillow (tepsi/simge/ekran görüntüsü), pystray (tepsi),
#             edge-tts (ses), openai (LM Studio/Ollama), mcp (bağlayıcılar),
#             pypdf + reportlab (paketle gelen yetenekler)
#   dışarıda: faster-whisper/sounddevice (dinleme) ve opencv (kamera) —
#             ağır; yoklukları özelliği zaten kapatıyor.
$Bagimliliklar = @(
    "anthropic>=0.92", "rich>=13.7", "pywebview>=5.0", "numpy",
    "pillow>=10.0", "pystray>=0.19", "edge-tts>=7.0", "openai>=1.60",
    "mcp>=1.2", "pypdf", "reportlab"
)

function Adim([string]$mesaj) { Write-Host "`n== $mesaj" -ForegroundColor Cyan }

function Kopyala([string]$kaynak, [string]$hedef, [string[]]$haric) {
    # robocopy: 8 ve üstü gerçek hata; 0-7 "kopyalandı/aynıydı" demek.
    $args = @($kaynak, $hedef, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($haric) { $args += "/XD"; $args += $haric }
    robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy başarısız ($LASTEXITCODE): $kaynak" }
}

# -- 0) temiz sayfa -----------------------------------------------------------
Adim "Çıktı klasörü: $Paket"
if (Test-Path $Paket) { Remove-Item -Recurse -Force $Paket }
New-Item -ItemType Directory -Force $Paket | Out-Null
New-Item -ItemType Directory -Force $Indirme | Out-Null

# -- 1) gömülü Python ---------------------------------------------------------
Adim "Gömülü Python $PySurum"
$zipYolu = Join-Path $Indirme $PyZip
if (-not (Test-Path $zipYolu)) {
    Invoke-WebRequest -Uri $PyUrl -OutFile $zipYolu
}
$PyDizin = Join-Path $Paket "python"
Expand-Archive -Path $zipYolu -DestinationPath $PyDizin -Force

# ._pth: gömülü Python'un arama yolu bu dosyadan ibaret. Kaynak, pip
# klasörü ve (varsa) eğitim bileşeninin torch klasörü ekleniyor — var
# olmayan yol sessizce atlanır, o yüzden eğitimsiz kurulumda da doğru.
$pth = Join-Path $PyDizin "python311._pth"
@(
    "python311.zip",
    ".",
    "Lib\site-packages",
    "..\src",
    "..\training\site",
    "import site"
) | Set-Content -Path $pth -Encoding Ascii

# -- 2) pip + bağımlılıklar ---------------------------------------------------
Adim "pip kuruluyor"
$getPip = Join-Path $Indirme "get-pip.py"
if (-not (Test-Path $getPip)) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
}
$PyExe = Join-Path $PyDizin "python.exe"
& $PyExe $getPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip başarısız" }

Adim "Bağımlılıklar kuruluyor"
& $PyExe -m pip install --no-warn-script-location @Bagimliliklar
if ($LASTEXITCODE -ne 0) { throw "pip install başarısız" }

# -- 3) uygulama kaynağı ------------------------------------------------------
Adim "Kaynak kopyalanıyor (src/neocp + varlıklar)"
Kopyala (Join-Path $Kok "src\neocp") (Join-Path $Paket "src\neocp") @("__pycache__")

# -- 4) eğitim bileşeni (isteğe bağlı) ---------------------------------------
if (-not $AtlaTorch) {
    Adim "Eğitim düzeneği kopyalanıyor ($TabanDepo)"
    if (-not (Test-Path $TabanDepo)) { throw "Eğitim düzeneği yok: $TabanDepo" }
    $Egitim = Join-Path $Paket "training"

    Kopyala (Join-Path $TabanDepo "scripts") (Join-Path $Egitim "scripts") @("__pycache__")
    Kopyala (Join-Path $TabanDepo "model")   (Join-Path $Egitim "model")   @("__pycache__")
    # teacher.py yedek öğretmen içindir; .env BİLEREK paket dışı —
    # anahtarsız yedek sessizce devre dışı kalır, seçili model yeter.
    Copy-Item (Join-Path $TabanDepo "teacher.py") $Egitim
    New-Item -ItemType Directory -Force (Join-Path $Egitim "checkpoints") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $Egitim "data")        | Out-Null
    Copy-Item (Join-Path $TabanDepo "checkpoints\base.pt")  (Join-Path $Egitim "checkpoints")
    Copy-Item (Join-Path $TabanDepo "data\corpus.jsonl")    (Join-Path $Egitim "data")
    Copy-Item (Join-Path $TabanDepo "data\corpus_en.jsonl") (Join-Path $Egitim "data")

    # Sınav kapısının TR ölçütü: ürünün kendi kıyaslama düzeneği.
    $Eval = Join-Path $Paket "eval\context_memory"
    New-Item -ItemType Directory -Force $Eval | Out-Null
    Copy-Item (Join-Path $Kok "eval\context_memory\scale_bench.py")     $Eval
    Copy-Item (Join-Path $Kok "eval\context_memory\scale_dataset.json") $Eval

    Adim "Torch (CPU) eğitim bileşenine kuruluyor"
    & $PyExe -m pip install --no-warn-script-location `
        --target (Join-Path $Egitim "site") `
        --index-url "https://download.pytorch.org/whl/cpu" torch
    if ($LASTEXITCODE -ne 0) { throw "torch kurulamadı" }
}

# -- 5) başlatıcı -------------------------------------------------------------
Adim "Başlatıcı yazılıyor"
# Kısayollar doğrudan pythonw'yu hedefliyor (konsolsuz); neo.cmd klasörden
# çift tıkla açmak isteyen için aynı komutun görünür hali.
@'
@echo off
rem neo — masaustu penceresini acar (konsol penceresi acilmaz).
set "KOK=%~dp0"
start "" "%KOK%python\pythonw.exe" -m neocp --app -C "%KOK%."
'@ | Set-Content -Path (Join-Path $Paket "neo.cmd") -Encoding Ascii

# -- 6) derleme ---------------------------------------------------------------
if ($AtlaDerleme) {
    Adim "Derleme atlandı (-AtlaDerleme). Paket hazır: $Paket"
    exit 0
}

Adim "Inno Setup aranıyor"
$iscc = $null
$aday = Get-Command iscc -ErrorAction SilentlyContinue
if ($aday) { $iscc = $aday.Source }
if (-not $iscc) {
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if (-not $iscc) {
    Write-Host "iscc yok — winget ile kurulum deneniyor" -ForegroundColor Yellow
    winget install -e --id JRSoftware.InnoSetup --scope user --accept-source-agreements --accept-package-agreements
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if (-not $iscc) {
    Write-Host "`nISCC bulunamadı. Paket hazır: $Paket" -ForegroundColor Yellow
    Write-Host "Inno Setup kurunca: iscc installer\neo.iss"
    exit 2
}

Adim "Sihirbaz derleniyor ($iscc)"
& $iscc (Join-Path $PSScriptRoot "neo.iss")
if ($LASTEXITCODE -ne 0) { throw "iscc başarısız" }

$exe = Get-ChildItem (Join-Path $Cikti "*.exe") | Sort-Object LastWriteTime | Select-Object -Last 1
Adim ("Bitti: {0} ({1:N0} MB)" -f $exe.FullName, ($exe.Length / 1MB))
