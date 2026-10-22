$ErrorActionPreference = "Continue"
$paths = @("server/auth", "server/validation", "server/federated-server", "hospital-node", "server/model-zoo", "server/condition-router", "server/admin", "server/synthesis")
$failed = 0
foreach ($path in $paths) {
    Write-Output "=== $path ==="
    Push-Location $path
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { $failed++ }
    Pop-Location
}
if ($failed -gt 0) { exit 1 }
