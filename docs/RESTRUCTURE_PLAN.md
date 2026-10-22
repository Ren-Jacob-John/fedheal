# FedHeal client-server restructure plan

Status: **Phase 1 audit only. No files have been moved.**

Branch: `ren-jacob-john-restructure-client-server`

## Baseline

The baseline was run before any structural changes.

| Check | Result |
|---|---|
| `module1-auth` backend pytest | No tests ran; exit 5 |
| `module2-validation` backend pytest | No tests ran; exit 5 |
| `module3-fedlearning` backend pytest | No tests ran; exit 5 |
| `module5-modelzoo` backend pytest | No tests ran; exit 5 |
| `module6-condition-router` backend pytest | No tests ran; exit 5 |
| `module7-admin` backend pytest | No tests ran; exit 5 |
| `module8-synthesis` backend pytest | No tests ran; exit 5 |
| Root `tests` suite | Not present |
| Dashboard `npm run build` | **Passed**; Vite transformed 28 modules |

`pytest` and dashboard npm dependencies were not installed initially, so the
existing package-manager commands were used to make the requested baseline
commands runnable. `npm ci` reported two audit findings; no dependency or
runtime behavior change is proposed for this structural refactor.

## Target mapping

The mapping below covers every tracked project file and folder. Files are
listed individually where their destination is not obvious; same-purpose
files within a listed service directory retain their relative path.

### Root and repository configuration

| Current path | New path | Decision |
|---|---|---|
| `.dockerignore` | `.dockerignore` | Keep; update ignored-path comments only if needed |
| `.gitignore` | `.gitignore` | Keep; add new generated client/server paths only if required |
| `.github/workflows/ci.yml` | `.github/workflows/ci.yml` | Keep; update all module paths and working directories |
| `.kilo/kilo.jsonc` | `.kilo/kilo.jsonc` | Keep; audit path assumptions, no behavior change |
| `.vscode/settings.json` | `.vscode/settings.json` | Keep; update paths if present |
| `README.md` | `README.md` | Keep; rewrite layout, setup, and boundary references |
| `FINAL_IMPLEMENTATION_REPORT.md` | `FINAL_IMPLEMENTATION_REPORT.md` | Keep; update links or mark historical content |
| `docker-compose.yml` | `infra/docker-compose.yml` | Move with `git mv`; update compose invocation/documentation |
| `firebase.json` | `infra/firebase.json` | Move with `git mv` |
| `firestore.rules` | `infra/firestore.rules` | Move with `git mv` |
| `firestore.indexes.json` | `infra/firestore.indexes.json` | Move with `git mv` |
| `deploy/compose.env.example` | `infra/deploy/compose.env.example` | Move with `git mv` |
| `firebase-debug.log` | `infra/firebase-debug.log` | Move only if it is intentionally tracked; otherwise record as an open question and do not delete |

### Client

| Current path | New path |
|---|---|
| `module4-dashboard-react/` | `client/dashboard/` |
| `module4-dashboard-react/.env.example` | `client/dashboard/.env.example` |
| `module4-dashboard-react/.gitignore` | `client/dashboard/.gitignore` |
| `module4-dashboard-react/Dockerfile` | `client/dashboard/Dockerfile` |
| `module4-dashboard-react/index.html` | `client/dashboard/index.html` |
| `module4-dashboard-react/module4-dashboard-react.md` | `client/dashboard/module4-dashboard-react.md` |
| `module4-dashboard-react/package.json` | `client/dashboard/package.json` |
| `module4-dashboard-react/package-lock.json` | `client/dashboard/package-lock.json` |
| `module4-dashboard-react/playwright.config.js` | `client/dashboard/playwright.config.js` |
| `module4-dashboard-react/vite.config.js` | `client/dashboard/vite.config.js` |
| `module4-dashboard-react/public/` and its `favicon.svg`, `robots.txt` | `client/dashboard/public/` |
| `module4-dashboard-react/src/` and all existing JSX/CSS files | `client/dashboard/src/` |

The dashboard API wrapper already reads `VITE_AUTH_API_BASE`,
`VITE_ADMIN_API_BASE`, and `VITE_SYNTHESIS_API_BASE`; these remain the
configurable contract variables after the move, with defaults preserved.

### Server services

| Current path | New path |
|---|---|
| `module1-auth/` and all contents | `server/auth/` |
| `module2-validation/` and all contents | `server/validation/` |
| `module5-modelzoo/` and all contents | `server/model-zoo/` |
| `module6-condition-router/` and all contents | `server/condition-router/` |
| `module7-admin/` and all contents | `server/admin/` |
| `module8-synthesis/` and all contents | `server/synthesis/` |

For each service, `Dockerfile`, `.env.example`, `requirements.txt`,
service markdown, migrations, and all Python files retain their relative
paths below the new service directory. `module5-modelzoo/models/` and
`module6-condition-router/{models,explainers}/` remain service library
subdirectories.

### Federated learning split

`module3-fedlearning/` is split by data ownership rather than copied as one
central service:

| Current path | New path | Reason |
|---|---|---|
| `server.py` | `server/federated-server/server.py` | Central Flower server |
| `fedavg.py` | `server/federated-server/fedavg.py` | Server aggregation |
| `federation_registry.py` | `server/federated-server/federation_registry.py` | Server-side round/model reporting |
| `privacy.py` | `server/federated-server/privacy.py` | Update transformation used by the server/client contract |
| `.env.example`, `config.py`, `requirements.txt`, `module3-fedlearning.md` | `server/federated-server/` equivalent | Server configuration/documentation |
| `client.py` | `hospital-node/client.py` | Hospital-local Flower client |
| `client_runner.py` | `hospital-node/client_runner.py` | Hospital-local runner |
| `data.py` | `hospital-node/data.py` | Local synthetic partition helper |
| `real_data.py` | `hospital-node/real_data.py` | Hospital-scoped local data loading |
| `model.py` | `server/shared/model.py` | Exact model parameter contract is used by both sides |
| `simulate.py`, `simulate_real.py` | `hospital-node/` equivalent | Simulation/client execution tools |
| `compare_uci_heart.py`, `seed_uci_heart.py`, `uci_heart.py` | `hospital-node/` equivalent | Dataset/demo tooling; remains local-data tooling |
| `datasets/README.md`, `datasets/heart_cleveland_islr.csv` | `hospital-node/datasets/` | Raw/demo data stays on the hospital side |

`server/federated-server` will not receive raw patient data. The existing
scoped service-token and Flower payload boundaries remain unchanged. If
`model.py` proves to be required by both executable contexts after the move,
it will be imported from `server/shared`; otherwise it will remain with the
hospital node and the decision will be recorded.

### Shared code

The following files are byte-identical by SHA-256 and are candidates for one
canonical copy in `server/shared/`:

| Files compared | SHA-256 |
|---|---|
| `module{1-auth,2-validation,3-fedlearning,7-admin,8-synthesis}/service_auth.py` | `5A434E6783B23C8724D606441058F0A42F449313505CACEBEAAB77E78337B8DC` |
| `module{1-auth,2-validation,7-admin,8-synthesis}/audit.py` | `85A6041AFA449366C51ABC14525DAE65F858268FD8A570876E16D109ED7AAB80` |
| `module{1-auth,2-validation,7-admin,8-synthesis}/docs_theme.py` | `E8C8F42E777FACA3C943D6D7BC7272761B5965F51550C0434E9A0FA319AA6222` |
| `module{1-auth,2-validation}/limits.py` | `C8DB6BAA3EACA867C745A29C2857AE12F456EB3576F87F58E278CB2ECB9F4C98` |

These will be consolidated only after a phase-4 import smoke test proves
identical behavior in every consumer. Until then, phase-2 moves preserve
copies. `config.py`, database/docstore code, auth modules, and repositories
are not treated as shared because their service-local configuration and data
ownership differ.

## Cross-module imports and runtime coupling

- Services use flat, service-local imports (`import config`, `import models`,
  `from audit import ...`), so each service must preserve its executable
  working directory or receive an explicit `PYTHONPATH`/app-directory update.
- `server/admin` currently refers to module 3 for service-auth semantics and
  registry documentation, but does not import module 3 Python files at runtime.
- `server/condition-router` adds the model-zoo directory to `sys.path` via
  `paths.py`; this must become a stable `server/model-zoo` path.
- `server/synthesis` adds model-zoo and condition-router directories to
  `sys.path` and dynamically loads `module3-fedlearning/uci_heart.py`; these
  paths must become `server/model-zoo`, `server/condition-router`, and the
  final `hospital-node/uci_heart.py` location without changing the API.
- `server/admin/model_registry.py` and module 3's registry use the same
  artifact-hash canonicalization; this is a contract to preserve, not an
  automatic shared-code consolidation.
- Docker images for admin and synthesis copy sibling module directories;
  their contexts and `COPY` paths must be updated after moves.

## Hard-coded path/configuration surfaces audited

- `docker-compose.yml`: every service `build.dockerfile`, dashboard build
  context, ports, health checks, and service URLs.
- All service `Dockerfile`s: `WORKDIR`, requirements copies, source copies,
  sibling copies, and command paths.
- `.github/workflows/ci.yml`: Python matrix names, requirements paths,
  integration test path, dashboard working directory/cache path, and
  Compose/browser-e2e commands.
- `module1-auth/alembic.ini` and `module7-admin/alembic.ini`, plus each
  migrations `env.py`: service-local script locations and import path setup.
- `client/dashboard/playwright.config.js`: test directory and E2E base URL.
- `client/dashboard/package.json`: build and Playwright scripts.
- `.env.example` files: service URLs, dashboard Vite variables, and
  credential names. Values remain placeholders; no secrets are introduced.
- `README.md`, `docs/*.md`, and all eight module markdown files: shell paths,
  links, ports, dataset locations, and module names.
- `docs/DEMO_RUNBOOK.md`, `docs/SETUP.md`, and `docs/TESTING.md`: install,
  start, test, and dashboard commands.
- `firestore.rules`, `firestore.indexes.json`, `firebase.json`, and
  `.kilo/kilo.jsonc`: configuration locations and any relative references.
- Runtime paths: `module1-auth/cases.py` upload storage default,
  module3 dataset resolution, module3 federation registry output paths, and
  synthesis dynamic imports.

## Scripts to add

Create, without Docker or a venv requirement:

- `scripts/run-all.ps1` and `scripts/run-all.sh`
- `scripts/run-one.ps1` and `scripts/run-one.sh`
- `scripts/test-all.ps1` and `scripts/test-all.sh`

They will use the current interpreter and package manager, fail explicitly on
missing dependencies, start services with the new `--app-dir`/working
directories, and preserve existing ports and environment variable names.

## Risks and mitigations

1. Flat Python imports can resolve the wrong same-named module after
   consolidation. Mitigation: preserve service working directories, use
   explicit path setup only where already required, and run import/health
   smoke checks.
2. Moving the tracked SQLite file or migration directories can change local
   development state. Mitigation: preserve the file with `git mv`, update
   Alembic paths, and do not alter schema behavior.
3. Module 3 contains both central and hospital code. Mitigation: keep raw
   dataset loading and client execution in `hospital-node`; keep server
   aggregation in `server/federated-server`; do not introduce a new API.
4. Consolidating identical shared files can break imports or `__file__`
   assumptions. Mitigation: move only after checksum confirmation and
   import smoke tests; retain separate copies if behavior differs.
5. Compose, CI, Playwright, and docs can drift from the filesystem.
   Mitigation: update all audited references in one reference-fix phase and
   validate `docker compose config`.
6. Existing checkout has no test files despite historical documentation
   mentioning tests. Mitigation: preserve this baseline fact and report any
   post-refactor test discovery changes separately.
7. Local Docker, service dependencies, browser binaries, or cloud emulators
   may be unavailable. Mitigation: distinguish unavailable verification from
   regressions and never weaken behavior to make checks pass.

## Open questions

- `firebase-debug.log` is tracked but appears generated; should it remain in
  `infra/`, or should a separate cleanup request remove it?
- Historical docs mention test files that are absent from this checkout. Are
  those tests expected to be supplied separately?
- Should the synthetic/UCI simulation scripts stay in `hospital-node`, or
  should a separate `scripts/demo/` location be preferred?
- Is `server/shared/model.py` desired as the permanent shared model contract,
  or should the model remain hospital-local with only parameter-shape
  documentation shared?
- Are `module5-modelzoo` and `module6-condition-router` intentionally
  import-only libraries, or should they eventually expose standalone service
  entrypoints? This refactor assumes they remain libraries.

## Phase and commit boundaries

1. **Audit** — this plan only.
2. **Move** — `git mv` one logical group per commit: client, each server
   service, federated server, hospital node, and infra.
3. **Fix references** — imports, Docker/Compose, CI, scripts, env examples,
   runtime paths, tests, and documentation.
4. **Shared code** — consolidate only checksum-identical files after smoke
   tests; retain and document differences otherwise.
5. **Contract docs** — document dashboard base URLs, CORS origins, and JWT or
   cookie/Authorization header flow.
6. **Verify** — backend tests, dashboard build, Compose config, and local
   health/startup checks; compare directly with the baseline table.
7. **Docs/report** — update README, architecture/service docs, and final
   report with unresolved verification and open questions.
