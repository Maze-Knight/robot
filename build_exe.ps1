param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw ".venv was not found. Create it and install requirements.txt first."
}

Push-Location $ProjectRoot
try {
    if (-not $SkipInstall) {
        & $PythonExe -m pip install -r requirements.txt -r build-requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "Failed to install build dependencies." }
    }

    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --console `
        --hidden-import "trickcal.legacy" `
        --add-data "daily_draw_assets;daily_draw_assets" `
        --add-data "trickcal_assets;trickcal_assets" `
        --name "ElenaBot" `
        main.py
    if ($LASTEXITCODE -ne 0) { throw "Failed to build the EXE." }

    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name "ElenaManager" `
        manager.py
    if ($LASTEXITCODE -ne 0) { throw "Failed to build the management EXE." }

    Copy-Item -LiteralPath ".env.example" -Destination "dist\.env.example" -Force
    Copy-Item -LiteralPath "DEPLOY_WINDOWS.md" -Destination "dist\DEPLOY_WINDOWS.md" -Force
    Copy-Item -LiteralPath "daily_draw_pool.json" -Destination "dist\daily_draw_pool.json" -Force
    New-Item -ItemType Directory -Path "dist\data" -Force | Out-Null
    New-Item -ItemType Directory -Path "dist\logs" -Force | Out-Null

    Write-Host ""
    Write-Host "Build complete: $ProjectRoot\dist\ElenaBot.exe"
    Write-Host "Management terminal: $ProjectRoot\dist\ElenaManager.exe"
    Write-Host "Deploy the dist folder, rename .env.example to .env, and fill in real settings."
} finally {
    Pop-Location
}
