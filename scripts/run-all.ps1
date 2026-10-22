$env:FEDHEAL_ENV = if ($env:FEDHEAL_ENV) { $env:FEDHEAL_ENV } else { "development" }
$services = @(
    @("auth", "python", "-m uvicorn main:app --app-dir server/auth --port 8001"),
    @("validation", "python", "-m uvicorn main:app --app-dir server/validation --port 8002"),
    @("admin", "python", "-m uvicorn main:app --app-dir server/admin --port 8005"),
    @("synthesis", "python", "-m uvicorn main:app --app-dir server/synthesis --port 8006"),
    @("dashboard", "npm", "--prefix client/dashboard run dev")
)

foreach ($service in $services) {
    Start-Process -FilePath $service[1] -ArgumentList $service[2] -WorkingDirectory (Get-Location)
    Write-Output "Started $($service[0])"
}
Write-Output "Use scripts/run-one.ps1 federated-server to start the optional Flower server."
