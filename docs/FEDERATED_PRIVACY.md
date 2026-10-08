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
| Authentication / authorization of the update path | Implemented (per-hop service keys; scoped export tokens) |
| Audit logging of registration / validation / promotion / rollback | Implemented |
| Update validation | Partial: registry integrity + gate; no per-update anomaly screening |
| Transport encryption (TLS) | **Not implemented.** Flower gRPC is plaintext; run on a trusted network only |
| Update clipping | **Not implemented** |
| Differential privacy | **Not implemented** |
| Secure aggregation | **Not implemented** (the aggregation server sees each hospital's individual update) |

The federation server therefore must be trusted not to attempt reconstruction from individual updates.
This is a limitation of the MVP, not a claim of formal privacy.

## Continual learning

New data never changes production by itself:
eligible data → local training → FedAvg → CANDIDATE → validation gate → explicit super_admin promotion
→ DEPLOYED (previous version kept for rollback). Eligibility today: only validated records (flagged
records are excluded) and only hospital-sourced labels (placeholder labels make the `data_quality`
check fail). Clinician review decisions are **never** used as training labels.
