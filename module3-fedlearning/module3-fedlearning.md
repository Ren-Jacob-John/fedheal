# Module 3 — Local Training + Federated Aggregation

## What this module is for

This is the core of the "federated" part of FedHeal: it proves that
multiple hospitals can collaboratively improve one shared model **without
any hospital's raw patient data ever leaving that hospital** — only
learned model weights are exchanged, and a central process averages them
(Federated Averaging / FedAvg).

## How it works internally

**Files:**
- `model.py` — the shared model architecture: `SGDClassifier` (logistic
  regression via incremental `partial_fit`), chosen specifically because
  its weights are a flat, simple numpy array that's trivial to average
  correctly — the clearest way to see FedAvg actually working before
  layering on XGBoost/PyTorch's extra complexity.
- `client.py` — `HospitalClient`, a `flwr.client.NumPyClient`. One
  instance = one hospital's local node. It only ever touches that
  hospital's own `(X, y)` partition; only `fit()`'s returned weight
  arrays travel back to the server, never the data itself.
- `data.py` — synthetic data generation and a **non-IID** (Dirichlet)
  partition across simulated hospitals, so the demo reflects the real
  problem (different hospitals have different patient population
  distributions) rather than an easy IID split.
- `real_data.py` — pulls **real, validated** hospital data from Module
  1's `/vitals/export` (service-to-service, authenticated) instead of
  synthetic data. Documents openly that when a record has no real
  clinical outcome label, it falls back to a **rule-based placeholder
  label** (`_placeholder_label`) purely so the pipeline is runnable
  end-to-end today — this is a known, intentional limitation, not a
  hidden bug, and should be swapped for real clinical labels as soon as
  they're available from a hospital's own records.
- `simulate.py` — drives the federated rounds manually, single-process,
  using the exact same `HospitalClient` class a real deployment would
  use. Deliberately avoids `flwr.simulation.start_simulation()` (which
  needs Ray) since real multiprocessing isn't needed to prove FedAvg
  works. Reports round number / hospital count / accuracy to Module 7,
  best-effort.
- `simulate_real.py` — the same round-driving loop as `simulate.py`, but
  against `real_data.py`'s real (validated, currently placeholder-labeled)
  hospital data instead of synthetic data.
- `server.py` — the **real, networked** Flower server
  (`fl.server.start_server` + a custom `DeterministicFedAvg` strategy) —
  this is what the project graduates to once hospitals are literally
  separate machines, and it is now implemented and verified working, not
  just scaffolding. Accepts `--min-clients`, `--rounds`, `--address` on
  the command line; prints a final `FINAL_ACCURACY: <n> (round <r>)` line
  in a fixed, greppable format that both humans and `test_client_runner_
  matches_simulation.py` (below) parse.
- `client_runner.py` — the real per-hospital client entry point. One
  process per hospital, pointed at `server.py`, reusing the exact same
  `HospitalClient` class the in-process simulations use — only the
  caller changes, from a manual Python loop to Flower's real gRPC
  transport. Resolves a hospital by `--hospital-id` or `--hospital-name`,
  pulls that hospital's own validated data via `real_data.py`, and never
  sends anything but model weights over the wire. TLS is explicitly out
  of scope for now (`--insecure` defaults on, matching `server.py`'s
  plaintext listener) — noted directly in both files' docstrings as a
  deferred item, not an oversight.

**Why `DeterministicFedAvg` exists (worth understanding, not just
knowing it's there):** plain Flower `FedAvg` aggregates client results in
whatever order they arrive over the network — normally invisible, but
with this project's `SGDClassifier` (small feature/sample counts,
predictions often sitting near the 0.5 decision boundary), floating-point
summation *order alone* was enough to swing a round's reported accuracy
by double digits between two otherwise-identical runs. `DeterministicFedAvg`
sorts results by `hospital_id` (the FedHeal identity, not Flower's own
per-connection `ClientProxy.cid`) before aggregating, so a run's result
depends only on the data and the code — not on network timing. This was
found and fixed via the test described below, not discovered in
production.

**Feature scaling (`real_data.py`) — a related, load-bearing fix:** the
real-data feature vector spans wildly different raw scales (roughly 0–5
for `medication_count` up to 0–400+ for `medication_mg_total`).
`SGDClassifier`'s gradient step scales with raw feature magnitude, so a
single unscaled `partial_fit()` epoch could send `coef_` from 0 to the
thousands — making every real-data FL run numerically unstable
(wild round-to-round accuracy swings, hypersensitive to summation order)
independent of networking entirely. `real_data.py` now applies a fixed
`(x - _FEATURE_MEAN) / _FEATURE_STD` normalization with constants agreed
in advance (never fit from a hospital's own data — every hospital must
apply the *identical* transform to the *identical* feature, or FedAvg is
silently averaging models trained in different feature spaces).

**What one simulation run proves:** N simulated hospitals each train
locally on their own non-IID data partition for one local epoch, only
their model weights are centralized, the server averages those weights
(FedAvg), and the resulting global model is evaluated on a shared holdout
set no single hospital trained or tested on — the fair comparison of
"federated" vs. "any one hospital training alone."

## How to run it

```bash
cd module3-fedlearning
pip install -r requirements.txt

# Synthetic-data simulation (no other services needed):
python simulate.py

# Real-data simulation (needs Module 1 running and reachable, plus its
# service key configured):
python simulate_real.py

# Real NETWORKED path — one Flower server + one client process per
# hospital (needs Module 1 running, reachable, and each hospital already
# holding >= --min-records validated vitals):
python server.py --min-clients 2 --rounds 8
# then, one per hospital, in separate terminals/machines:
python client_runner.py --hospital-name "General Hospital" --server localhost:8080
python client_runner.py --hospital-name "Rural Clinic"     --server localhost:8080
```

### Automated checks for the real networked path

- `run_local_smoke_test.sh` — spins up a throwaway Module 1 (SQLite),
  seeds N non-IID hospitals, starts `server.py`, starts N real
  `client_runner.py` processes, and asserts the run completes with every
  client's results aggregated every round (fails loudly, with logs, on
  any client error or missing-participant round). Safe to wire into CI.
  ```bash
  ./run_local_smoke_test.sh                # 3 hospitals (default)
  ./run_local_smoke_test.sh --hospitals 5
  ```
- `test_client_runner_matches_simulation.py` — the more rigorous check:
  runs the real networked path (subprocesses, real gRPC) and an
  in-process reproduction of the *identical* clients/data/rounds/
  aggregation math, then asserts their final accuracy matches within a
  tolerance. This is what originally caught both the non-determinism bug
  (fixed by `DeterministicFedAvg`) and the feature-scaling bug (fixed in
  `real_data.py`) — it's a plumbing check ("did the real path reproduce
  the same math as the known-good in-process path"), not a claim about
  generalization, which remains `simulate_real.py`'s job via its
  global-holdout comparison.
  ```bash
  python test_client_runner_matches_simulation.py --hospitals 3 --records-per-hospital 20
  ```

**Key environment variables** (read via `real_data.py` / `simulate_real.py`):
match Module 1's `FEDHEAL_SVC_KEY_M3_M1` and the URL Module 1 is
reachable at.

## How it depends on / is depended on by other modules

- **Calls:** Module 1's `/vitals/export` (real data path only), Module 7
  (best-effort round/accuracy reporting).
- **Depended on by:** the whole project's core value proposition — the
  federated-vs-solo accuracy comparison this module produces is the
  central proof point of the system.

## Known limitations / current status

- The shared model is a simple logistic regression by design (see
  `model.py`'s docstring) — swapping in XGBoost/PyTorch is future work
  that doesn't require changing `simulate.py`'s round-driving loop.
- `_placeholder_label` in `real_data.py` is a rule-based stand-in for a
  real clinical outcome label — flag this clearly in any external-facing
  demo or documentation until real labels are wired up.
- `server.py`/`client_runner.py` (the real networked path) are now
  implemented and verified — via `run_local_smoke_test.sh` and
  `test_client_runner_matches_simulation.py` — to reach the same result
  as the known-good in-process simulation. Not yet exercised across
  actually-separate physical machines (everything tested so far is
  localhost/subprocess-based) or under TLS — both explicitly deferred,
  not overlooked (see `docs/development-plan-to-oct20.md` if present in
  your checkout, or ask the team for its current equivalent).
- Aside from the two tests above, the rest of the module (synthetic
  simulation, `client.py`, `model.py`, `data.py`) still has no dedicated
  unit tests.
