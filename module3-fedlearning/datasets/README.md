# Vendored evaluation dataset — UCI Heart Disease (Cleveland)

This folder holds the one **real, publicly citable** dataset FedHeal's
federated-vs-solo accuracy comparison runs on. It replaces
`data.py`'s `make_classification` synthetic data as the *demo/eval*
story (Sprint A, `docs/DEVELOPMENT_PLAN.md`). `data.py` itself stays —
it's still the right tool for offline smoke tests and for stress-testing
FedAvg under controlled non-IID skew, which a fixed 303-row real dataset
can't do.

## File

| File | Rows | SHA-256 |
|---|---|---|
| `heart_cleveland_islr.csv` | 303 (+1 header) | `8d2f18114152427beb57b7a4df4ab71fd41c010136fdaeaf6f168770f865b368` |

## Provenance

- **Original dataset:** Heart Disease, Cleveland subset
  (`processed.cleveland.data`), UCI Machine Learning Repository, dataset
  ID 45. Donated 1988. Principal investigators: Andras Janosi (Hungarian
  Institute of Cardiology), William Steinbrunn (University Hospital
  Zurich), Matthias Pfisterer (University Hospital Basel), Robert
  Detrano (V.A. Medical Center, Long Beach / Cleveland Clinic
  Foundation).
- **Citation:** Janosi, A., Steinbrunn, W., Pfisterer, M., & Detrano, R.
  (1989). *Heart Disease* [Dataset]. UCI Machine Learning Repository.
  https://doi.org/10.24432/C52P4X
- **License:** CC BY 4.0, per the UCI repository listing.
- **Immediate source of this copy:** the ISLR-python teaching mirror,
  `JWarmenhoven/ISLR-python`, path `Notebooks/Data/Heart.csv`. This is a
  faithful decode of `processed.cleveland.data` — the numeric codes for
  `cp`, `slope`, `thal` and the `num` target are spelled out as strings
  (`"asymptomatic"`, `"reversable"`, `"Yes"`/`"No"`), and nothing else is
  changed. `uci_heart.py` re-encodes them back to the original numeric
  codes on load.

### Why a mirror and not `archive.ics.uci.edu` directly

The build/CI environment this was prepared in has an egress allowlist
that doesn't include `archive.ics.uci.edu`. Rather than make the seed
step depend on network policy we don't control, the file is vendored
here (it's 11 KB) and `uci_heart.py` reads the local copy by default.
`uci_heart.py --verify` re-checks the SHA-256 above so a corrupted or
swapped file fails loudly instead of quietly training on something else.

### Fidelity checks run against this copy

These are the published characteristics of the Cleveland subset, and
this file reproduces all of them — that's the evidence it's the real
dataset and not a re-derived Kaggle variant:

- 303 records.
- Class split 164 / 139 (`num == 0` vs `num > 0`).
- `age` 29–77, `trestbps` 94–200, `thalach` 71–202.
- Exactly 6 missing values: 4 in `ca`, 2 in `thal`.

`test_uci_heart.py` asserts each of these.

> A note on the widely-circulated Kaggle `heart.csv`: the 1025-row
> version is the 303-row Cleveland data with duplicated rows, and even
> the 303-row version re-codes `cp`/`slope`/`thal` and inverts the target
> polarity relative to UCI. It was deliberately **not** used here, since
> the point of this sprint item is a *citable* dataset.

## What FedHeal actually uses from it

Only 4 of the 14 columns map onto a field that already exists in
FedHeal's vitals schema. `uci_heart.py` documents the mapping in full,
including what it does about the 5 vitals fields Cleveland has no
equivalent for — read that module docstring before quoting any accuracy
number from this data.
