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
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
#   ... -AtlaTorch    : eğitim bileşenini (torch + düzenek) paketleme
#   ... -AtlaDinleme  : dinleme bileşenini (faster-whisper + sounddevice) paketleme
#   ... -AtlaKamera   : kamera bileşenini (opencv + onnxruntime-gpu) paketleme
#   ... -AtlaDerleme  : iscc'yi çağırma, yalnız paketi hazırla

param(
    [switch]$AtlaTorch,
    [switch]$AtlaDinleme,
    [switch]$AtlaKamera,
    [switch]$AtlaDerleme,
    # Paket sürümü. Boş bırakılırsa pyproject.toml'daki version okunur —
    # sürüm tek yerden yönetilir, iss'e /DSurum ile geçer.
    [string]$Surum = "",
    # Eğitim düzeneğinin kaynağı. Varsayılan geliştirme makinesinin yolu;
    # depoyu klonlayan biri kendi yolunu verebilir. Yol yoksa betik
    # PATLAMIYOR, eğitim bileşenini atlayıp söylüyor — "kurulum paketi
    # üretemedim" demek, kullanıcının istemediği bir bileşen yüzünden
    # orantısız.
    [string]$TabanDepo = "D:\Projects\ai\neocp-base-model"
)

$ErrorActionPreference = "Stop"

# -- yollar -------------------------------------------------------------------
$Kok      = Split-Path -Parent $PSScriptRoot          # neocp deposu
$Cikti    = Join-Path $PSScriptRoot "dist"
$Indirme  = Join-Path $Cikti "indirme"                # arşivler burada önbelleklenir
$Paket    = Join-Path $Cikti "paket"                  # kurulacak ağacın birebir kopyası

if (-not $Surum) {
    $eslesme = Select-String -Path (Join-Path $Kok "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"'
    if (-not $eslesme) { throw "pyproject.toml içinde version bulunamadı" }
    $Surum = $eslesme.Matches[0].Groups[1].Value
}

$PySurum  = "3.11.9"
$PyZip    = "python-$PySurum-embed-amd64.zip"
$PyUrl    = "https://www.python.org/ftp/python/$PySurum/$PyZip"

# Uygulamanın gerçekten kullandığı üçüncü partiler (src/neocp import taraması):
#   zorunlu : anthropic, rich, numpy (taban.npz çıkarımı), pywebview (pencere)
#   pratik  : pillow (tepsi/simge/ekran görüntüsü), pystray (tepsi),
#             edge-tts (ses), openai (LM Studio/Ollama), mcp (bağlayıcılar),
#             pypdf + reportlab (paketle gelen yetenekler)
#   dışarıda: faster-whisper/sounddevice (dinleme) ve opencv+onnxruntime-gpu
#             (kamera) — ağır; yoklukları özelliği zaten kapatıyor.
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
    "..\egitim\sitepaket",
    "..\listen\site",
    "..\watch\site",
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
# Sürümün tek gerçek kaynağı pyproject.toml; ortam.surum() çalışma zamanında
# paket kökünden okur — kurulu ağaç da depo gibi kökünde taşımalı.
Copy-Item (Join-Path $Kok "pyproject.toml") $Paket

# -- 4) eğitim bileşeni (isteğe bağlı) ---------------------------------------
if (-not $AtlaTorch -and -not (Test-Path $TabanDepo)) {
    # Depoyu klonlayan biri bu yolu taşımıyor. Patlamak yerine bileşeni
    # atlıyoruz: kullanıcı "kurulum paketi üretemedim" değil, "eğitim
    # bileşeni pakete girmedi, sebebi şu" duymalı.
    Write-Host ("`nEğitim deposu bulunamadı: {0}" -f $TabanDepo) -ForegroundColor Yellow
    Write-Host "Eğitim bileşeni (Beni tanı) pakete girmeyecek."
    Write-Host "Kendi yolunu vermek için: -TabanDepo <yol>   ·   bilerek atlamak için: -AtlaTorch"
    $AtlaTorch = $true
}

if (-not $AtlaTorch) {
    Adim "Eğitim düzeneği kopyalanıyor ($TabanDepo)"
    $Egitim = Join-Path $Paket "egitim"

    Kopyala (Join-Path $TabanDepo "betikler") (Join-Path $Egitim "betikler") @("__pycache__")
    Kopyala (Join-Path $TabanDepo "model")    (Join-Path $Egitim "model")    @("__pycache__")
    # ayarlar.py yedek öğretmen içindir; anahtar.env BİLEREK paket dışı —
    # anahtarsız yedek sessizce devre dışı kalır, seçili model yeter.
    Copy-Item (Join-Path $TabanDepo "ayarlar.py") $Egitim
    New-Item -ItemType Directory -Force (Join-Path $Egitim "out")  | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $Egitim "veri") | Out-Null
    Copy-Item (Join-Path $TabanDepo "out\eniyi.pt") (Join-Path $Egitim "out")
    Copy-Item (Join-Path $TabanDepo "veri\korpus.jsonl")    (Join-Path $Egitim "veri")
    Copy-Item (Join-Path $TabanDepo "veri\korpus_en.jsonl") (Join-Path $Egitim "veri")

    # Sınav kapısının TR ölçütü: ürünün kendi kıyaslama düzeneği.
    $Eval = Join-Path $Paket "eval\context_memory"
    New-Item -ItemType Directory -Force $Eval | Out-Null
    Copy-Item (Join-Path $Kok "eval\context_memory\scale_bench.py")     $Eval
    Copy-Item (Join-Path $Kok "eval\context_memory\scale_dataset.json") $Eval

    Adim "Torch (CPU) eğitim bileşenine kuruluyor"
    & $PyExe -m pip install --no-warn-script-location `
        --target (Join-Path $Egitim "sitepaket") `
        --index-url "https://download.pytorch.org/whl/cpu" torch
    if ($LASTEXITCODE -ne 0) { throw "torch kurulamadı" }
}

# -- 4b) dinleme bileşeni (isteğe bağlı) --------------------------------------
# faster-whisper (ctranslate2, onnxruntime dahil) + sounddevice kendi site
# klasörüne gidiyor: bileşen seçilmezse klasör hedefe hiç kopyalanmaz,
# import düşer ve özellik kapalı görünür — torch kalıbının aynısı.
if (-not $AtlaDinleme) {
    Adim "Dinleme bileşeni (faster-whisper + sounddevice)"
    & $PyExe -m pip install --no-warn-script-location `
        --target (Join-Path $Paket "listen\site") faster-whisper sounddevice
    if ($LASTEXITCODE -ne 0) { throw "dinleme paketleri kurulamadı" }
}

# -- 4c) kamera bileşeni (isteğe bağlı) ---------------------------------------
if (-not $AtlaKamera) {
    Adim "Kamera bileşeni (opencv-python-headless + onnxruntime-gpu)"
    & $PyExe -m pip install --no-warn-script-location `
        --target (Join-Path $Paket "watch\site") opencv-python-headless onnxruntime-gpu
    if ($LASTEXITCODE -ne 0) { throw "kamera paketi kurulamadı" }

    # YOLO ONNX ağırlığı da pakete: kurulu makinede ilk bakış indirme
    # beklemesin, çevrimdışı da çalışsın (kullanıcı ilkesi: "sonradan
    # kendi kurması gerekmesin"). İndirme önbelleklenir; sight._model_path
    # önce bu kopyaya bakar.
    Adim "YOLO modeli (yolov8n.onnx) paketleniyor"
    # v8.3.0 adresi oldu (404, 31.08); once v8.4.0. Indirilemezse paket
    # DUSURULMEZ: model ilk kullanimda calisma zamaninda da inebiliyor —
    # cevrimdisi derleme "kurulum paketi uretemedim" ile bitmemeli.
    $OnnxCache = Join-Path $Indirme "yolov8n.onnx"
    if (-not (Test-Path $OnnxCache)) {
        foreach ($u in @(
            "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.onnx",
            "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx")) {
            try { Invoke-WebRequest -Uri $u -OutFile $OnnxCache -ErrorAction Stop; break }
            catch { Write-Host "  indirilemedi: $u" -ForegroundColor Yellow }
        }
    }
    if (Test-Path $OnnxCache) {
        $ModelDizin = Join-Path $Paket "watch\models"
        New-Item -ItemType Directory -Force $ModelDizin | Out-Null
        Copy-Item $OnnxCache $ModelDizin
    } else {
        Write-Host "  ONNX paketlenemedi - ilk kullanimda indirilecek" -ForegroundColor Yellow
    }
}

# -- 5) başlatıcı -------------------------------------------------------------
Adim "Başlatıcı yazılıyor"
# Görev Yöneticisi PE ikonuna bakar: pythonw kopyası neo.exe + ico damgası.
# neo.cmd klasörden çift tıkla açmak isteyen için aynı komutun görünür hali.
$PyW = Join-Path $PyDizin "pythonw.exe"
$NeoExe = Join-Path $PyDizin "neo.exe"
Copy-Item $PyW $NeoExe -Force
& $PyExe -c "from neocp.winicon import ensure_host; ensure_host()"
if ($LASTEXITCODE -ne 0) {
    Write-Host "simge damgası atlandı — kurulum/ilk açılış dener" -ForegroundColor Yellow
}
@'
@echo off
rem neo — masaustu penceresini acar (konsol penceresi acilmaz).
set "KOK=%~dp0"
start "" "%KOK%python\neo.exe" -m neocp --app -C "%KOK%."
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

Adim "Sihirbaz derleniyor ($iscc, sürüm $Surum)"
& $iscc "/DSurum=$Surum" (Join-Path $PSScriptRoot "neo.iss")
if ($LASTEXITCODE -ne 0) { throw "iscc başarısız" }

$exe = Get-ChildItem (Join-Path $Cikti "*.exe") | Sort-Object LastWriteTime | Select-Object -Last 1
Adim ("Bitti: {0} ({1:N0} MB)" -f $exe.FullName, ($exe.Length / 1MB))
