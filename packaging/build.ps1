#!/usr/bin/env pwsh
# Reproducible build for VOID on Windows.
# For byte-for-byte parity with the official release, build inside
# Dockerfile.build (Linux). The Windows binary will differ across OSes
# but will reproduce across runs on the same Windows host.
$ErrorActionPreference = "Stop"

# Work from repo root regardless of where build.ps1 is invoked from.
$here = Split-Path -Parent $PSCommandPath
if (Test-Path (Join-Path $here "..\VERSION")) {
    Set-Location (Resolve-Path (Join-Path $here ".."))
} else {
    Set-Location $here
}

$Version = (Get-Content -Raw VERSION).Trim()
$sdeFile = if (Test-Path "packaging\SOURCE_DATE_EPOCH") { "packaging\SOURCE_DATE_EPOCH" } else { "SOURCE_DATE_EPOCH" }
$env:SOURCE_DATE_EPOCH = (Get-Content -Raw $sdeFile).Trim()
$env:PYTHONHASHSEED    = "0"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:TZ                = "UTC"
$env:LC_ALL            = "C.UTF-8"

$Platform = "windows"
$Arch     = $env:PROCESSOR_ARCHITECTURE.ToLower()

Write-Host "[void/build] VERSION=$Version  SOURCE_DATE_EPOCH=$env:SOURCE_DATE_EPOCH"
Write-Host "[void/build] PLATFORM=$Platform-$Arch"

if (Test-Path dist)  { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }

$specDir = if (Test-Path "packaging\babel.spec") { "packaging" } else { "." }
pyinstaller --clean --noconfirm (Join-Path $specDir "void-server.spec")
pyinstaller --clean --noconfirm (Join-Path $specDir "babel.spec")

Push-Location dist
$epoch = [int]$env:SOURCE_DATE_EPOCH
$dt    = (Get-Date -Date "1970-01-01Z").AddSeconds($epoch)
Get-ChildItem -Recurse | ForEach-Object {
    $_.LastWriteTimeUtc = $dt
    $_.CreationTimeUtc  = $dt
    $_.LastAccessTimeUtc = $dt
}

foreach ($stem in @("babel", "void-server")) {
    $candidates = @("$stem", "$stem.exe")
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $suffix = if ($c.EndsWith(".exe")) { ".exe" } else { "" }
            $new = "$stem-$Version-$Platform-$Arch$suffix"
            Move-Item -Force $c $new
        }
    }
}

# Deterministic SHA256SUMS.
$files = Get-ChildItem | Where-Object { $_.Name -ne "SHA256SUMS" -and $_.Name -ne "SHA256SUMS.asc" } | Sort-Object Name
$lines = @()
foreach ($f in $files) {
    $hash = (Get-FileHash -Algorithm SHA256 $f.FullName).Hash.ToLower()
    $lines += "$hash  $($f.Name)"
}
$lines | Out-File -Encoding ascii -NoNewline SHA256SUMS
"`n" | Out-File -Encoding ascii -Append SHA256SUMS

Write-Host "[void/build] SHA256SUMS:"
Get-Content SHA256SUMS

if ($env:VOID_GPG_SIGN -eq "1") {
    gpg --batch --yes --detach-sign --armor SHA256SUMS
    Write-Host "[void/build] signed -> dist/SHA256SUMS.asc"
}

Pop-Location
