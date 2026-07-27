# Builds dist\WallpaperExtractor.exe (single file, no console window).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --quiet --upgrade pyinstaller pillow tkinterdnd2

foreach ($dir in "build", "dist") {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}

python -m PyInstaller --noconfirm --clean WallpaperExtractor.spec

$exe = Join-Path $PSScriptRoot "dist\WallpaperExtractor.exe"
$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "`nBuilt $exe ($mb MB)" -ForegroundColor Green
