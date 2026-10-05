# Compliance write-up (HIPAA / GDPR / IRB) — DRAFT

**This is documentation of what a real deployment would require. It is not
an approval, a certification or legal advice, and FedHeal is not currently
cleared to process real patient data.** Items marked **Operator** need a
decision or evidence from the deploying organisation; the code cannot supply them.

## 1. Scope and status

FedHeal is a research prototype. The Oct 12 demo runs on public data (UCI
Cleveland heart disease) and synthetic data only. Module 8's output is a
review packet for a clinician; it is not a diagnosis and requires human
sign-off. Imaging, genomic and CBC specialists are stubs (see DEVELOPMENT_PLAN §4).

## 2. What the code already does, by control

| Concern | Implemented control | Where |
|---|---|---|
| Data minimisation | Stored record has no name, DOB, address or free text; `patient_ref` is a hospital-chosen pseudonym | `module1-auth/models.py`, DATA_CONTRACT.md |
| De-identification screening | Forbidden-field check rejects identifier-like columns before storage | `module2-validation/rules.py` |
| Tenant isolation | Hospital-scoped JWT; cross-tenant access returns 403/404 and is audited | SECURITY.md |
| Access control | Role-based endpoint table; service-to-service keys per edge | SECURITY.md |
| Audit trail | Allow-listed JSON events, no values, no credentials | SECURITY.md, `audit.py` |
| Fail-closed configuration | Unset `FEDHEAL_ENV` means production; weak/missing secrets refuse to start | `config.py` |
| Raw data stays local | Only model weights are exchanged in federated training | Module 3 |
| Honest model labelling | `is_stub`, `is_fallback`, `training_status`, `federated` shown end to end | DATA_CONTRACT.md |

## 3. Gaps a real deployment must close

1. **TLS.** The Flower gRPC channel is plaintext; HTTP services need TLS at a
   proxy. (Cut-listed in DEVELOPMENT_PLAN §4.)
2. **Token revocation and login throttling.** Rate limiting is in-memory per
   process; there is no per-token revocation list; self-registration is open.
3. **Static service keys.** M2→M7 and M3→M7 keys carry no tenant scope.
4. **Secrets management.** Environment variables only; no vault/rotation.
5. **No retention or deletion workflow.** There is no endpoint or job that
   deletes a patient's records on request (GDPR Art. 17) or expires them.
6. **No data export for a data subject** (Art. 15/20).
7. **Encryption at rest** depends entirely on the database host (Postgres
   volume / managed service); the application does not encrypt columns.
8. **Federated weights can leak.** Model updates can be inverted or used for
   membership inference. There is no differential privacy or secure aggregation.
9. **No bias or subgroup validation.** The only evaluation is on 3 real features
   of one public dataset (SPRINT-A-REPORT.md); no performance claim is valid for
   any real population.

## 4. HIPAA (US) — mapping

| Safeguard | Status |
|---|---|
| Access control, audit controls, person/entity authentication, transmission security (§164.312) | Partial: see §2 and gaps 1–4 |
| Administrative safeguards (risk analysis, workforce training, contingency plan) | **Operator** |
| Business Associate Agreements with every hosting/cloud vendor | **Operator** |
| De-identification standard (Safe Harbor 18 identifiers or Expert Determination) | The screen is a heuristic guard, not a determination. **Operator** must choose and document a method |
| Minimum necessary | Schema is minimal by construction (§2) |
| Breach notification process | **Operator** |

## 5. GDPR (EU) — mapping

| Requirement | Status |
|---|---|
| Lawful basis and Art. 9 condition for health data (e.g. explicit consent, research) | **Operator** |
| Pseudonymised data is still personal data | Treat all stored records as in scope |
| DPIA (Art. 35) | Required before real use. **Operator** |
| Controller/processor roles per hospital; Art. 28 contracts | **Operator** |
| Data subject rights (access, erasure, portability) | Not implemented (gaps 5–6) |
| International transfers | Depends on hosting region. **Operator** |
| Art. 22 automated decisions | Mitigated by design: output is advisory and needs clinician sign-off |

## 6. IRB / ethics

Real approval, per-hospital data-governance agreements and any use of
MIMIC-III/IV (Physionet credentialing and a data-use agreement) are outside
the team's control and are not claimed. Before any study: a protocol,
inclusion criteria, an informed-consent or waiver decision, and an approved
data-use agreement per site. **Operator**.

## 7. Claims the demo must not make

- That the system is HIPAA/GDPR compliant, certified or approved.
- That the federated model is deployed in Module 8 (it is a labelled demo fallback).
- That accuracy figures generalise beyond the UCI seed (SPRINT-A-REPORT.md).
- That imaging, genomic or CBC outputs are real model results.
