# Testing and verification

## Current checkout results

The verification run for this documentation task used Python 3.12.10,
Node.js v24.12.0, and npm 11.11.0.

| Check | Result |
|---|---|
| `python -m pytest -q` in each Python module | **Executed** in `server/auth`, `server/validation`, `server/federated-server`, `hospital-node`, `server/model-zoo`, `server/condition-router`, `server/admin`, and `server/synthesis`; each reported `no tests ran` and exit 5 |
| Test file inventory | No `test_*.py`, `*_test.py`, root `tests/`, or Playwright spec files are present in this checkout |
| `npm --prefix client/dashboard run build` | **Passed**; Vite transformed 28 modules and produced `dist/`. |
| `docker compose -f infra/docker-compose.yml --env-file infra/deploy/compose.env.example config` | **Passed** |

No Python pass count is claimed because no test files are present. The
non-zero pytest exit code is the standard pytest result for an empty test
collection, not a failing assertion.

## Available commands when dependencies and tests are supplied

```text
python -m pytest -q
python -m compileall server/auth server/validation server/federated-server hospital-node server/model-zoo server/condition-router server/admin server/synthesis
npm --prefix client/dashboard run build
npm --prefix client/dashboard run test:e2e
docker compose -f infra/docker-compose.yml config
docker compose -f infra/docker-compose.yml up --build
```

The cross-platform wrappers are:

```text
scripts/test-all.ps1
scripts/test-all.sh
scripts/run-all.ps1
scripts/run-all.sh
```

The module `requirements.txt` files define runtime dependencies. The React
package defines `test:e2e` as `playwright test`, but no test spec is present in
this checkout.

## Coverage gaps verified from the tree

- No executable Python test suite is present.
- Browser E2E execution is not verified.
- Full Docker image build/Compose runtime, TLS, load, and multi-machine
  Flower execution are not verified in this task.
- The model registry stores reported metrics and gates them; it does not
  independently re-measure clinical performance.

## Documentation discrepancy

The previous `docs/TESTING.md` listed historical module and integration test
results, including named test files, but those files are absent from the
current checkout. This document reports only checks executed against the
current tree.
