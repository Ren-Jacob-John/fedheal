# Module 3 — Local Training + Federated Aggregation: Full Explanation

## What this module is for

This is the technical core of the entire project — the piece that
actually implements federated learning, which is the whole reason FedHeal
exists instead of just being "upload your data to one server and train a
model." The idea: each hospital trains a model on its own local data, and
only the *model's learned adjustments* (a set of numbers, not patient
records) ever leave that hospital. A central process averages those
adjustments together into one improved shared model and sends it back out.
Nobody's raw data ever travels anywhere.

## How it works

Three pieces work together:

- **`model.py`** defines the shared architecture every hospital trains —
  currently logistic regression via scikit-learn's `SGDClassifier`, chosen
  specifically because its weights are a flat, simple array that's easy to
  average, which makes the federated-averaging math easy to see working
  correctly before adding more complex architectures (XGBoost, PyTorch)
  later.
- **`client.py`** defines `HospitalClient` — one instance represents one
  hospital's local training process. It only ever touches that hospital's
  own data. Given the current global model's weights, it does one round of
  local training (`fit`) and returns the *updated weights*, never the
  data it trained on.
- **The FedAvg loop** (`simulate.py` / `simulate_real.py`) drives the
  rounds: ask every hospital client to train locally on the current global
  weights, collect their updated weights, average them (weighted by how
  much data each hospital trained on), and repeat. After a fixed number of
  rounds, the resulting global model is evaluated against a holdout set
  that represents patients no single hospital saw.

## Two ways to run it

- **`simulate.py`** — synthetic data (`data.py`), generated locally with a
  non-IID partition across simulated hospitals (Dirichlet split, the
  standard technique for making simulated hospitals look realistically
  different from each other). This has zero dependencies on any other
  module and was built first, deliberately, so the federated-averaging
  logic itself could be proven correct in isolation before anything else
  depended on it.
- **`simulate_real.py`** *(added during the data-flow integration
  sprint)* — the same FedAvg loop, but the data comes from
  `real_data.py`, which pulls each active hospital's actual
  validated vitals from Module 1 (which got them from Module 2). This is
  what "the pipeline actually works end-to-end" looks like: a hospital
  uploads vitals through the dashboard, they get validated, and this
  script trains a real federated model on them.

## The fairness comparison that matters

Every run reports two numbers: what each hospital could achieve training
**only on its own data**, and what the **federated global model**
achieves — both evaluated on the same holdout set that no hospital trained
or locally tested on. That comparison is deliberate and important: testing
a hospital's model only on patients like its own makes it look artificially
strong. The federated model's whole value proposition is generalizing to
patients no single hospital ever saw, so that's the fair test.

## How other modules depend on it

- **Module 1** is where `simulate_real.py` gets its real data from
  (`GET /vitals/export`).
- **Module 7** receives a best-effort report after every completed round
  — round number, hospital count, global accuracy, baseline accuracy —
  so a platform operator can see "is the model actually improving?"
  without reading terminal output.

## What's real vs. what's a known prototype simplification

Real: the FedAvg math itself, the non-IID simulation, the real-data
pipeline via `real_data.py`/`simulate_real.py`. Documented as next-sprint
work in this folder's `README.md`: `server.py` is a *reference*
implementation of a real networked Flower server (not yet wired up — both
`simulate*.py` scripts drive everything in one process); the model
architecture is still logistic regression, not the XGBoost/PyTorch models
the proposal calls for; and — the most important open gap — uploaded
vitals don't carry a real diagnosis/outcome label yet, so `real_data.py`
falls back to a rule-based placeholder label when one's missing. Any
accuracy number `simulate_real.py` reports right now demonstrates the
*pipeline* works, not clinical performance.
