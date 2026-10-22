# Status and roadmap

## Current status from source

| Area | Status | Evidence/limitation |
|---|---|---|
| User auth and role model | Done | Module 1 issues user JWTs/cookies and enforces roles. |
| Hospital isolation | Done in application path | JWT/service-token hospital scopes and Firestore deny-all client rules; no production penetration test verified. |
| Vitals validation | Done | Rule pipeline, limits, and anomaly flagging are implemented. |
| Firestore/local persistence | Implemented | Firestore and local/memory adapters exist; real Firestore runtime not verified here. |
| Federated synthetic/networked training | Implemented | Flower server/client and FedAvg code exist; cross-machine deployment not verified. |
| Model registry/gate/promotion/rollback | Implemented | Module 7 separates lifecycle actions; no automatic promotion. |
| Vitals inference | Partial | Promoted model path exists; UCI fallback is optional and non-clinical. |
| Case analysis/review history | Implemented | Module 8 builds structured packets and Module 1 stores append-only analysis/review records. |
| Imaging analysis | Stub/unavailable | Scan endpoint returns `analysis_unavailable`; no validated imaging model serves bytes. |
| Other specialist models | Partial/stub | Registry and contracts exist; many models require unavailable dependencies/weights/data. |
| Browser dashboard | Implemented | React build passes; browser E2E is not verified and no spec is present. |
| Tests in this checkout | Missing | No Python or Playwright test files are present; pytest invocations report an empty collection. |

## Known technical debt

- Duplicate canonical configuration/service-auth/upload-limit files across
  service directories can drift.
- Legacy Alembic/SQLite migration artifacts remain beside the active docstore
  implementation.
- Login rate limiting is process-local.
- No scheduler starts retraining; queue polling is explicit.
- Service secrets are manually coordinated environment values.
- No formal DP accountant, secure aggregation, or default Flower TLS.
- Module 5/6 specialist availability depends on optional packages, weights, and
  input modalities.
- No current automated regression suite is present in the checkout.

## Prioritized remaining work

1. Restore or add executable tests for service auth, tenant isolation, registry
   lifecycle, validation, and case workflows.
2. Exercise Compose and real Firestore/emulator paths with non-secret test
   configuration.
3. Define and verify a production transport/security design: TLS, secret
   management, update protection, secure aggregation, and a formal privacy
   analysis.
4. Replace or clearly isolate demo/fallback models with validated, provenance-
   tracked models and independent evaluation.
5. Implement validated imaging and non-vitals specialists only when licensed
   data, weights, and safe explainers exist.
6. Add a distributed rate limiter, scheduler/worker operational model, and
   observability for failures and queue lifecycle.
7. Add browser E2E and accessibility/error-boundary coverage.

## Documentation discrepancies

- Existing module documentation describes historical tests that are absent from
  this checkout.
- Existing Module 4 prose contains an obsolete statement that synthesis
  hand-enters vitals; current `SynthesisView.jsx` selects a stored record and
  calls `/synthesize/record`.
- Existing module docs describe some paths as fully verified, but this task
  could not reproduce those results without the missing test files/dependencies.
