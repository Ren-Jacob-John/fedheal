# Module 3 — Local Training + Federated Aggregation

## Setup

```bash
pip install -r requirements.txt --break-system-packages
python simulate.py
```

## What's in here

| File | Role |
|---|---|
| `data.py` | Synthetic vitals dataset + Dirichlet non-IID partitioning across N simulated hospitals |
| `real_data.py` | **New this sprint.** Pulls each active hospital's real, validated vitals from Module 1 (`GET /vitals/export`) instead of synthetic data — same `(X, y)` contract as `data.py`, so nothing downstream changes. See its docstring for the placeholder-label caveat. |
| `model.py` | The shared model architecture (logistic regression via `SGDClassifier`) and weight get/set helpers |
| `client.py` | `HospitalClient` — a Flower `NumPyClient`. This is the exact class a real hospital's local app would run. |
| `simulate.py` | Manually drives federated rounds in one process over **synthetic** data (no Ray needed) so it runs anywhere with no extra setup. |
| `simulate_real.py` | **New this sprint.** Same FedAvg loop as `simulate.py`, but over **real** hospital data via `real_data.py` — requires Module 1 + Module 2 running and at least 2 hospitals with validated vitals uploaded. |
| `server.py` | A real, networked Flower `FedAvg` server (`fl.server.start_server`, port 8080) — not used by either `simulate*.py`, which drive everything in one process instead. |
| `client_runner.py` | A real, networked Flower client for one hospital (`fl.client.start_client`) — pulls that hospital's own validated vitals via `real_data.py` and connects to `server.py`. Run one per hospital; see "Running the real networked version" below. |

## Why `simulate.py` doesn't use Flower's built-in simulation runner

`flwr.simulation.start_simulation()` needs Ray for process isolation between
simulated clients. That's the right tool once you're stress-testing many
clients or want realistic timing — but it's a heavy dependency and a common
source of version conflicts for very little benefit at this stage. Instead,
`simulate.py` drives the exact same `HospitalClient` class through the
FedAvg rounds manually, in one process. When you're ready for hospitals on
separate machines, this same `HospitalClient` plugs into
`fl.client.start_numpy_client()` unchanged (see `server.py`'s docstring).

## Reading the output

`simulate.py` reports two numbers:

- **Local-only baseline** — the average accuracy you'd get if each hospital
  trained *only* on its own data, tested against a global holdout set that
  represents the general patient population (not that hospital's own
  patients — testing on your own easy local slice makes a lone model look
  artificially strong).
- **Federated global model accuracy**, round by round, tested the same way.

The federated model should end up beating the local-only baseline — that
gap *is* the pitch for the whole project: no hospital sees another's data,
yet every hospital ends up with a model that generalizes better than it
could have built alone.

## Data partitioning

`data.py` uses a Dirichlet(alpha) split (`Hsu et al. 2019`, the standard
non-IID FL benchmark technique) so each simulated hospital has a
realistically different class balance — e.g. one hospital sees more
positive diagnoses than another — without any hospital ending up with
literally zero examples of a class. Turn `alpha` down in `data.py` to
stress-test FedAvg under more extreme skew; expect federated accuracy to
suffer in that regime — that's a real, documented FedAvg limitation worth
understanding, not a bug to chase away.

## Running the real networked version (`server.py` + `client_runner.py`)

Once at least 2 hospitals each have `--min-records` (default 10) validated
vitals uploaded (via the dashboard, or `POST /vitals/upload` — see
`module1-auth/README.md`):

```bash
# terminal 1 — the aggregation server (plaintext gRPC, localhost:8080)
python server.py

# terminal 2+ — one process per hospital, pointed at that server
python client_runner.py --hospital-name "General Hospital" --server localhost:8080
python client_runner.py --hospital-id <uuid> --server localhost:8080
```

`client_runner.py` reuses the exact same `HospitalClient` class the
in-process simulations use, loading that one hospital's own data via
`real_data.py` and never touching any other hospital's records. `--secure`
switches to TLS, but `server.py` doesn't terminate TLS yet, so this is a
localhost/LAN demo, not something to point at real traffic over the open
internet.

## Next sprint (not yet done here, on purpose)

- Swap `SGDClassifier` for XGBoost or a small PyTorch net (see the
  proposal's model-zoo discussion) — only `model.py` and `client.py`'s
  fit/evaluate need to change.
- TLS for `server.py`/`client_runner.py` — both currently talk plaintext
  gRPC (`--insecure` defaults to `True`), which is fine for a
  localhost/LAN demo and not for real hospital traffic over the open
  internet.
- Real diagnosis/outcome labels. `real_data.py` currently falls back to a
  rule-based placeholder label for any vitals record uploaded without one —
  see its docstring. That's fine for proving the pipeline runs end-to-end,
  not for anything resembling clinical evaluation. This is the actual next
  blocker, not a nice-to-have.

## Running against real data (`simulate_real.py`)

```bash
# terminal 1
cd module1-auth && uvicorn main:app --port 8001
# terminal 2
cd module2-validation && uvicorn main:app --port 8002
# then, after creating >=2 hospitals and uploading >=10 vitals records each
# via module4-dashboard-react's upload form (or curl — see module1-auth/README.md):
cd module3-fedlearning && python simulate_real.py
```

If fewer than 2 hospitals have enough validated data yet, it exits with
instructions instead of silently falling back to synthetic data.
