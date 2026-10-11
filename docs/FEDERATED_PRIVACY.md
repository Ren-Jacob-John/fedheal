# Federated privacy — what exists and what does not

Two different things are protected, and they are not the same:

**1. Raw-data privacy (implemented).** Patient data stays in the hospital's own records.
- Training reads a hospital's data only through Module 1 with a token scoped to that one hospital
  (`/vitals/export`, `service_auth.py`).
- A hospital client returns only weight arrays, an example count and its id
  (`test_federation_registry.py::test_client_fit_returns_only_weights_a_count_and_an_id`).
- The model registry accepts only ids, hashes, short strings and aggregate numbers and refuses
  payloads containing patient/record-like fields or oversized lists/strings
  (`module7-admin/model_registry.py::assert_no_raw_data`; 7 parametrised refusal tests).
- The integration test checks the stored registry row contains no patient references or vitals values.
- Audit events carry ids only, never clinical content (tested).

**2. Federated-update privacy (NOT implemented).** Weight updates can leak information about the
training data (membership inference, gradient inversion). Current state, stated in every candidate's
`training_metadata`:

| Mechanism | State |
|---|---|
| Authentication / authorization of the update path | Implemented: short-lived signed service tokens with a separate key per hop (caller, endpoint family, hospital scope, expiry). Module 2 → 7 flag reports are hospital-scoped; Module 3 → 7 and Module 8 → 7 are platform-level (aggregates / weights only) |
| Audit logging of registration / validation / promotion / rollback | Implemented |
| Update validation | Partial: the registry re-derives the weight hash itself and refuses a mismatch; refuses patient-like fields and oversized values; validation gate before promotion. No per-update anomaly screening |
| Transport encryption (TLS) | Flower server/client support server-authenticated TLS via `server.py --ca-cert --server-cert --server-key` and `client_runner.py --secure [--root-certificates ...]`. Compose remains plaintext unless operators provide/configure certificates. Mutual TLS is not supported by the current Flower 1.11.1 `start_client` adapter; use a mutually authenticated network proxy or upgrade the transport before exposing it beyond a trusted network. |
| Update clipping | Optional client-side global L2 clipping of the local model delta via `FEDHEAL_UPDATE_CLIP_NORM`; default off. |
| Gaussian update noise | Optional client-side Gaussian noise, scaled to the clipping bound via `FEDHEAL_UPDATE_NOISE_MULTIPLIER`; default off. It is an experimental perturbation, **not an epsilon-DP guarantee**: no sampling/composition accountant exists and no epsilon is computed or reported. |
| Secure aggregation | **Not implemented** (the aggregation server sees each hospital's individual update) |

The federation server therefore must be trusted not to attempt reconstruction from individual updates.
This is a limitation of the MVP, not a claim of formal privacy.

The networking tests currently exercise localhost/plaintext Flower only. No
two-hospital TLS or mTLS run was executed. SecAgg+ feasibility remains a
separate protocol integration: the current FedAvg strategy receives
individual updates, and no secure-aggregation round protocol or dropout
recovery has been integrated/tested. The installed Flower 1.11.1
compatibility `flwr.server.strategy` surface exposes no SecAgg strategy;
feasibility therefore requires evaluating a supported Flower workflow or
separate secure-aggregation protocol, including key setup and dropout
recovery, then testing it with at least two independent hospital clients.
Do not claim that clipping, noise, TLS, or the hospital-scoped request queue
prevents update leakage.

## Continual learning

No model changes production by itself. The candidate lifecycle is CANDIDATE →
validation gate → explicit super_admin promotion → DEPLOYED (previous version
kept for rollback). The networked Flower server can register a final-round
aggregate as a CANDIDATE only when every participant's hospital id, claimed
request id, validated training count, and evaluation provenance match. M7
links the candidate to the corresponding requests; missing or inconsistent
provenance skips registration and prevents queue completion. The
queue-triggered Flower flow passed across separate service processes with
throwaway local stores; Docker-container execution remains unverified.
Centralized `simulate_real.py` pooling is refused. Clinician review
decisions remain **excluded** from training labels; the opt-in
clinician-confirmed label provenance flow is not implemented.

Module 7's retraining queue is count-only and disabled unless
`FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS` is positive. Each hospital runner reports
its eligible count using a separately minted hospital-scoped service token.
Module 7 establishes the initial count as a baseline, then creates at most one
pending/claimed request when at least N new eligible records have accumulated
since the last completed request. Completion advances that hospital's baseline;
failed/flagged/placeholder-labeled rows are not used by watch mode. Queue
requests and audit records contain counts, tenant ids, and request ids only.
Watch mode excludes failed, flagged, and placeholder-labeled rows. Optional
clinician-confirmed labels remain unavailable (not merely disabled): there
is no provenance-enabled implementation yet. Candidate validation and
explicit promotion remain separate and unchanged.
