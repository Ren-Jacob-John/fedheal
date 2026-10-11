# MVP scope — status reviewed 2026-10-11 (target: 2026-10-10)

Implemented: platform → hospital → hospital_admin → doctor onboarding (public registration closed);
hospital-isolated cases, structured medical history, case-linked validated vitals, scan upload
(store + link only); clinician review; append-only, hospital-scoped analysis history with optional
same-case review linkage; `POST /cases/{id}/analyze` over the **promoted federated model**
(demo fallback only behind an explicit flag, labelled NON-CLINICAL); two-hospital FedAvg through the real
services; model registry with weight-hash verification, validation gate, explicit promotion and rollback;
scoped service-to-service tokens; Firestore data layer for Modules 1 and 7 (migrated from Postgres/Supabase, see docs/FIRESTORE_MIGRATION.md); doctor dashboard workflow.

Explicitly **not** done: image/lab analysis (no validated imaging model — scans are stored only);
training or inference with optional temperature, SpO2, respiratory rate (stored/validated, but no
source-backed v2 transform or validated trained model); secure aggregation; verified browser-level
(Playwright) E2E; a verified Docker/Compose run;
a run against real Firestore or the Firestore emulator; demo recording and screenshots.
The scan-analysis HTTP route exists but intentionally returns an unavailable
status-only contract, not image analysis.

Retraining is only partially automated: the count-threshold queue is off by
default and the hospital-scoped runner can poll/claim requests. The networked
Flower server can register a provenance-complete final aggregate as a Module 7
CANDIDATE; an incomplete or mismatched provenance set blocks registration and
request completion. This queue-triggered networked path passed across separate
service processes with throwaway stores; Docker-container execution remains
unverified. The dashboard shows queued requests and registered
candidates; no path auto-validates or auto-promotes a model. A cron-based
scheduler is not implemented.

Persistence is Firestore document storage. Existing documents default newly
added optional vital fields to null. There is no Alembic migration layer in
this repository; do not add an unrelated SQL migration stack.

Analysis history stores model/artifact metadata, input identifiers, missing-input
identifiers, and bounded structured output only; raw clinical free text and
clinician notes are not copied into it. Module 8 persists with the clinician's
existing JWT. Review decisions remain excluded from training labels.
The optional clinician-confirmed training-label provenance mechanism is not
implemented.
