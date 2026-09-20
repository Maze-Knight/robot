$ErrorActionPreference = "Stop"
$Processes = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match 'uvicorn\s+majsoul_data_service\.app:app' })
if ($Processes.Count -eq 0) { Write-Host "Majsoul data service is not running."; exit 0 }
$Processes | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "Majsoul data service stopped."
