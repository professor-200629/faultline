# Store your Nebius Token Factory API key for FAULTLINE without echoing it.
#
# Run in your own PowerShell window (not through an AI assistant):
#   powershell -ExecutionPolicy Bypass -File scripts\set-nebius-key.ps1
#
# The key is saved as the per-user environment variable NEBIUS_API_KEY.
# FAULTLINE's server reads it from the environment (or, on Windows, from the
# per-user registry entry), so a running server picks it up without a restart.
# The key is never written to the repository, logs or the browser.

$ErrorActionPreference = "Stop"
$secure = Read-Host -Prompt "Paste your Nebius Token Factory API key (input hidden)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
if ($key.Length -lt 20) {
    Write-Host "That does not look like an API key (too short). Nothing was saved." -ForegroundColor Yellow
    exit 1
}

[Environment]::SetEnvironmentVariable("NEBIUS_API_KEY", $key, "User")
$env:NEBIUS_API_KEY = $key
Write-Host "Saved NEBIUS_API_KEY for user $env:USERNAME ($($key.Length) characters)." -ForegroundColor Green

# Optional check: list models (free; no tokens are generated).
try {
    $resp = Invoke-RestMethod -Uri "https://api.tokenfactory.nebius.com/v1/models" -Headers @{ Authorization = "Bearer $key" } -TimeoutSec 30
    $nvidia = @($resp.data | Where-Object { $_.id -like "nvidia/*" } | ForEach-Object { $_.id })
    Write-Host "Key accepted by Nebius. NVIDIA models visible to this key:" -ForegroundColor Green
    $nvidia | ForEach-Object { Write-Host "  $_" }
    if ($nvidia -notcontains "nvidia/nemotron-3-super-120b-a12b") {
        Write-Host "Note: nvidia/nemotron-3-super-120b-a12b is not listed; set FAULTLINE_MODEL to one of the IDs above." -ForegroundColor Yellow
    }
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host "Saved, but the model-list check failed (HTTP $code). Check the key and your Token Factory credit." -ForegroundColor Yellow
} finally {
    Remove-Variable key -ErrorAction SilentlyContinue
}
