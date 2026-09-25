# Builds build\StreamDeckTool.exe (single file) with Nuitka.
#
# Prerequisites:
#   - Python 3.13 x64 with: pip install -r requirements.txt nuitka zstandard
#   - Visual Studio 2022 Build Tools (C++ workload)
#   - hidapi.dll (x64) in the project root (see README), or pass -HidApiDll
#
# Usage:  .\build_exe.ps1 [-Python <python.exe>] [-HidApiDll <path>]

param(
    [string]$Python = ".\.venv-build\Scripts\python.exe",
    [string]$HidApiDll = ".\hidapi.dll"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path $HidApiDll)) { throw "hidapi.dll not found at '$HidApiDll'." }
$HidApiDll = (Resolve-Path $HidApiDll).Path

& $Python -m nuitka ui_main.py `
    --mode=onefile `
    --msvc=latest `
    --assume-yes-for-downloads `
    --enable-plugin=tk-inter `
    --windows-console-mode=attach `
    --windows-icon-from-ico=sde.ico `
    --include-module=pynput.keyboard._win32 `
    --include-module=pynput.mouse._win32 `
    --include-module=pystray._win32 `
    --include-module=screeninfo.enumerators.windows `
    --include-data-files="$HidApiDll=hidapi.dll" `
    --company-name="Tobias Wagner" `
    --product-name="Stream Deck Tool" `
    --file-description="Stream Deck Configuration Tool" `
    --file-version=3.0.0 `
    --product-version=3.0.0 `
    --output-dir=build `
    --output-filename=StreamDeckTool.exe

if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed (exit code $LASTEXITCODE)." }
Write-Host "Done: build\StreamDeckTool.exe"
