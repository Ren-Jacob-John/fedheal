# Federated learning

## Round model

The current shared model is an scikit-learn `SGDClassifier` used as a
logistic-regression-style binary classifier. A `HospitalClient` owns one
hospital's local `(X, y)` partition. In each round it receives weights, runs
one local `partial_fit` epoch, evaluates locally, and returns updated weights,
sample count, hospital id, and aggregate metrics. It never returns raw feature
rows.

The server uses weighted FedAvg: each layer is weighted by the client's
training-example count. The deterministic Flower strategy sorts results by
hospital id before aggregation so network arrival order does not change the
floating-point result.

## Data sources

- `module3-fedlearning/data.py` creates synthetic non-IID partitions for the
  local simulation.
- `uci_heart.py` and `seed_uci_heart.py` use the vendored UCI Cleveland data
  for a public-data demo path.
- `real_data.py` loads hospital-scoped records from Module 1. By default it
  excludes unlabeled, flagged, and incomplete records.
- `simulate_real.py` intentionally refuses centralized raw-data pooling.

The UCI mapping supplies real values for only age, systolic blood pressure,
and heart rate in the current eight-feature schema; remaining feature slots
are constants. It is therefore demo/public data, not evidence of clinical
performance.

## Registry lifecycle

1. Module 3 reports aggregate round metadata and can register a model candidate
   in Module 7.
2. Module 7 verifies candidate metadata/artifact integrity and stores it as
   `CANDIDATE`.
3. A `super_admin` invokes validation. The registry stores `PASSED` or
   `FAILED` validation status and a report.
4. A `super_admin` explicitly promotes a passed candidate to `DEPLOYED`.
   Previous deployment becomes retired/replaced.
5. Rollback restores a prior registered deployment. Module 8 reads only the
   promoted model for production-like inference.

No scheduler or automatic promotion is implemented.

## Privacy mechanisms actually present

- Hospital-local data loading and hospital-scoped Module 1 export tokens.
- Separate service-token signing keys for internal hops.
- Aggregate weights, ids, counts, metrics, and provenance are sent to the
  federated server; raw patient rows are not part of the client result.
- Module 7 receives count-only validation summaries.
- `privacy.py` supports optional update clipping and Gaussian noise via
  `FEDHEAL_UPDATE_CLIP_NORM` and `FEDHEAL_UPDATE_NOISE_MULTIPLIER`.

The clipping/noise feature is disabled by default and explicitly states that
it does **not** provide an epsilon-differential-privacy guarantee because
there is no privacy accountant. Secure aggregation is not implemented.
Flower TLS is optional in the adapter, while the local Compose path uses
plaintext by default. There is no verified cross-machine or production
network deployment in this checkout.
