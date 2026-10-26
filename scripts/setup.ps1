# One-time setup for FAULTLINE on Windows.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1          (app only)
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Dev     (also installs test tools)
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Python {
    foreach ($v in @("3.11", "3.12", "3.13")) {
        try { $p = & py "-$v" -c "import sys; print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() } } catch {}
    }
    try {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($ver -and [version]$ver -ge [version]"3.11") { return (& python -c "import sys; print(sys.executable)").Trim() }
    } catch {}
    throw "Python 3.11 or newer is required (https://www.python.org/downloads/). Install it and re-run."
}

$python = Find-Python
Write-Host "Using Python: $python"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $python -m venv .venv
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet --require-hashes -r backend\requirements.lock
if ($Dev) { & $venvPy -m pip install --quiet --require-hashes -r backend\requirements-dev.lock }
Write-Host "Backend dependencies installed (hash-checked from backend\requirements.lock)."

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw "Node.js 18 or newer is required to build the interface (https://nodejs.org/)." }
Push-Location frontend
try {
    npm ci --no-audit --no-fund
    npm run build
} finally { Pop-Location }
Write-Host "Interface built into frontend\dist."
Write-Host ""
Write-Host "Next:"
Write-Host "  1. (for LIVE mode) powershell -ExecutionPolicy Bypass -File scripts\set-nebius-key.ps1"
Write-Host "  2. powershell -ExecutionPolicy Bypass -File scripts\start.ps1"
