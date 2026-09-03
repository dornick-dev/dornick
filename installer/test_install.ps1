# Proves the install wizard's safety nets in a sandbox.
#
# Does NOT touch the real installation: the test build uses a separate AppId
# (AppIdGuid) and a separate name (dornick-test) — registry key, shortcuts and
# file tree are fully isolated. The package content is a stub too: what is
# being tested is the [Code] logic of dornick.iss — not file copying itself.
#
# Scenarios:
#   1. Clean install (0.2.1) — with no .dornick, the backup zip is NOT created.
#   2. Plant a fake .dornick → update to 0.2.2 on top — the backup zip IS
#      created, it contains .dornick\anilar.json, the installed data is intact,
#      DisplayVersion in the registry becomes 0.2.2.
#   3. Backup rotation — with 6 old zips in the folder, one more update:
#      only the newest 5 remain, the oldest are deleted.
#   4. Running-copy detection — a real "-m dornick" process is started
#      (recall-mcp: no model, no window, waits on stdin); the installer is
#      invoked with /SADECE_TARA=1 /SUREC_RAPOR=<file> and the report is
#      proven to list that PID. (The wizard page cannot be driven by
#      automation, so the [Code] logic is tested via the parameter.)
#   5. Gentle/forced kill chain — proves that a gentle taskkill is not enough
#      for a console process and /F kills it (the rationale for the
#      Attempt>0 escalation in the installer).
#   6. Uninstall — .dornick is still in place AFTER uninstalling.
#
# Usage: powershell -ExecutionPolicy Bypass -File installer\test_install.ps1

param(
    # Sandbox root. Does not touch Documents or the real installation.
    [string]$Root = (Join-Path $env:TEMP "dornick-kurulum-test")
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$TestGuid = "5A5A5A5A-1111-4222-8333-444455556666"
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{$TestGuid}_is1"
# A real Python 3.11+ (not the WindowsApps stub): from the py launcher.
$Py = ""
try { $Py = (& py -3.11 -c "import sys; print(sys.executable)").Trim() } catch { }
if (-not $Py) {
    $candidate = Get-Command python -ErrorAction SilentlyContinue
    if ($candidate) { $Py = $candidate.Source }
}
if (-not $Py) { throw "Python not found — required for the running-copy scenario" }

$Failed = @()
function Check([bool]$condition, [string]$message) {
    if ($condition) { Write-Host "  OK   $message" -ForegroundColor Green }
    else { Write-Host "  FAIL $message" -ForegroundColor Red; $script:Failed += $message }
}

# -- iscc ---------------------------------------------------------------
$iscc = $null
foreach ($p in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
                 "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                 "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
    if (Test-Path $p) { $iscc = $p; break }
}
if (-not $iscc) { throw "ISCC not found — Inno Setup 6 required" }

# -- 0) clean sandbox ---------------------------------------------------
if (Test-Path $Root) { Remove-Item -Recurse -Force $Root }
foreach ($sub in @("paket", "cikti", "kurulum", "yedek", "calisma")) {
    New-Item -ItemType Directory -Force (Join-Path $Root $sub) | Out-Null
}
$Package = Join-Path $Root "paket"
$Out     = Join-Path $Root "cikti"
$Target  = Join-Path $Root "kurulum"
$Backup  = Join-Path $Root "yedek"

# -- 1) stub package ----------------------------------------------------
# Every source directory in the [Files] section must exist; content is irrelevant.
foreach ($d in @("python", "src\dornick\assets", "egitim", "listen", "watch", "eval")) {
    New-Item -ItemType Directory -Force (Join-Path $Package $d) | Out-Null
}
"saplama" | Set-Content (Join-Path $Package "python\bos.txt")
"saplama" | Set-Content (Join-Path $Package "egitim\bos.txt")
"saplama" | Set-Content (Join-Path $Package "listen\bos.txt")
"saplama" | Set-Content (Join-Path $Package "watch\bos.txt")
"saplama" | Set-Content (Join-Path $Package "eval\bos.txt")
"@echo off" | Set-Content (Join-Path $Package "dornick.cmd")
Copy-Item (Join-Path $Repo "pyproject.toml") $Package
Copy-Item (Join-Path $Repo "src\dornick\assets\dornick.ico") (Join-Path $Package "src\dornick\assets")

# -- 2) test builds (0.2.1 and 0.2.2) ------------------------------------
Write-Host "`n== Build (isolated identity: dornick-test / $TestGuid)" -ForegroundColor Cyan
foreach ($v in @("0.2.1", "0.2.2")) {
    & $iscc /Qp "/DVersion=$v" "/DAppName=dornick-test" "/DAppIdGuid=$TestGuid" `
        "/DPackage=$Package" "/O$Out" (Join-Path $PSScriptRoot "dornick.iss")
    if ($LASTEXITCODE -ne 0) { throw "iscc failed (version $v)" }
}
$Setup021 = Join-Path $Out "dornick-setup-0.2.1.exe"
$Setup022 = Join-Path $Out "dornick-setup-0.2.2.exe"

function Install([string]$exe, [string[]]$extra) {
    $argList = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                 "/DIR=$Target", "/MERGETASKS=!desktopicon",
                 "/YEDEKDIZIN=$Backup") + $extra
    $p = Start-Process -FilePath $exe -ArgumentList $argList -Wait -PassThru
    return $p.ExitCode
}

# -- 3) scenario: clean install -----------------------------------------
Write-Host "`n== Scenario 1: clean install (0.2.1), no .dornick" -ForegroundColor Cyan
$code = Install $Setup021 @()
Check ($code -eq 0) "install exit code 0 (actual: $code)"
Check (Test-Path (Join-Path $Target "pyproject.toml")) "pyproject.toml went into the install (single source of the version)"
$ds = (Get-ItemProperty $RegPath -ErrorAction SilentlyContinue).DisplayVersion
Check ($ds -eq "0.2.1") "DisplayVersion 0.2.1 in the registry (actual: $ds)"
Check (@(Get-ChildItem $Backup -Filter "dornick-backup-*.zip" -ErrorAction SilentlyContinue).Count -eq 0) "no backup zip created while .dornick is absent"

# -- 4) scenario: fake .dornick + update ---------------------------------
Write-Host "`n== Scenario 2: plant a fake .dornick, update to 0.2.2 on top" -ForegroundColor Cyan
$Dornick = Join-Path $Target ".dornick"
New-Item -ItemType Directory -Force (Join-Path $Dornick "mind") | Out-Null
'{"ani": "kıymetli hatıra"}' | Set-Content (Join-Path $Dornick "anilar.json") -Encoding utf8
"sqlite-saplama" | Set-Content (Join-Path $Dornick "mind\recall.db")

$code = Install $Setup022 @()
Check ($code -eq 0) "update exit code 0 (actual: $code)"
$ds = (Get-ItemProperty $RegPath -ErrorAction SilentlyContinue).DisplayVersion
Check ($ds -eq "0.2.2") "DisplayVersion in the registry became 0.2.2 (actual: $ds)"
$zips = @(Get-ChildItem $Backup -Filter "dornick-backup-*.zip" | Sort-Object Name)
Check ($zips.Count -eq 1) "backup zip WAS created (count: $($zips.Count))"
Check ((Get-Content (Join-Path $Dornick "anilar.json") -Raw) -match "kıymetli") ".dornick data in the install is intact"

# Does the zip really contain the memories?
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($zips[0].FullName)
try {
    $entries = @($zip.Entries | ForEach-Object { $_.FullName })
} finally { $zip.Dispose() }
Check (($entries -join "`n") -match "anilar\.json") "zip contains .dornick\anilar.json"
Check (($entries -join "`n") -match "recall\.db") "zip contains .dornick\mind\recall.db"

# -- 5) scenario: backup rotation ---------------------------------------
Write-Host "`n== Scenario 3: update with 6 old backups present — last 5 remain" -ForegroundColor Cyan
foreach ($n in 1..6) {
    "eski" | Set-Content (Join-Path $Backup ("dornick-backup-20200101-00000$n.zip"))
}
$code = Install $Setup022 @()
Check ($code -eq 0) "reinstall exit code 0 (actual: $code)"
$remaining = @(Get-ChildItem $Backup -Filter "dornick-backup-*.zip" | Sort-Object Name)
Check ($remaining.Count -eq 5) "only 5 backups remain (actual: $($remaining.Count))"
Check (-not (Test-Path (Join-Path $Backup "dornick-backup-20200101-000001.zip"))) "the oldest backup was deleted"
Check (($remaining[-1].Name) -match "dornick-backup-2") "the newest backup remains ($($remaining[-1].Name))"

# -- 6) scenario: running-copy detection --------------------------------
Write-Host "`n== Scenario 4: a running '-m dornick' process is detected by the installer" -ForegroundColor Cyan
# recall-mcp: a real dornick process without a model and without a window;
# the stdio protocol waits on stdin, so we keep it alive by holding stdin open.
$WorkDir = Join-Path $Root "calisma"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Py
$psi.Arguments = "-m dornick recall-mcp -C `"$WorkDir`""
$psi.WorkingDirectory = $Repo
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Seconds 3
try {
    Check (-not $proc.HasExited) "sandbox dornick process is up (PID $($proc.Id))"
    $Report = Join-Path $Root "surec-raporu.txt"
    $p = Start-Process -FilePath $Setup022 -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SADECE_TARA=1",
        "/SUREC_RAPOR=$Report") -Wait -PassThru
    Check ($p.ExitCode -ne 0) "/SADECE_TARA exited without installing (code: $($p.ExitCode))"
    $content = ""
    if (Test-Path $Report) { $content = Get-Content $Report -Raw }
    Check ($content -match [regex]::Escape("$($proc.Id)|")) "the report lists the sandbox process's PID"
    Write-Host "  report content:`n$(($content -split "`n" | ForEach-Object { '    ' + $_ }) -join "`n")"

    # -- 7) scenario: gentle → forced kill chain ------------------------
    Write-Host "`n== Scenario 5: gentle taskkill is not enough, /F kills (rationale for Attempt>0)" -ForegroundColor Cyan
    cmd /c "taskkill /PID $($proc.Id) >nul 2>&1"
    Start-Sleep -Seconds 2
    $gentleWorked = $proc.HasExited
    if (-not $gentleWorked) {
        cmd /c "taskkill /PID $($proc.Id) /F >nul 2>&1"
        Start-Sleep -Seconds 2
    }
    Check $proc.HasExited "process was closed (gentle was enough: $gentleWorked; the installer has the same escalation)"
} finally {
    if (-not $proc.HasExited) { $proc.Kill() }
}

# -- 8) scenario: uninstall does not touch .dornick ----------------------
Write-Host "`n== Scenario 7: CLEAN INSTALL — code from scratch, DATA STAYS" -ForegroundColor Cyan
# What the user expects when saying "clean install": the code of a broken
# installation goes away but their memories/tasks REMAIN. If the two get
# mixed up, "clean install" means the user is wiping their own memory.
New-Item -ItemType Directory -Force (Join-Path $Dornick "mind") | Out-Null
'{"n":"temiz-senaryo"}' | Set-Content (Join-Path $Dornick "anilar.json") -Encoding utf8
'gorev' | Set-Content (Join-Path $Dornick "tasks.json") -Encoding utf8
$staleCode = Join-Path (Join-Path $Target 'src') 'artik.py'
New-Item -ItemType Directory -Force (Join-Path $Target 'src') | Out-Null
'eski surumden kalan' | Set-Content $staleCode -Encoding utf8

$code = Install $Setup022 @("/TEMIZLE=temiz")
Check ($code -eq 0) "clean install exit code 0 (actual: $code)"
Check (Test-Path (Join-Path $Dornick "anilar.json")) "memories REMAIN in a CLEAN install"
Check (Test-Path (Join-Path $Dornick "tasks.json")) "tasks REMAIN in a CLEAN install"
Check (-not (Test-Path $staleCode)) "code file left over from the old version was deleted"
Check (Test-Path (Join-Path $Target "pyproject.toml")) "new code was put in place"

Write-Host "`n== Scenario 8: RESET DATA TOO — backup first, deletion after" -ForegroundColor Cyan
# The most dangerous path. Two things must both be true: the data must
# REALLY be gone (otherwise "reset" is a lie) and it must have been backed
# up BEFORE it went. Backup count is capped at 5 (Scenario 3): "did the
# count increase" would be the wrong measure. The right measure is that
# the NEWEST backup has changed.
$prevNewest = (Get-ChildItem $Backup -Filter "dornick-backup-*.zip" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime | Select-Object -Last 1).Name
Start-Sleep -Seconds 1   # backup name is second-stamped: avoid landing in the same second
$code = Install $Setup022 @("/TEMIZLE=veri")
Check ($code -eq 0) "data reset exit code 0 (actual: $code)"
$finalBackups = @(Get-ChildItem $Backup -Filter "dornick-backup-*.zip" -ErrorAction SilentlyContinue)
$newNewest = ($finalBackups | Sort-Object LastWriteTime | Select-Object -Last 1).Name
Check ($newNewest -ne $prevNewest) "a new backup was taken BEFORE deleting ($newNewest)"
Check (-not (Test-Path (Join-Path $Dornick "anilar.json"))) "memories were really deleted"
Check (-not (Test-Path (Join-Path $Dornick "tasks.json"))) "tasks were really deleted"
Check (Test-Path (Join-Path $Target "pyproject.toml")) "install is still healthy after the deletion"
# The deleted data must be INSIDE the backup — an empty zip is not a backup.
$newest = $finalBackups | Sort-Object LastWriteTime | Select-Object -Last 1
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($newest.FullName)
$content = @($zip.Entries | ForEach-Object { $_.FullName })
$zip.Dispose()
Check (($content -join [char]10) -match 'anilar') "the deleted memories are inside the backup"

Write-Host "`n== Scenario 6: .dornick in place after uninstall" -ForegroundColor Cyan
# Sets up its own precondition: Scenario 8 deleted the data on purpose; the
# question here is "does uninstall delete data" — hence fresh data is planted.
New-Item -ItemType Directory -Force $Dornick | Out-Null
'{"n":"kaldirma-senaryosu"}' | Set-Content (Join-Path $Dornick "anilar.json") -Encoding utf8
$unins = Join-Path $Target "unins000.exe"
if (Test-Path $unins) {
    Start-Process -FilePath $unins -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES") -Wait
    Start-Sleep -Seconds 2
    Check (Test-Path (Join-Path $Dornick "anilar.json")) "uninstall left .dornick alone"
    Check (-not (Test-Path (Join-Path $Target "pyproject.toml"))) "code files (pyproject included) were removed"
} else {
    Check $false "uninstaller not found: $unins"
}

# -- cleanup ------------------------------------------------------------
if (Test-Path $RegPath) { Remove-Item $RegPath -Recurse -Force }
$shortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\dornick-test.lnk"
if (Test-Path $shortcut) { Remove-Item $shortcut -Force }

# -- summary ------------------------------------------------------------
Write-Host ""
if ($Failed.Count -eq 0) {
    Write-Host "ALL INSTALL SCENARIOS PASSED" -ForegroundColor Green
    Write-Host "(sandbox: $Root — kept in place if you want to inspect it)"
    exit 0
}
Write-Host "FAILED: $($Failed.Count)" -ForegroundColor Red
$Failed | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
exit 1
