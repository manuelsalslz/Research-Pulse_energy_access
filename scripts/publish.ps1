# Publish research-pulse to PyPI
# Usage:
#   $env:TWINE_PASSWORD = "pypi-Ag..."   # API token from pypi.org
#   .\scripts\publish.ps1
# Or:
#   .\scripts\publish.ps1 -TestPyPI      # upload to test.pypi.org first

param(
    [switch]$TestPyPI,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

if (-not $SkipBuild) {
    Write-Host "Syncing bundled config..." -ForegroundColor Cyan
    & $Python scripts/sync_bundled.py
    Write-Host "Building sdist + wheel..." -ForegroundColor Cyan
    & $Python -m pip install -q build twine
    & $Python -m build
}

Write-Host "Checking package..." -ForegroundColor Cyan
& $Python -m twine check dist/*

if (-not $env:TWINE_PASSWORD) {
    Write-Host ""
    Write-Host "Set your PyPI API token first:" -ForegroundColor Yellow
    Write-Host '  $env:TWINE_USERNAME = "__token__"'
    Write-Host '  $env:TWINE_PASSWORD = "pypi-..."'
    Write-Host ""
    Write-Host "Create a token: https://pypi.org/manage/account/token/"
    exit 1
}

$env:TWINE_USERNAME = "__token__"
$Repo = if ($TestPyPI) { "https://test.pypi.org/legacy/" } else { "https://upload.pypi.org/legacy/" }

Write-Host "Uploading to $Repo ..." -ForegroundColor Cyan
& $Python -m twine upload dist/* --repository-url $Repo

Write-Host ""
Write-Host "Done! Users can install with:" -ForegroundColor Green
Write-Host "  pip install research-pulse"
