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
| `model.py` | The shared model architecture (logistic regression via `SGDClassifier`) and weight get/set helpers |
| `client.py` | `HospitalClient` — a Flower `NumPyClient`. This is the exact class a real hospital's local app would run. |
| `simulate.py` | **Run this.** Manually drives federated rounds in one process (no Ray needed) so it runs anywhere with no extra setup. |
| `server.py` | Reference for a REAL networked Flower server — next sprint's work, not used by `simulate.py`. |

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

## Next sprint (not yet done here, on purpose)

- Swap `data.py`'s synthetic data for a real public dataset (UCI Heart
  Disease, MIMIC-III-derived features) — nothing downstream needs to change.
- Swap `SGDClassifier` for XGBoost or a small PyTorch net (see the
  proposal's model-zoo discussion) — only `model.py` and `client.py`'s
  fit/evaluate need to change.
- Stand up `server.py` for real, and write a `client_runner.py` that a
  "hospital" machine actually runs (`fl.client.start_numpy_client`),
  swapping the in-process loop in `simulate.py` for real gRPC traffic.
- Wire Module 2's validation output in as this module's training data,
  instead of the synthetic partitions.
