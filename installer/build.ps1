# Prepares the installation package and (if iscc is present) compiles the wizard.
#
# What it does:
#   1. Downloads and extracts python.org's embeddable Python 3.11 —
#      the target machine does not need Python installed.
#   2. Installs pip via get-pip, installs the app's dependencies into THAT python.
#   3. Copies the src/dornick source and (for the training component) the
#      dornick-base-model rig into the output folder. Keys/data from .dornick
#      NEVER enter the package — only code, assets and training files.
#   4. Installs Torch's CPU wheel into the training component's own site
#      folder (egitim\sitepaket): if the component is not selected the folder
#      never reaches the target and the path in python311._pth stays silently
#      empty — no need to run pip during installation.
#   5. If Inno Setup (iscc) is found, compiles dornick.iss.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
#   ... -SkipTorch    : do not package the training component (torch + rig)
#   ... -SkipListen   : do not package the listening component (faster-whisper + sounddevice)
#   ... -SkipCamera   : do not package the camera component (opencv + onnxruntime-gpu)
#   ... -SkipCompile  : do not invoke iscc, only prepare the package

param(
    [switch]$SkipTorch,
    [switch]$SkipListen,
    [switch]$SkipCamera,
    [switch]$SkipCompile,
    # Package version. If left empty, version is read from pyproject.toml —
    # the version is managed in one place and passed to the iss via /DVersion.
    [string]$Version = "",
    # Source of the training rig. Default is the development machine's path;
    # someone cloning the repo can pass their own path. If the path is missing
    # the script does NOT blow up: it skips the training component and says so —
    # "could not produce the installer" would be disproportionate for a
    # component the user did not ask for.
    # EXTERNAL repo — this is its real on-disk name (not renamed in the rebrand).
    [string]$BaseRepo = "D:\Projects\ai\neocp-base-model"
)

$ErrorActionPreference = "Stop"

# -- paths --------------------------------------------------------------------
$RepoRoot    = Split-Path -Parent $PSScriptRoot       # the dornick repo
$OutDir      = Join-Path $PSScriptRoot "dist"
$DownloadDir = Join-Path $OutDir "indirme"            # archives are cached here
$PackageDir  = Join-Path $OutDir "paket"              # exact copy of the tree to be installed

if (-not $Version) {
    $found = Select-String -Path (Join-Path $RepoRoot "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"'
    if (-not $found) { throw "version not found in pyproject.toml" }
    $Version = $found.Matches[0].Groups[1].Value
}

$PyVersion = "3.11.9"
$PyZip     = "python-$PyVersion-embed-amd64.zip"
$PyUrl     = "https://www.python.org/ftp/python/$PyVersion/$PyZip"

# Third parties the app actually uses (src/dornick import scan):
#   required : anthropic, rich, numpy (taban.npz inference), pywebview (window)
#   practical: pillow (tray/icon/screenshot), pystray (tray),
#              edge-tts (voice), openai (LM Studio/Ollama), mcp (connectors),
#              pypdf + reportlab (capabilities shipped with the package)
#   excluded : faster-whisper/sounddevice (listening) and opencv+onnxruntime-gpu
#              (camera) — heavy; their absence already disables the feature.
$Dependencies = @(
    "anthropic>=0.92", "rich>=13.7", "pywebview>=5.0", "numpy",
    "pillow>=10.0", "pystray>=0.19", "edge-tts>=7.0", "openai>=1.60",
    "mcp>=1.2", "pypdf", "reportlab"
)

function Step([string]$message) { Write-Host "`n== $message" -ForegroundColor Cyan }

function Copy-Tree([string]$source, [string]$destination, [string[]]$exclude) {
    # robocopy: 8 and above is a real error; 0-7 means "copied/identical".
    $args = @($source, $destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($exclude) { $args += "/XD"; $args += $exclude }
    robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE): $source" }
}

# -- 0) clean slate -----------------------------------------------------------
Step "Output folder: $PackageDir"
if (Test-Path $PackageDir) { Remove-Item -Recurse -Force $PackageDir }
New-Item -ItemType Directory -Force $PackageDir | Out-Null
New-Item -ItemType Directory -Force $DownloadDir | Out-Null

# -- 1) embedded Python -------------------------------------------------------
Step "Embedded Python $PyVersion"
$zipPath = Join-Path $DownloadDir $PyZip
if (-not (Test-Path $zipPath)) {
    Invoke-WebRequest -Uri $PyUrl -OutFile $zipPath
}
$PyDir = Join-Path $PackageDir "python"
Expand-Archive -Path $zipPath -DestinationPath $PyDir -Force

# ._pth: the embedded Python's search path is this file and nothing else.
# The source, the pip folder and (if present) the training component's torch
# folder are added — a non-existent path is silently skipped, so this is
# also correct for an install without training.
$pth = Join-Path $PyDir "python311._pth"
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

# -- 2) pip + dependencies ----------------------------------------------------
Step "Installing pip"
$getPip = Join-Path $DownloadDir "get-pip.py"
if (-not (Test-Path $getPip)) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
}
$PyExe = Join-Path $PyDir "python.exe"
& $PyExe $getPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }

Step "Installing dependencies"
& $PyExe -m pip install --no-warn-script-location @Dependencies
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# -- 3) application source ----------------------------------------------------
Step "Copying source (src/dornick + assets)"
Copy-Tree (Join-Path $RepoRoot "src\dornick") (Join-Path $PackageDir "src\dornick") @("__pycache__")
# pyproject.toml is the single source of truth for the version;
# environment.surum() reads it from the package root at runtime — the
# installed tree must carry it at its root just like the repo does.
Copy-Item (Join-Path $RepoRoot "pyproject.toml") $PackageDir

# -- 4) training component (optional) -----------------------------------------
if (-not $SkipTorch -and -not (Test-Path $BaseRepo)) {
    # Someone cloning the repo does not carry this path. Instead of blowing up
    # we skip the component: the user should hear "the training component was
    # not packaged, here is why" — not "could not produce the installer".
    Write-Host ("`nTraining repo not found: {0}" -f $BaseRepo) -ForegroundColor Yellow
    Write-Host "The training component (Know-me) will not be packaged."
    Write-Host "To pass your own path: -BaseRepo <path>   ·   to skip deliberately: -SkipTorch"
    $SkipTorch = $true
}

if (-not $SkipTorch) {
    Step "Copying training rig ($BaseRepo)"
    $TrainingDir = Join-Path $PackageDir "egitim"

    Copy-Tree (Join-Path $BaseRepo "betikler") (Join-Path $TrainingDir "betikler") @("__pycache__")
    Copy-Tree (Join-Path $BaseRepo "model")    (Join-Path $TrainingDir "model")    @("__pycache__")
    # ayarlar.py is for the fallback teacher; anahtar.env is DELIBERATELY kept
    # out of the package — without a key the fallback silently stays disabled,
    # the selected model is enough.
    Copy-Item (Join-Path $BaseRepo "ayarlar.py") $TrainingDir
    New-Item -ItemType Directory -Force (Join-Path $TrainingDir "out")  | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $TrainingDir "veri") | Out-Null
    Copy-Item (Join-Path $BaseRepo "out\eniyi.pt") (Join-Path $TrainingDir "out")
    Copy-Item (Join-Path $BaseRepo "veri\korpus.jsonl")    (Join-Path $TrainingDir "veri")
    Copy-Item (Join-Path $BaseRepo "veri\korpus_en.jsonl") (Join-Path $TrainingDir "veri")

    # The exam gate's TR criterion: the product's own benchmark rig.
    $Eval = Join-Path $PackageDir "eval\context_memory"
    New-Item -ItemType Directory -Force $Eval | Out-Null
    Copy-Item (Join-Path $RepoRoot "eval\context_memory\scale_bench.py")     $Eval
    Copy-Item (Join-Path $RepoRoot "eval\context_memory\scale_dataset.json") $Eval

    Step "Installing Torch (CPU) into the training component"
    & $PyExe -m pip install --no-warn-script-location `
        --target (Join-Path $TrainingDir "sitepaket") `
        --index-url "https://download.pytorch.org/whl/cpu" torch
    if ($LASTEXITCODE -ne 0) { throw "torch install failed" }
}

# -- 4b) listening component (optional) ---------------------------------------
# faster-whisper (including ctranslate2, onnxruntime) + sounddevice go into
# their own site folder: if the component is not selected the folder is never
# copied to the target, the import fails and the feature shows as disabled —
# the same pattern as torch.
if (-not $SkipListen) {
    Step "Listening component (faster-whisper + sounddevice)"
    & $PyExe -m pip install --no-warn-script-location `
        --target (Join-Path $PackageDir "listen\site") faster-whisper sounddevice
    if ($LASTEXITCODE -ne 0) { throw "listening packages failed to install" }
}

# -- 4c) camera component (optional) ------------------------------------------
if (-not $SkipCamera) {
    Step "Camera component (opencv-python-headless + onnxruntime-gpu)"
    & $PyExe -m pip install --no-warn-script-location `
        --target (Join-Path $PackageDir "watch\site") opencv-python-headless onnxruntime-gpu
    if ($LASTEXITCODE -ne 0) { throw "camera package failed to install" }

    # The YOLO ONNX weight goes into the package too: the first look on the
    # installed machine should not wait for a download, and it should work
    # offline (user principle: "they should not have to install things
    # themselves later"). The download is cached; sight._model_path checks
    # this copy first.
    Step "Packaging YOLO model (yolov8n.onnx)"
    # The v8.3.0 URL went away (404, 31.08); try v8.4.0 first. If it cannot be
    # downloaded the package is NOT dropped: the model can also come down at
    # runtime on first use — an offline build must not end with "could not
    # produce the installer".
    $OnnxCache = Join-Path $DownloadDir "yolov8n.onnx"
    if (-not (Test-Path $OnnxCache)) {
        foreach ($u in @(
            "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.onnx",
            "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx")) {
            try { Invoke-WebRequest -Uri $u -OutFile $OnnxCache -ErrorAction Stop; break }
            catch { Write-Host "  download failed: $u" -ForegroundColor Yellow }
        }
    }
    if (Test-Path $OnnxCache) {
        $ModelDir = Join-Path $PackageDir "watch\models"
        New-Item -ItemType Directory -Force $ModelDir | Out-Null
        Copy-Item $OnnxCache $ModelDir
    } else {
        Write-Host "  ONNX could not be packaged - it will be downloaded on first use" -ForegroundColor Yellow
    }
}

# -- 5) launcher --------------------------------------------------------------
Step "Writing launcher"
# Task Manager looks at the PE icon: dornick.exe is a pythonw copy + ico stamp.
# dornick.cmd is the visible form of the same command for whoever wants to
# double-click it from the folder.
$PyW = Join-Path $PyDir "pythonw.exe"
$DornickExe = Join-Path $PyDir "dornick.exe"
Copy-Item $PyW $DornickExe -Force
& $PyExe -c "from dornick.winicon import ensure_host; ensure_host()"
if ($LASTEXITCODE -ne 0) {
    Write-Host "icon stamp skipped — install/first launch will retry" -ForegroundColor Yellow
}
@'
@echo off
rem dornick — masaustu penceresini acar (konsol penceresi acilmaz).
set "KOK=%~dp0"
start "" "%KOK%python\dornick.exe" -m dornick --app -C "%KOK%."
'@ | Set-Content -Path (Join-Path $PackageDir "dornick.cmd") -Encoding Ascii

# -- 6) compile ---------------------------------------------------------------
if ($SkipCompile) {
    Step "Compile skipped (-SkipCompile). Package ready: $PackageDir"
    exit 0
}

Step "Looking for Inno Setup"
$iscc = $null
$candidate = Get-Command iscc -ErrorAction SilentlyContinue
if ($candidate) { $iscc = $candidate.Source }
if (-not $iscc) {
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if (-not $iscc) {
    Write-Host "iscc missing — trying to install via winget" -ForegroundColor Yellow
    winget install -e --id JRSoftware.InnoSetup --scope user --accept-source-agreements --accept-package-agreements
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if (-not $iscc) {
    Write-Host "`nISCC not found. Package ready: $PackageDir" -ForegroundColor Yellow
    Write-Host "Once Inno Setup is installed: iscc installer\dornick.iss"
    exit 2
}

Step "Compiling wizard ($iscc, version $Version)"
& $iscc "/DVersion=$Version" (Join-Path $PSScriptRoot "dornick.iss")
if ($LASTEXITCODE -ne 0) { throw "iscc failed" }

$exe = Get-ChildItem (Join-Path $OutDir "*.exe") | Sort-Object LastWriteTime | Select-Object -Last 1
Step ("Done: {0} ({1:N0} MB)" -f $exe.FullName, ($exe.Length / 1MB))
