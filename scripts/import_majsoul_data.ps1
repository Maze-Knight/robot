param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$DatabasePath = "data\majsoul_data_service.sqlite3"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw ".venv was not found." }
$ImportFile = (Resolve-Path -LiteralPath $Path).Path
Push-Location $ProjectRoot
try {
    & $PythonExe -c "import asyncio; from pathlib import Path; from majsoul_data_service.database import MajsoulDataRepository; from majsoul_data_service.importer import import_local_file; repo=MajsoulDataRepository(Path(r'''$DatabasePath''')); asyncio.run(repo.initialize()); print(asyncio.run(import_local_file(repo, Path(r'''$ImportFile'''))))"
    if ($LASTEXITCODE -ne 0) { throw "Import failed." }
} finally { Pop-Location }
