# Testing and verification

## Current checkout results

The verification run for this documentation task used Python 3.12.10,
Node.js v24.12.0, and npm 11.11.0.

| Check | Result |
|---|---|
| `python -m pytest -q` in each Python module | **Not run to completion**: `pytest` is not installed; each invocation failed with `No module named pytest`. |
| Test file inventory | No `test_*.py`, `*_test.py`, root `tests/`, or Playwright spec files are present in this checkout. Historical test claims in existing docs are therefore not reproducible from this tree. |
| `npm --prefix client/dashboard run build` | **Passed**; Vite transformed 28 modules and produced `dist/`. |
| `docker compose config` | **Not verified**; Compose stopped because root `.env` is absent. |

No Python pass/fail count is claimed. Installing dependencies and running
historical suites would require test files that are not present here.

## Available commands when dependencies and tests are supplied

```text
python -m pytest -q
python -m compileall server/auth server/validation module3-fedlearning server/model-zoo server/condition-router server/admin server/synthesis
npm --prefix client/dashboard run build
npm --prefix client/dashboard run test:e2e
docker compose config
docker compose up --build
```

The module `requirements.txt` files define runtime dependencies. The React
package defines `test:e2e` as `playwright test`, but no test spec is present in
this checkout.

## Coverage gaps verified from the tree

- No executable Python test suite is present.
- Browser E2E execution is not verified.
- Real Firestore, Firestore emulator, Docker/Compose runtime, TLS, load, and
  multi-machine Flower execution are not verified in this task.
- The model registry stores reported metrics and gates them; it does not
  independently re-measure clinical performance.

## Documentation discrepancy

The previous `docs/TESTING.md` listed historical module and integration test
results, including named test files, but those files are absent from the
current checkout. This document reports only checks executed against the
current tree.
