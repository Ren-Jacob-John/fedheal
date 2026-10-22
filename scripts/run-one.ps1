param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("auth", "validation", "federated-server", "admin", "synthesis", "dashboard")]
    [string] $Service
)

$env:FEDHEAL_ENV = if ($env:FEDHEAL_ENV) { $env:FEDHEAL_ENV } else { "development" }

switch ($Service) {
    "auth" { python -m uvicorn main:app --app-dir server/auth --port 8001 }
    "validation" { python -m uvicorn main:app --app-dir server/validation --port 8002 }
    "federated-server" { python server/federated-server/server.py --address 0.0.0.0:8080 }
    "admin" { python -m uvicorn main:app --app-dir server/admin --port 8005 }
    "synthesis" { python -m uvicorn main:app --app-dir server/synthesis --port 8006 }
    "dashboard" { npm --prefix client/dashboard run dev }
}
