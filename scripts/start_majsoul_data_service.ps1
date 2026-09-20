param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw ".venv was not found. Create it and install requirements.txt first."
}

$Listener = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if ($Listener.Count -gt 0) { throw "Port $Port is already in use; service startup cancelled." }

Push-Location $ProjectRoot
try {
    & $PythonExe -m uvicorn majsoul_data_service.app:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
