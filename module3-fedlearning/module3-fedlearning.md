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
- `server.py` — a **reference implementation** of a real, networked
  Flower server (`flwr.server.start_server` + `FedAvg` strategy) — this
  is what the project graduates to once hospitals are literally separate
  machines. Not used by `simulate.py`; kept so that jump is an obvious
  small step, not a rewrite, when the project is ready for it.
- `client_runner.py` — the corresponding real client entry point, run
  from a "hospital" machine against a real `server.py`.

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
```

`server.py` / `client_runner.py` are for the real networked path and
require a Flower server plus one client process per hospital machine —
not part of the default local demo flow yet.

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
- `server.py`/`client_runner.py` (the real networked path) are
  untested reference code, not yet exercised across real separate
  machines.
- No automated tests yet.
