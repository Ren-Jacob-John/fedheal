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
  hospital's own `(X, y)` partition; only weight arrays, ids, counts and
  aggregate evaluation metrics travel to the server, never the data itself.
- `data.py` — synthetic data generation and a **non-IID** (Dirichlet)
  partition across simulated hospitals, so the demo reflects the real
  problem (different hospitals have different patient population
  distributions) rather than an easy IID split.
- `real_data.py` — hospital-local loader uses the existing scoped Module 1
  credential and excludes unlabeled, flagged, or incomplete records by
  default. `load_real_partitions()` is explicitly disabled because it
  pooled raw records centrally; `client_runner.py` is the allowed
  hospital-local path.
- `simulate.py` — drives the federated rounds manually, single-process,
  using the exact same `HospitalClient` class a real deployment would
  use. Deliberately avoids `flwr.simulation.start_simulation()` (which
  needs Ray) since real multiprocessing isn't needed to prove FedAvg
  works. Reports round number / hospital count / accuracy to Module 7,
  best-effort.
- `simulate_real.py` — deprecated and refused: centralized pooling of real
  hospital data violates the privacy boundary. Use the per-hospital runner.
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
pulls that hospital's own validated data via `real_data.py`, and sends
model updates plus only hospital/request ids, provenance counts, and
aggregate evaluation metrics, never patient rows. Server-
  authenticated TLS is supported by Flower's certificate arguments but
  remains opt-in (`--insecure` defaults on for localhost). Client-
  certificate mTLS is unsupported by this Flower adapter.

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

# Verify the vendored UCI Heart Disease dataset:
python uci_heart.py --verify

# Federated-vs-solo on REAL UCI data, offline (no services needed).
# This is the defensible number — always run the sweep before quoting it:
python compare_uci_heart.py --sweep 20

# Seed the demo/eval data into Module 1 through the real upload path
# (needs Modules 1 and 2 running):
python seed_uci_heart.py --hospitals 3

# Synthetic-data simulation (no other services needed):
python simulate.py

# Centralized real-data pooling is disabled by the privacy boundary. This
# legacy entry point now exits with an explicit refusal:
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

- `run_local_smoke_test.sh` — spins up a throwaway Module 1 (local document store),
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
  generalization. Public-data comparison is handled by
  `compare_uci_heart.py`; centralized hospital-data pooling is disabled.
  ```bash
  python test_client_runner_matches_simulation.py --hospitals 3 --records-per-hospital 20
  ```

### Which comparison script to run

| Script | Data | Labels | Needs services? |
|---|---|---|---|
| `simulate.py` | synthetic (`make_classification`) | synthetic | No |
| `compare_uci_heart.py` | **real** (UCI Cleveland) | **real** | No |
| `simulate_real.py` | disabled; central pooling is refused | n/a | No |

`simulate.py` isn't obsolete — it's the synthetic-data harness for
controlled-skew FedAvg checks. `compare_uci_heart.py` is the offline,
public-data comparison tool; only quote its multi-seed summary with its
spread and win rate, not a single run as clinical performance.

The real-services integration, including hospital-local networked clients,
count-triggered requests, candidate registration, validation/promotion and
inference, is exercised by
`python -m pytest -q tests/integration/test_federation_flow.py` from the repo
root. Each client needs a Module 1 token scoped to that hospital
(`FEDHEAL_SVC_TOKEN_M3_M1`) and a Module 7 retraining token
(`FEDHEAL_SVC_TOKEN_M3_M7`); tokens must never be shared across hospitals.

For count-gated scheduling, run the hospital-local client with
`client_runner.py --watch-retraining --hospital-id <id>`. It additionally
requires a hospital-scoped `FEDHEAL_SVC_TOKEN_M3_M7` minted by
Module 7's `mint_retraining_runner_token.py`, and polls
`FEDHEAL_ADMIN_API_URL` (default `http://localhost:8005`). Module 7's
`FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS` threshold is disabled when unset or
zero. The runner reports only an eligible-record count to M7 and excludes flagged
and placeholder-labeled records in watch mode. Each fit/evaluation message
contains only ids and counts/metrics needed to associate the round with its
claimed requests and attest eligible inputs. On a complete final round, the
networked server registers the aggregated weights and aggregate local-holdout
metrics as a CANDIDATE only when all participating requests and provenance
counts match. Otherwise it logs an explicit skip; the runner marks the
request FAILED and the eligibility baseline is not advanced. M7 links
candidate ids to requests. Nothing is auto-validated or promoted.

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
- **Labels (changed in Sprint A).** `_placeholder_label` is no longer the
  default path. Unlabeled records are excluded server-side
  (`labeled_only=true` on Module 1's export), hitting one without the
  explicit `--allow-placeholder-labels` flag raises `UnlabeledDataError`
  naming the hospital, and every loader now returns a `LabelProvenance`
  alongside the data. Runs that do use placeholders print a warning
  banner before any accuracy number and are stamped `NON-CLINICAL` in the
  round report sent to Module 7.
- **The UCI seed covers only 3 of 8 features.** Cleveland supplies
  `age`, `trestbps` and `thalach` and nothing that maps to diastolic BP,
  height, weight, or medication load; those five slots are fixed
  constants pinned to the normalization mean so they contribute exactly
  zero. Quote results as "3 real vitals features from Cleveland", never
  as "UCI Heart Disease accuracy". Closing that gap means adding real
  clinical columns to the vitals schema, which changes `N_FEATURES` and
  therefore Module 5/6 too — deliberately out of Sprint A's scope. Note
  also that `thalach` is exercise *maximum* heart rate, not a resting
  vital.
- **Single runs of the comparison are not results.** A ~47-record global
  holdout means one patient moves accuracy by two points, and the sign of
  the federated-vs-solo delta changes between seeds. Over 20 seeds
  federation wins 17 and averages +0.077 — report the mean, the spread
  and the win rate together, via `compare_uci_heart.py --sweep 20`.
- `server.py`/`client_runner.py` (the real networked path) are now
  implemented and verified — via `run_local_smoke_test.sh` and
  `test_client_runner_matches_simulation.py` — to reach the same result
  as the known-good in-process simulation. Not yet exercised across
  actually-separate physical machines or under TLS. The durable retraining
  queue-triggered candidate link flow passes in the integration test across
  separate service processes, but not yet in separate containers.
- Aside from the two tests above, the rest of the module (synthetic
  simulation, `client.py`, `model.py`, `data.py`) still has no dedicated
  unit tests.
