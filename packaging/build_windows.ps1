[CmdletBinding()]
param(
    [string]$PythonLauncher = "py",
    [string]$InnoSetupCompiler = $env:INNO_SETUP_COMPILER
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Venv = Join-Path $Root ".venv-build"
$Release = Join-Path $PSScriptRoot "release"
$Version = (Get-Content (Join-Path $Root "VERSION") -Raw).Trim()

if (-not $InnoSetupCompiler) {
    $InnoCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    $InnoSetupCompiler = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not (Test-Path $InnoSetupCompiler)) {
    throw "Inno Setup 6 compiler not found. Set INNO_SETUP_COMPILER to ISCC.exe."
}

Push-Location $Root
try {
    if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
    & $PythonLauncher -3.12 -m venv $Venv
    $Python = Join-Path $Venv "Scripts\python.exe"
    & $Python -m pip install --disable-pip-version-check --requirement requirements.lock
    & $Python -m pytest
    & $Python scripts\generate_examples.py
    & $Python -m PyInstaller --noconfirm --clean packaging\coa-generator.spec

    New-Item -ItemType Directory -Force -Path $Release | Out-Null
    & $InnoSetupCompiler "/DAppVersion=$Version" packaging\installer-script.iss

    $Installer = Get-ChildItem $Release -Filter "COA-Generator-Setup-$Version.exe" |
        Select-Object -First 1
    if (-not $Installer) { throw "Installer output was not found." }
    $Hash = Get-FileHash -Algorithm SHA256 $Installer.FullName
    "$($Hash.Hash.ToLower())  $($Installer.Name)" |
        Set-Content -Encoding ASCII (Join-Path $Release "$($Installer.Name).sha256")
    Write-Host "Built $($Installer.FullName)"
    Write-Host "SHA-256 $($Hash.Hash)"
}
finally {
    Pop-Location
}
