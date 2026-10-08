# FedHeal — Federated Learning Healthcare AI

Developed by a team of 4 members.

> **Status: research / MVP prototype. Nothing in this repository is clinically validated.**
> FedHeal is clinical *decision support*. Every result must be reviewed by a doctor. See
> [What works today and what is planned](#what-works-today-and-what-is-planned) before relying on any feature.

---

## 1. What FedHeal is

FedHeal is a healthcare AI platform that helps a doctor understand why a patient was admitted and what to
consider next. For each patient, the doctor provides:

- **vitals**,
- **medical history**,
- **the condition / problem the patient is admitted for**,
- **scans** done on the patient.

The AI analyses this information and returns a **result with the reasoning behind it**, for the doctor to
accept, override, or send back for more data.

The AI is trained with **federated learning**: every hospital trains on its own data, and only learned model
weights are combined. **One hospital's patient data is never shared with another hospital.** After the first
training, the shared model keeps improving through further federated rounds, and a new version only goes
live after it passes a validation gate.

### Who uses it

| User | Created by | What they can do |
|---|---|---|
| **Platform operator** (`super_admin`) | the developers | create hospitals and their hospital users, see platform-level status, validate / promote / roll back models. **No access to patient-level data.** |
| **Hospital user** (`hospital_admin`) | the platform operator | create and deactivate the hospital's doctors. Manages people, not patients. |
| **Doctor** (`clinician`) | the hospital user | create patient cases, enter vitals / history / condition, upload scans, run AI analysis, review results. Sees only their own hospital's cases. |

There is **no public registration**. Accounts are created top-down: developers → hospital user → doctors.

### Data isolation rule

A hospital's data stays inside that hospital:

- The hospital a request belongs to is read from the signed login token, never from anything the client sends.
- A doctor asking for another hospital's case gets `403`, and the attempt is written to the audit log.
- Training reads a hospital's data only through a token scoped to that one hospital.
- Training clients send back **only** weights, an example count and a hospital id.
- The model registry refuses anything that looks like patient data.

---

## 2. How it works (end to end)

1. The developers create a **hospital** and its **hospital user**. The hospital user creates **doctors**.
2. A doctor logs in and creates a **patient case** (admission reason, current condition, symptoms).
3. The doctor adds **medical history**, **vitals** and **scans**. Vitals pass a 5-stage validation gate
   (de-identification screen → schema → plausibility ranges → cross-field consistency → outlier detection);
   only validated records can be used for training.
4. The doctor runs **AI analysis** on the case. The analysis uses the **currently promoted federated model**
   and returns a clinician review packet: the model result, which inputs drove it, which inputs were missing,
   and the model's version and status.
5. The doctor records a **review**: Accepted, Overridden, or Needs more data.
6. **Federated retraining.** Each hospital trains locally on its own validated data; only weights are
   averaged (FedAvg) into a new global model, which is registered as a **candidate**.
7. **Validation gate → promotion.** A candidate is checked against the gate. Only a `super_admin` can promote
   it. The previous version is kept so it can be **rolled back**.
8. Promoted models are what step 4 uses, so the system improves as more validated data arrives.

New data never changes the live model by itself. Doctor review decisions are **never** used as training labels.

---

## 3. What works today and what is planned

Legend: **Done** = code and tests exist · **Partial** = works with gaps · **Planned** = not built yet.
Nothing was run in Docker/Compose yet; "Done" does not mean clinically validated.

| Capability from the concept | Status | Notes |
|---|---|---|
| Two-level user creation (developers → hospital user → doctors), no public sign-up | **Done** | |
| Hospital data isolation | **Done** | enforced from the token; cross-hospital access refused and audited |
| Doctor enters condition, history, vitals | **Done** | cases, structured history, case-linked validated vitals |
| Doctor uploads scans | **Partial** | scans are **stored and linked to the case only**; no scan analysis |
| AI result for the patient | **Partial** | one runnable model (heart-risk on vitals), trained on small public data; not clinically useful yet |
| Reasoning behind the result | **Partial** | per-feature contributions and a list of missing inputs; history/symptoms are not yet model inputs |
| Suggested next steps / "solution" for the doctor | **Planned** | will come from a reviewable rule file with a source per rule, never invented, no drug dosing |
| Doctor review (accept / override / needs more data) | **Done** | |
| Federated training across hospitals (FedAvg) | **Done** | 2-hospital flow tested through the real services |
| Model registry, validation gate, promotion, rollback | **Done** | no automatic deployment |
| Model improves by itself over time | **Partial** | retraining is started manually; automatic (but still gated) triggering is **Planned** |
| Saved AI-analysis history per case | **Planned** | analyses are not persisted yet |
| Extra vitals (temperature, SpO2, respiratory rate) | **Planned** | |
| Imaging models (chest X-ray, retina, skin, CT) | **Planned** | stubs only; no validated models or weights in the repo |
| Federated-update privacy: TLS, clipping, differential privacy, secure aggregation | **Planned** | today the aggregation server sees each hospital's weight update, so it must run on a trusted network |
| Docker Compose run, browser E2E test | **Planned** | Compose file exists but has never been run |

Honest model status, recorded numbers, and gate thresholds: [`docs/MODEL_STATUS.md`](docs/MODEL_STATUS.md).
What is deliberately not done: [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md).
Privacy details: [`docs/FEDERATED_PRIVACY.md`](docs/FEDERATED_PRIVACY.md).

**Never claim:** accurate, clinically proven, hospital-ready, FDA approved, medically certified.

---

## 4. Architecture

Eight cooperating modules. Backend services use Python 3.12 / FastAPI, the dashboard is React (Vite), and
federated learning uses Flower.

```
Browser (M4 React) ──JWT──► M1 auth/cases/vitals :8001 ──service token──► M2 validation :8002
        │                         ▲
        │                         └── hospital-scoped service token ── M3 federated learning (Flower :8080)
        ├──JWT──► M7 admin / model registry :8005 ◄── candidates & round reports ── M3
        └──JWT──► M8 synthesis / analysis :8006 ── reads promoted model from M7
                         └─ uses M6 condition router ─► M5 model zoo
```

| # | Module | Purpose |
|---|---|---|
| 1 | `module1-auth/` | Login, hospitals, hospital users, doctors, cases, history, vitals, scans, reviews, audit |
| 2 | `module2-validation/` | 5-stage data validation gate |
| 3 | `module3-fedlearning/` | Local training and FedAvg (simulation and networked Flower server/client) |
| 4 | `module4-dashboard-react/` | Doctor, hospital-user and operator dashboard |
| 5 | `module5-modelzoo/` | Specialist-model interface, registry, router (most specialists are labelled stubs) |
| 6 | `module6-condition-router/` | Maps a condition to specialists and explainers (SHAP, Grad-CAM, knowledge graph) |
| 7 | `module7-admin/` | Platform oversight, training rounds, model registry, validation gate, promotion, rollback |
| 8 | `module8-synthesis/` | Builds the clinician review packet and runs `POST /cases/{id}/analyze` |

Ports: M1 8001 · M2 8002 · M7 8005 · M8 8006 · Flower 8080 · dashboard 5173.

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/API.md`](docs/API.md),
[`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md), [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md).

---

## 5. Safety rules built into the design

- Every analysis is `requires_clinician_review`. The system never states a confirmed diagnosis.
- It does not output a treatment plan, medication or dose.
- Every result shows the model version, status (`DEPLOYED`, or `FALLBACK` for the non-clinical demo model) and
  whether it is federated.
- Missing inputs are reported as missing. Nothing is silently filled in.
- With no promoted model, analysis answers `MODEL_UNAVAILABLE`. The demo fallback only runs if
  `FEDHEAL_ALLOW_DEMO_MODEL=true`, and is labelled **NON-CLINICAL DEMO MODEL**.
- A scan without a validated imaging model is reported as `UPLOADED — analysis UNAVAILABLE`.
- Services refuse to start in production mode with missing or placeholder secrets.

---

## 6. Running FedHeal locally

### Prerequisites

- Python 3.11+ and Node.js 18+
- No GPU is needed for the core demo. The database falls back to SQLite when no URL is set.

### Environment

Copy `deploy/compose.env.example` to `.env` and fill the secrets
(`python -c "import secrets; print(secrets.token_urlsafe(48))"`). These values must match across services:

| Variable | Shared by | Purpose |
|---|---|---|
| `FEDHEAL_ENV` | all services | `development` for local work. **Unset = production**, which refuses weak config |
| `FEDMED_JWT_SECRET` | M1, M7, M8 | M7 and M8 only verify tokens M1 issues |
| `FEDHEAL_SVC_SIGNING_KEY_M3_M1` | M1; M3 operator | hospital-scoped training-data token |
| `FEDHEAL_SVC_SIGNING_KEY_M1_M2` | M1, M2 | upload → validation token |
| `FEDHEAL_SVC_SIGNING_KEY_M2_M7` | M2, M7 | validation flag reports |
| `FEDHEAL_SVC_SIGNING_KEY_M3_M7` | M3, M7 | round reports and model candidates |
| `FEDHEAL_SVC_SIGNING_KEY_M8_M7` | M8, M7 | reading the promoted model |
| `FEDHEAL_DASHBOARD_ORIGIN` | M1, M7, M8 | must equal the dashboard origin (CORS) |
| `FEDHEAL_ADMIN_API_URL` | M3, M8 | address of Module 7 |
| `FEDHEAL_ALLOW_DEMO_MODEL` | M8 | leave **unset** to see the promoted model answer |

### Start the stack

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r module1-auth/requirements.txt -r module2-validation/requirements.txt \
  -r module3-fedlearning/requirements.txt -r module6-condition-router/requirements.txt \
  -r module7-admin/requirements.txt -r module8-synthesis/requirements.txt

export FEDHEAL_ENV=development FEDHEAL_DATABASE_URL=sqlite:////tmp/fedheal.db \
  FEDHEAL_DASHBOARD_ORIGIN=http://localhost:5173 \
  FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD=demo-bootstrap-password-1

(cd module1-auth && alembic upgrade head && python create_super_admin.py --email admin@demo.local)
(cd module1-auth && uvicorn main:app --port 8001) &
(cd module2-validation && uvicorn main:app --port 8002) &
(cd module7-admin && uvicorn main:app --port 8005) &
(cd module8-synthesis && uvicorn main:app --port 8006) &
(cd module4-dashboard-react && npm ci && npm run dev) &
```

### Demo walkthrough

The full step-by-step flow is in [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md). In short:

1. Log in as the platform operator and create two hospitals and a hospital user for each.
2. As a hospital user, create a doctor.
3. As the doctor, create a case, then add vitals and history (and optionally a scan).
4. Run AI analysis. Before any model is promoted, the correct answer is `MODEL_UNAVAILABLE`.
5. Seed two hospitals with public heart data and run federated training
   (`seed_uci_heart.py --hospitals 2`, then `simulate_real.py`). A **candidate** model is registered.
6. Validate the candidate. With the default gate the recorded public-data run is **rejected**, which is the
   honest result. A relaxed test policy exists only to demonstrate the wiring.
7. Promote a passing model, run analysis again, then record a doctor review.
8. Try another hospital's case id as a doctor from a different hospital: you get `403`.
9. Roll back to the previous model version.

### Tests

```bash
# per module, for example:
(cd module1-auth && pytest)
pytest tests/        # cross-module and integration tests
```

See [`docs/TESTING.md`](docs/TESTING.md). Known gap: Module 3 tests are not in CI yet.

### Troubleshooting

- **401 between services:** a shared secret or signing key does not match. Check the table above.
- **CORS errors:** `FEDHEAL_DASHBOARD_ORIGIN` must exactly match the dashboard URL, including the port.
- **403 on training export:** the hospital token belongs to a different hospital.
- **Imaging/genomic specialists show `[STUB]`:** expected without torch, weights and data.
- **Security model and required configuration:** [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 7. Technology

| Layer | Used |
|---|---|
| Federated learning | Flower (FedAvg), scikit-learn (SGD logistic regression for the vitals model) |
| Validation | rules plus Isolation Forest outlier detection |
| Model zoo (scaffolded) | XGBoost, TabPFN, LightGBM, PyTorch imaging and segmentation models. Most are stubs until weights and data exist |
| Explainability | linear feature contributions (promoted model), SHAP (demo model), Grad-CAM and knowledge graph (scaffolded) |
| APIs | FastAPI, Pydantic, SQLAlchemy, Alembic (Modules 1 and 7) |
| Auth | bcrypt password hashing, JWT for users, scoped signed tokens between services |
| Database | PostgreSQL in Compose, SQLite for local development |
| Frontend | React 18 + Vite |

---

## 8. Roadmap

Planned in this order (details and acceptance rules in the project docs):

1. Suggested next-step considerations from a reviewable, sourced rule file (no dosing, no invented advice).
2. Use history, symptoms, admission condition and extra vitals as model inputs. Missing values stay missing.
3. Save every AI analysis per case (append-only, hospital-scoped) and link reviews to it.
4. Automatic retraining trigger per hospital, with candidates still gated and promotion still manual.
5. Docker Compose and browser end-to-end run, Module 3 in CI.
6. Scan analysis through a validated imaging model, only when real weights and a licensed dataset exist.
7. Federated-update privacy: TLS, update clipping, differential privacy, evaluate secure aggregation.

---

## 9. Why this matters

Hospitals cannot pool raw patient records because of privacy law and data-governance policy, and a model
trained at one hospital often performs poorly at another. FedHeal keeps patient data where it was collected and
shares only learned weights, so small and rural hospitals can benefit from a model shaped by many hospitals
without handing over their patients' records. The validation gate, the human-review requirement and the
explicit model status exist because a silently wrong or unexplained result is dangerous in medicine.
