# Local setup

The commands below use placeholders for secrets. Do not copy real credentials
into documentation or source control.

## Prerequisites

- Python version required by the repository documentation: Python 3.11+.
  The verification environment used Python 3.12.10.
- Node.js 18+ and npm for Module 4. Verification used Node.js v24.12.0 and
  npm 11.11.0.
- Optional Docker/Compose and Firebase CLI for emulator workflows.

## Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:FEDHEAL_ENV = "development"
python -m pip install -r server/auth\requirements.txt
python -m pip install -r server/validation\requirements.txt
python -m pip install -r module3-fedlearning\requirements.txt
python -m pip install -r server/model-zoo\requirements.txt
python -m pip install -r server/condition-router\requirements.txt
python -m pip install -r server/admin\requirements.txt
python -m pip install -r server/synthesis\requirements.txt
Copy-Item deploy\compose.env.example .env
```

For separate services, copy each module's `.env.example` to `.env` in that
module and replace placeholders with matching values. At minimum, set a
development environment, dashboard origin, JWT secret, and the signing keys
needed by each caller/provider pair. The examples use local defaults and are
not production secrets.

Create the first super admin:

```powershell
python server/auth\create_super_admin.py --email admin@example.invalid
```

The script reads the configured bootstrap password/environment as implemented
by the module. If no documented bootstrap password is configured, inspect the
script's required arguments before running it; this task did not execute
service startup or account creation.

Start services in separate PowerShell windows:

```powershell
python -m uvicorn main:app --app-dir server/auth --port 8001
python -m uvicorn main:app --app-dir server/validation --port 8002
python -m uvicorn main:app --app-dir server/admin --port 8005
python -m uvicorn main:app --app-dir server/synthesis --port 8006
npm --prefix client/dashboard install
npm --prefix client/dashboard run dev
```

The dashboard defaults to `http://localhost:5173`. Module 3's Flower server
uses port 8080 in Compose; its server/client scripts must be started only
after the required Module 1/7 service tokens and eligible data exist.

## Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
export FEDHEAL_ENV=development
for m in server/auth server/validation module3-fedlearning server/model-zoo server/condition-router server/admin server/synthesis; do
  python -m pip install -r "$m/requirements.txt"
done
cp infra/deploy/compose.env.example .env
```

Copy each module `.env.example` to its local `.env`, then use the same
`uvicorn`, `create_super_admin.py`, and `npm` commands shown above with
forward-slash paths.

## Docker Compose

At the repository root:

```bash
cp infra/deploy/compose.env.example .env
# replace every CHANGE_ME value with a generated placeholder-safe secret
docker compose config
docker compose up --build
```

Compose starts the Firestore emulator, Modules 1, 2, 7, and 8, and the
dashboard. Module 3 is behind the `federation` profile:

```bash
docker compose --profile federation up --build
```

The current verification could not validate Compose because root `.env` was
absent; Docker runtime was not run. The Compose file itself states that the
Firestore emulator is in-memory and data is lost when it stops.
