# Start FAULTLINE (API + built interface) on http://127.0.0.1:8000
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Port 8000] [-NoBrowser]
param([int]$Port = 8000, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Run scripts\setup.ps1 first." }
if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) { Write-Host "Interface not built; run scripts\setup.ps1 (API will still start)." -ForegroundColor Yellow }
$env:PYTHONPATH = Join-Path $root "backend"
$url = "http://127.0.0.1:$Port"
Write-Host "FAULTLINE at $url  (Ctrl+C to stop)"
if (-not $NoBrowser) { Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 2; Start-Process $u } -ArgumentList $url | Out-Null }
& $venvPy -m uvicorn faultline.api:create_app --factory --host 127.0.0.1 --port $Port --log-level warning
