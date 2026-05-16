# VOID - one-command setup for Windows (PowerShell 5.1+ / pwsh 7).
#
#   iwr -useb https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.ps1 | iex
#
# Installs Python 3.11 + Tor (via winget), drops a per-user torrc with
# ControlPort 9051 + cookie auth, starts tor.exe in the background, and
# pip-installs VOID. Re-run is safe; it skips anything already in place.

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

function VSay  { param([string]$m) Write-Host "[void] $m" -ForegroundColor Cyan }
function VOk   { param([string]$m) Write-Host "[ok]   $m" -ForegroundColor Green }
function VWarn { param([string]$m) Write-Host "[!]    $m" -ForegroundColor Red }
function VDie  { param([string]$m) VWarn $m; exit 1 }

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable('PATH', 'Machine')
    $userPath    = [Environment]::GetEnvironmentVariable('PATH', 'User')
    $env:PATH = $machinePath + ';' + $userPath
}

# winget does NOT reliably add tor.exe to PATH. Tor Browser, depending on how
# it was installed (manual portable, winget silent, expert bundle), ends up in
# very different places — including the user's Desktop in the winget case.
# Hunt it across all of them, sorted from most-likely to fallback.
function Find-TorExe {
    $rel = 'Tor Browser\Browser\TorBrowser\Tor\tor.exe'
    $candidates = @()
    foreach ($base in @($env:LOCALAPPDATA, $env:ProgramFiles, ${env:ProgramFiles(x86)},
                         [Environment]::GetFolderPath('Desktop'),
                         [Environment]::GetFolderPath('MyDocuments'),
                         (Join-Path $env:USERPROFILE 'Downloads'))) {
        if ($base) { $candidates += (Join-Path $base $rel) }
    }
    $candidates += @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Tor\tor.exe'),
        (Join-Path $env:LOCALAPPDATA 'Tor\tor.exe')
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    # Last resort: recursive scan of the whole user profile + WinGet packages root.
    $scanRoots = @($env:USERPROFILE)
    $wingetRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path $wingetRoot) { $scanRoots += $wingetRoot }
    foreach ($root in $scanRoots) {
        if (-not (Test-Path $root)) { continue }
        $found = Get-ChildItem -Path $root -Recurse -Filter 'tor.exe' -File -ErrorAction SilentlyContinue |
                 Where-Object { $_.Length -gt 100KB } |   # skip stubs / aliases
                 Sort-Object LastWriteTime -Descending |
                 Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    # Manual install on PATH.
    $onPath = Get-Command tor.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

function Test-Port {
    param([int]$port)
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', $port)
        $c.Close()
        return $true
    } catch {
        return $false
    }
}

# ---------- Python ---------------------------------------------------------

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    VSay 'installing Python 3.11 via winget...'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        VDie 'winget not available. Install Python 3.11 from https://python.org and re-run.'
    }
    winget install -e --silent --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        VDie 'Python install ran but python is still not on PATH. Open a new terminal and re-run.'
    }
}
VOk ('Python: ' + $python.Source)

# ---------- Tor ------------------------------------------------------------

$torPath = Find-TorExe
if (-not $torPath) {
    VSay 'Tor not found. Installing Tor Browser via winget (this includes a working tor.exe)...'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        VDie 'winget unavailable and Tor not found. Install Tor Browser from https://torproject.org and re-run.'
    }
    # TorProject.TorBrowser is the canonical id and ships a portable bundle that
    # extracts tor.exe somewhere under USERPROFILE (Desktop on most systems).
    winget install -e --silent --id TorProject.TorBrowser --accept-source-agreements --accept-package-agreements | Out-Null
    Start-Sleep -Seconds 2   # give the portable extractor a moment
    Refresh-Path
    $torPath = Find-TorExe
    if (-not $torPath) {
        VWarn 'Tor Browser installed but tor.exe was not located.'
        VWarn 'Open Tor Browser at least once so it extracts to its final folder, then re-run this installer.'
        VDie  'Cannot continue without tor.exe.'
    }
}
$torExe = [pscustomobject]@{ Source = $torPath }
VOk ('tor: ' + $torExe.Source)

# ---------- per-user torrc -------------------------------------------------

$torrcDir = Join-Path $env:APPDATA 'void'
$torrc    = Join-Path $torrcDir 'torrc'
$dataDir  = Join-Path $torrcDir 'tor-data'
New-Item -ItemType Directory -Force $torrcDir | Out-Null
New-Item -ItemType Directory -Force $dataDir  | Out-Null

$needsTorrc = $true
if (Test-Path $torrc) {
    $existing = Get-Content $torrc -Raw
    if ($existing -match 'ControlPort\s+9051') {
        $needsTorrc = $false
    }
}

if ($needsTorrc) {
    VSay ('writing torrc -> ' + $torrc)
    $lines = @(
        '## VOID - added by install.ps1'
        'ControlPort 9051'
        'CookieAuthentication 1'
        ('DataDirectory ' + $dataDir)
    )
    $lines -join "`r`n" | Set-Content -Encoding ASCII $torrc
    VOk 'torrc configured'
} else {
    VOk 'existing torrc already has ControlPort'
}

# ---------- start tor in background ----------------------------------------

if (-not (Test-Port 9050) -and -not (Test-Port 9150)) {
    VSay 'starting tor.exe in the background...'
    Start-Process -FilePath $torExe.Source -ArgumentList @('-f', $torrc) -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
        if (Test-Port 9050) { break }
        Start-Sleep -Seconds 1
    }
}

if (Test-Port 9050) {
    VOk 'Tor SOCKS5 up on 127.0.0.1:9050'
} elseif (Test-Port 9150) {
    VOk 'Tor SOCKS5 up on 127.0.0.1:9150 (Tor Browser bundle)'
} else {
    VWarn 'Tor did not come up automatically. Run it manually: tor.exe -f $torrc'
}

# ---------- git ------------------------------------------------------------

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    VSay 'installing Git via winget...'
    winget install -e --silent --id Git.Git --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        VDie 'git install succeeded but git is not on PATH yet. Re-open the terminal and re-run.'
    }
}

# ---------- VOID source ----------------------------------------------------

$repo = 'https://github.com/deox420/tower_of_babel.git'
$src  = Join-Path $env:LOCALAPPDATA 'void'

if (Test-Path (Join-Path $src '.git')) {
    VSay ('updating existing source -> ' + $src)
    & git -C $src pull --quiet --ff-only | Out-Null
} else {
    VSay ('cloning VOID -> ' + $src)
    & git clone --depth 1 $repo $src | Out-Null
}

VSay 'installing void-chat (pip --user)...'
& python -m pip install --quiet --user --upgrade pip | Out-Null
& python -m pip install --quiet --user -e $src | Out-Null

# Discover where pip put the scripts. Avoid Python f-strings inside the -c
# argument so PowerShell does not get confused by braces.
$pyCode = "import sysconfig; scheme = sysconfig.get_default_scheme() + '_user'; print(sysconfig.get_path('scripts', scheme))"
$pyScripts = (& python -c $pyCode 2>$null)
if ($pyScripts) { $pyScripts = $pyScripts.Trim() }

if ($pyScripts -and (Test-Path $pyScripts)) {
    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if (-not $userPath) { $userPath = '' }
    if (-not ($userPath -like ('*' + $pyScripts + '*'))) {
        $newPath = $userPath + ';' + $pyScripts
        [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
        $env:PATH = $env:PATH + ';' + $pyScripts
        VOk ('added ' + $pyScripts + ' to User PATH (open a new terminal to make it permanent)')
    }
}

VOk 'void installed'

# ---------- summary --------------------------------------------------------

Write-Host ''
Write-Host '===============================================' -ForegroundColor Green
Write-Host '  VOID is ready.'
Write-Host ''
Write-Host '  To host a room (prints a void:// link):' -ForegroundColor Cyan
Write-Host '      void --make-invite'
Write-Host ''
Write-Host '  To join a room (paste the void:// link):' -ForegroundColor Cyan
Write-Host '      void'
Write-Host ''
Write-Host '  help inside the app: press F1'
Write-Host '  health check:        void --setup'
Write-Host '===============================================' -ForegroundColor Green
Write-Host ''
