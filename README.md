# FedHeal — Federated Learning Healthcare AI

Starter codebase for the first development milestone, split across a 4-person team
following the build order from the project proposal:

1. Auth + multi-tenancy (get hospital logins working)
2. Data ingestion + validation (structured-data track)
3. Local training (XGBoost/logistic regression) + Flower federated loop across simulated hospitals
4. Dashboard wired to show login + training/round status

## Abstract

Modern clinical AI faces a structural tension: models generalize best when
trained on large, diverse patient populations, but privacy regulation
(HIPAA, GDPR) and institutional data-governance policies prevent hospitals
from pooling raw patient records on a central server. FedHeal addresses
this by combining **federated learning** with a **modular, multi-specialist
diagnostic architecture**, allowing multiple hospitals to collaboratively
train a shared model without any patient-level data ever leaving its
institution of origin.

The system is organized as eight cooperating modules. A multi-tenant
authentication layer issues hospital-scoped tokens that every downstream
service trusts exclusively. A five-stage validation gate
(de-identification screening, schema checks, plausibility ranges,
cross-field consistency, and batch-level outlier detection) filters
uploaded data before it can influence the shared model. Local training
happens independently at each hospital; only learned model weights,
aggregated centrally via Federated Averaging (FedAvg), are ever exchanged.
Rather than a single model attempting every diagnostic task, a **model
zoo** of specialist architectures — spanning tabular (XGBoost, TabPFN),
imaging (CNN-based classifiers, segmentation networks, and integration
groundwork for foundation models including RadFM, BiomedParse, and
SegVol), and genomic/histopathology data — sits behind a metadata-driven
router that dispatches each case only to the specialist built for it,
explicitly avoiding the failure mode of a confident answer from a
mismatched model. A condition router expands a named disease into its
full set of required specialists and explanation methods (SHAP, Grad-CAM,
knowledge-graph reasoning), and a synthesis layer aggregates these
outputs into a structured review packet for clinician oversight —
deliberately stopping short of automated diagnosis or treatment
recommendation, and requiring human sign-off by design.

FedHeal demonstrates that privacy-preserving collaboration, data-quality
enforcement, and explainable, human-supervised multi-modal diagnosis can
coexist within one coherent, incrementally extensible architecture — a
template applicable beyond healthcare to any multi-party setting where
data cannot be centralized but collaborative intelligence is still
valuable.

## Problem Statement

Modern healthcare AI needs large, diverse patient datasets to build models
that generalize well — a model trained on one hospital's patients often
performs poorly on another hospital's population. The obvious fix,
pooling every hospital's raw patient records onto one central server, is
blocked in practice for good reasons:

- **Privacy & legal risk** — regulations such as HIPAA/GDPR and hospital
  data-governance policies generally forbid moving identifiable patient
  data outside the institution that collected it.
- **Data silos** — each hospital's data stays locked inside its own
  systems, so no single institution (especially a small or rural one) has
  enough data on its own to train an accurate, generalizable model.
- **Data quality is uneven** — different hospitals use different
  equipment, units, and data-entry practices, so raw uploads can contain
  unit mismatches, out-of-range values, or outliers that silently corrupt
  a shared model if they aren't caught before training.
- **One-size-fits-all models don't work in medicine** — a chest X-ray
  needs a different model than a table of vital signs, which needs a
  different model than a genomic panel, so a real clinical AI platform
  has to intelligently route each case to the right specialist model(s).

**In short: how do you let many hospitals collaboratively train an
accurate, shared diagnostic AI model without any hospital's patient data
ever leaving its own servers?**

## Solution

FedHeal is a **federated learning platform for healthcare**, built as
eight cooperating modules that together implement the full pipeline from
hospital login to a continuously improving shared model:

1. **Authentication & multi-tenancy** (`module1-auth/`) — every hospital
   gets its own isolated login; a signed JWT (not a client-supplied value)
   is the only thing any other module trusts to know which hospital a
   request belongs to.
2. **Data ingestion & validation** (`module2-validation/`) — a five-stage
   gate (de-identification screen, schema validation, plausibility-range
   checks, cross-field consistency checks, batch-level outlier detection)
   that a hospital's uploaded data must pass before it can influence the
   shared model.
3. **Local training + federated aggregation** (`module3-fedlearning/`) —
   each hospital trains a model on only its own local data; only the
   learned model weights (never raw patient records) are sent to a
   central process that averages them (**Federated Averaging / FedAvg**)
   into one improved global model, which is then sent back out for
   another round.
4. **Hospital dashboard** (`module4-dashboard-react/`) — the interface a
   clinician or hospital admin uses to log in, upload vitals, and see
   their hospital's status and validated-record count, plus a spatial
   "federation map" — every hospital as a node in orbit around the shared
   model, live status, and an architecture view of all eight modules — see
   its own README for the design rationale. The original plain-HTML
   `module4-dashboard/` has been removed: it was confirmed fully
   superseded (same job, same API contracts against Module 1 and Module 7
   — see `module4-dashboard-react/README.md`'s "What's role-gated, and
   why" table), and the project consolidates on one dashboard going
   forward rather than maintaining both long-term.
5. **Model zoo & task router** (`module5-modelzoo/`) — a library of
   specialist models (one per data modality: vitals, chest X-ray, retina,
   skin, segmentation, genomic variants, plus four SOTA foundation-model
   additions — RadFM, BiomedParse, SegVol, OmiCLIP — see
   `docs/foundation-models-status.md` for what's real vs. blocked among
   those) behind one common interface, with a router that sends each case
   to the specialist actually built for it. As of this modernization pass,
   the legacy DenseNet201/ResNet50/EfficientNet imaging specialists and
   the custom U-Net segmentation model are joined by current-tier
   upgrades — BiomedCLIP embeddings + a fine-tuned CNN+ViT-hybrid head for
   imaging, nnU-Net for segmentation, Evo 2 for genomic variant-effect
   prediction — registered as the primary path with the legacy models
   kept as the auto-degrade fallback tier; see
   `docs/model-algorithm-catalog.md`'s "What's actually outdated" table
   and this module's own README/EXPLANATION for exactly what changed.
   **The specialist + router + fusion architecture itself is unchanged** —
   every new model, including the CNN+ViT hybrid, plugs in as one more
   specialist behind the same `SpecialistModel` interface, never a
   replacement for it.
6. **Condition router** (`module6-condition-router/`) — given a disease
   name (e.g. "breast cancer", "leukemia"), automatically pulls in every
   specialist model and every explanation method (SHAP, Grad-CAM,
   knowledge-graph reasoning) that condition requires, instead of a human
   having to wire that combination together by hand each time.
7. **Admin / platform module** (`module7-admin/`) — the operator's
   single view across the whole platform: which hospitals are active, is
   the shared model actually improving round over round, and how much
   data is being flagged for quality issues.
8. **Synthesis / review-packet layer** (`module8-synthesis/`) — aggregates
   Module 5/6's raw specialist findings into one structured report for a
   clinician to review. Deliberately does not emit a diagnosis, treatment
   plan, or cross-modality confidence score it can't justify — every
   report is hardcoded `requires_clinician_review = True` and every
   number in it traces back to a real specialist's confidence. See its
   README for the full rationale.

## Importance to Society

- **Better medicine for everyone, especially under-resourced hospitals.**
  A small or rural hospital that could never collect enough data on its
  own to train a reliable model benefits from a global model shaped by
  every participating hospital's experience, without ever handing its
  patients' records to anyone.
- **Genuine patient privacy protection.** Because only model weights
  (numbers), never patient records, ever leave a hospital, federated
  learning removes the single biggest risk of centralized medical
  datasets: a data breach exposing millions of patient records at once.
- **Regulatory-friendly by design.** Keeping data at its source
  institution aligns naturally with data-protection laws like HIPAA and
  GDPR, instead of requiring hospitals to fight their own compliance
  policies to participate in AI research.
- **Safer AI in a life-critical domain.** The validation gate, the
  "wrong specialist = confidently wrong answer" philosophy behind the
  routers, and the explainability layer (SHAP, Grad-CAM, knowledge-graph
  reasoning) all exist because a diagnostic system that is wrong silently
  or unexplainably is dangerous in medicine in a way it isn't in most
  other software.
- **A template for cross-institution collaboration** more broadly — the
  same architecture (isolate data, share only learned updates, validate
  before training, explain every prediction) generalizes to any
  privacy-sensitive, multi-party domain, not just hospitals.

## Working Principle

The system follows this end-to-end flow:

1. A hospital user logs in through the **dashboard**; Module 1 verifies
   their password and issues a JWT carrying their hospital ID and role —
   every later step trusts *only* that token, never a client-supplied
   hospital ID.
2. The hospital uploads a batch of vitals records. Module 1 forwards them
   to **Module 2**, which runs them through five checks in order
   (de-identification → schema → plausibility ranges → cross-field
   consistency → batch-level isolation-forest outlier detection) and
   returns each record as `passed`, `flagged`, or `rejected`. Only
   `passed` (and reviewed `flagged`) records are stored against that
   hospital.
3. When a federated training round starts, **Module 3** asks each
   hospital's local `HospitalClient` to train on only its own validated
   data, starting from the current shared model's weights. Each client
   returns its *updated weights* — never the underlying patient data.
4. A central aggregator averages all the hospitals' updated weights,
   weighted by how much data each hospital trained on (**FedAvg**),
   producing one improved global model. This repeats for a fixed number
   of rounds, and the result is evaluated on a shared holdout set no
   single hospital trained or tested on — the fair test of whether
   federation actually helped versus each hospital training alone.
5. For image- or condition-specific cases, **Module 5**'s router picks
   the specialist model built for that data's modality, and **Module 6**'s
   condition router expands a named disease into the full set of
   specialist models *and* explanation methods it requires, rather than
   guessing.
6. **Module 7** ties it together for a platform operator: hospital
   status, round-by-round accuracy history, and rolled-up (never
   patient-level) data-quality flags, all in one view.

## Algorithms & Frameworks Used

| Layer | Algorithm / Model | Framework / Library |
|---|---|---|
| Federated coordination | **Federated Averaging (FedAvg)** across a non-IID (Dirichlet-partitioned) simulation of hospitals | [Flower](https://flower.dev/) (`server.py` reference implementation), scikit-learn |
| Local/global model (tabular vitals) | Logistic regression (`SGDClassifier`) — chosen so weights are a simple flat array, easy to average correctly | scikit-learn |
| Structured/tabular specialist (current tier) | TabPFN v2 in-context tabular foundation model | `tabpfn` |
| Structured/tabular specialist (fallback) | Gradient-boosted trees | XGBoost |
| CBC / blood-count specialist (leukemia) | Gradient-boosted trees | LightGBM |
| Genomic/expression classifier (breast cancer risk, leukemia subtyping) | Random Forest | scikit-learn |
| Genomic variant-effect (BRCA1/2, cytogenetics) | Evo 2 (zero-shot log-likelihood-ratio scoring) | `evo2` |
| Histopathology (whole-slide breast tissue, current tier) | UNI2-h patch embeddings + CLAM-style gated-attention MIL | PyTorch / `timm` |
| Histopathology (fallback) | Attention-based MIL | PyTorch |
| Chest X-ray / retina / skin (current tier) | BiomedCLIP embeddings + fine-tuned CNN+ViT-hybrid head | `open_clip_torch` / PyTorch |
| Chest X-ray / retina / skin (fallback) | DenseNet201 / ResNet50 / EfficientNet-B0 (ImageNet transfer learning) | PyTorch / torchvision |
| Pixel-level segmentation (current tier) | nnU-Net v2 (hospital-trained model folder) | `nnunetv2` |
| Pixel-level segmentation (fallback) | Custom U-Net | PyTorch |
| Foundation-model additions (RadFM, BiomedParse, SegVol, OmiCLIP) | Radiology VQA, text-prompted segmentation, volumetric CT, pathology/omics alignment — see `docs/foundation-models-status.md` for what's runnable vs. stubbed | Mixed (cloned repos, `transformers`, HF Hub) |
| Batch-level anomaly detection | Isolation Forest | scikit-learn |
| Explainability — tabular/tree models | SHAP (feature attribution) | SHAP |
| Explainability — imaging models | Grad-CAM (pixel-level attribution) | PyTorch |
| Explainability — clinical reasoning | Rule-based knowledge-graph reasoner (ICD-10-style codes, plain-language reasoning, suggested next steps) | Custom |
| Clinician review packet | Structured synthesis of Module 5/6 findings (no diagnosis, `requires_clinician_review` hardcoded) | Custom (`module8-synthesis/`) |
| API services | REST APIs for auth, validation, admin | FastAPI, Pydantic, SQLAlchemy |
| Auth & security | Password hashing, signed tokens | bcrypt, JWT |
| Data storage | Relational database | PostgreSQL/Supabase (falls back to SQLite for local dev) |
| Frontend | Hospital + operator dashboard (federation map, vitals upload, super-admin views) | React + Vite (`module4-dashboard-react/`, wired to Module 1 + Module 7) |

See `docs/model-algorithm-catalog.md` for the full catalog of model
families relevant to future disease specialists (imaging, tabular/EHR,
genomic/omics, clinical NLP, time-series, survival analysis, multi-modal
fusion, and additional explainability/reasoning methods).

## Expected Outcome

- A working, end-to-end federated learning pipeline in which multiple
  simulated (and, via `simulate_real.py`, real-uploaded) hospitals train
  a shared diagnostic model **without any hospital's raw patient data
  leaving that hospital**.
- A measurable, honest comparison — reported after every run — between
  what each hospital's model could achieve training *alone* versus what
  the *federated* global model achieves on a shared holdout set, directly
  demonstrating federated learning's core value proposition (better
  generalization through collaboration, without pooling data).
- A validated, quality-gated data-ingestion pipeline that prevents
  malformed or implausible hospital data from silently degrading the
  shared model.
- A multi-modal diagnostic platform that automatically routes any case —
  by data type (Module 5) or by named disease (Module 6) — to the correct
  specialist model(s) and produces a human-readable explanation
  (SHAP / Grad-CAM / knowledge-graph reasoning) alongside every
  prediction, rather than an unexplained black-box output.
- A platform-operator view (Module 7) showing, at a glance, whether the
  shared model is actually improving round over round and how healthy
  each hospital's data quality is.
- A foundation designed to graduate from this prototype toward
  production: swapping the current logistic-regression baseline for the
  XGBoost/PyTorch models already scaffolded in the model zoo, wiring a
  real networked Flower server in place of the current single-process
  simulation, and replacing today's rule-based placeholder outcome labels
  with real clinical diagnosis/outcome labels once available — all
  without changing the surrounding architecture.

## Documentation map

- **`docs/16-week-development-plan.md`** — the full 16-week schedule this
  project follows, from initial proposal through final demo. Weeks 1–9
  cover the modules already in this repo; weeks 10–16 are the forward plan.
- **`docs/foundation-models-status.md`** — status of the SOTA
  foundation-model specialists added to Module 5 (RadFM, BiomedParse,
  SegVol, OmiCLIP, MeDiM, plus two unresolved names) — what's real code
  vs. blocked upstream vs. unverified.
- **`docs/module8-code-review-notes.md`** — code review findings from
  building Module 8, including fusion-severity-table gaps found and fixed
  in `module5-modelzoo/fusion.py` (Module 6 modalities and `genomic_variant`).
- **`moduleN-*/EXPLANATION.md`** (modules 1–8) — a full, presentation-ready
  presentation-ready explanation of what that module does, how it works,
  and how it connects to the rest of the system. (`moduleN-*/README.md`
  stays the terse, dev-facing "how to run this" reference — the two are
  meant to be read together, not as duplicates.)

## Model / algorithm / framework catalog

**Read `docs/model-algorithm-catalog.md` before building any new disease
specialist.** It covers every model family, algorithm, and framework
relevant to medical diagnosis + reasoning — imaging (2D classification,
segmentation, whole-slide/histopathology), tabular/EHR, genomic/omics,
clinical NLP, time-series, survival analysis, multi-modal fusion, and
explainability/reasoning methods (Grad-CAM, SHAP, causal inference,
knowledge graphs, etc.) — not just the five models currently implemented
in `module5-modelzoo`. Disease-specific notes for breast cancer and
leukemia are included, plus a general pattern for any disease not yet
named. Every future stage should pick its model(s) from this document.

## Team assignment

| Person | Module | Folder | Status this sprint |
|---|---|---|---|
| **P1 — Backend/Auth** | Authentication & Multi-Tenancy | `module1-auth/` | ✅ Done & tested. Hospital register/login/JWT, hospital-scoped endpoints. |
| **P2 — Data Engineer** | Data Ingestion & Validation | `module2-validation/` | ✅ Done & tested. Schema, range, consistency, and outlier checks. |
| **P3 — ML Engineer** | Local Training + Federated Aggregation | `module3-fedlearning/` | ✅ Done & tested. Working FedAvg simulation, 3 hospitals, non-IID data. |
| **P4 — Frontend** | Hospital Dashboard | `module4-dashboard-react/` | ✅ Done & tested. React "federation map," wired to Module 1 + Module 7's real APIs. The original plain-HTML dashboard was removed once this was confirmed fully wired — see the module's README. |
| **P3 (cont.) — ML Engineer** | Model Zoo & Task Router | `module5-modelzoo/` | ✅ Done & tested. XGBoost + TabPFN v2 (both real) + legacy DenseNet201/ResNet50/EfficientNet/U-Net + current-tier BiomedCLIP (CNN+ViT-hybrid head)/nnU-Net upgrades (real code, both tiers stubbed in this sandbox, current-tier preferred automatically when available) + Evo 2 genomic-variant specialist (new) + RadFM/BiomedParse/SegVol/OmiCLIP (real loading code added, stubbed here — see `docs/foundation-models-status.md`) coexisting via one unchanged router + fusion layer. |
| **P3 (cont.) — ML Engineer** | Condition Router (auto-switch by disease) | `module6-condition-router/` | ✅ Done & tested. Mention a disease (breast cancer, leukemia, diabetic retinopathy, etc.) and it auto-routes to the right specialist(s) + reasoning method(s) — see its README for the verified condition pathways. Histopathology now defaults to a UNI2-h + CLAM-style MIL specialist (legacy attention-MIL kept as fallback), and breast cancer/leukemia gained an Evo 2 genomic-variant track alongside the existing Random Forest expression-panel model. |
| **P1 (cont.) — Backend/Auth** | Admin / Platform Module (the operator's view) | `module7-admin/` | ✅ Done & tested. Hospital oversight (proxies Module 1), training-round history, validation-flag summaries, and a working "trigger a round" endpoint. First real cross-module wiring — see its README for exactly what's real. |
| — | Synthesis / Review-Packet Layer | `module8-synthesis/` | ✅ Done & tested. Aggregates Module 5/6 findings into a clinician review packet — no diagnosis, no treatment plan, `requires_clinician_review` hardcoded true. See its README. |

> Week mapping for this build: Week 1 = Modules 1–4, Week 2 = Module 5,
> Week 3 = Module 6, Week 4 = Module 7. This is the 8-module breakdown
> from the original proposal, not a 16-stage syllabus — if your
> course/team has a specific 16-stage breakdown, share it and this
> numbering can be remapped to match.

Every module runs and was smoke-tested independently. Modules 1–6 were
**not wired to each other** on purpose in earlier sprints — Module 7
brought the first real integration (dashboard status, training rounds,
validation flags), and **this sprint wires the actual data flow**: Module 1
now has a real `POST /vitals/upload` (forwards to Module 2 for validation,
stores passed/flagged records per hospital) and `GET /vitals/export`
(service-key gated, for Module 3), `training-status` is DB-backed instead
of a fake dict, the dashboard has a real upload form, and
`module3-fedlearning/simulate_real.py` runs FedAvg over that real,
validated hospital data instead of synthetic partitions. The one honest
gap left: uploaded vitals don't yet carry a real diagnosis/outcome label,
so `real_data.py` falls back to a rule-based placeholder — see its
docstring before treating any accuracy number from `simulate_real.py` as
clinically meaningful.

Each folder is independently runnable so the four of you aren't blocked on each other
this sprint. Module 3's `simulate.py` still doesn't depend on Module 1/2 — it uses
synthetic data so ML work can start immediately without a live pipeline; use
`simulate_real.py` once you want to exercise the real, wired-up path.

## Why this order

- Module 3 (FedAvg loop) is the riskiest/most novel piece technically, so it starts now,
  in isolation, on synthetic data — nobody wants to discover in week 4 that the
  federated averaging logic doesn't work.
- Module 1 and 2 can be built in parallel; neither depends on the other.
- Module 4 just needs Module 1's API contract (see `module1-auth/README.md`) to start
  wiring real requests instead of mocked ones.

## Running things

Each module has its own README with exact setup commands. Quick summary:

```bash
# Module 1 — Auth API
cd module1-auth && pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8001

# Module 2 — Validation service
cd module2-validation && pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8002

# Module 3 — Federated learning simulation
cd module3-fedlearning && pip install -r requirements.txt --break-system-packages
python simulate.py          # synthetic data, no dependencies on other modules
python simulate_real.py     # real hospital data — needs Module 1 + Module 2 running first

# Module 4 — Dashboard, React "Federation Map" (see module4-dashboard-react/README.md)
cd module4-dashboard-react && npm install
npm run dev          # http://localhost:5173

# Module 7 — Admin/Platform service (start Module 1 first — it proxies to it)
cd module7-admin && pip install -r requirements.txt --break-system-packages
export FEDMED_JWT_SECRET=dev-only-change-me   # MUST match Module 1's
export FEDHEAL_SVC_KEY_M2_M7=dev-only-key-module2-to-module7   # MUST match Module 2's
export FEDHEAL_SVC_KEY_M3_M7=dev-only-key-module3-to-module7   # MUST match Module 3's
uvicorn main:app --reload --port 8005
```

## Creating a hospital login

Every user in FedHeal belongs to a hospital (tenant) — there's no
standalone "sign up" separate from that. With Module 1 running
(`localhost:8001`), the full flow from zero to a logged-in session:

```bash
# 1. Create the hospital (tenant) itself
curl -X POST localhost:8001/hospitals -H "Content-Type: application/json" \
  -d '{"name": "General Hospital"}'
# -> {"id": "<hospital_id>", "name": "General Hospital", "is_active": true}
# copy <hospital_id> from the response for the next step

# 2. Register a user under that hospital
curl -X POST localhost:8001/register -H "Content-Type: application/json" \
  -d '{"email": "doc@general.com", "password": "hunter2", "hospital_id": "<hospital_id>"}'
# role defaults to "clinician" if not specified — see roles below

# 3. Log in — /token takes an OAuth2 form body, not JSON
curl -X POST localhost:8001/token -d "username=doc@general.com&password=hunter2"
# -> {"access_token": "<jwt>", "token_type": "bearer"}

# 4. Use the token on any protected endpoint
curl localhost:8001/me -H "Authorization: Bearer <jwt>"
```

You can also do all four steps interactively at
http://localhost:8001/docs once Module 1 is running.

**Roles** (set at registration via `"role"` in step 2, defaults to
`clinician` if omitted):
- `clinician` — views predictions, uploads vitals for their own hospital
- `hospital_admin` — manages that hospital's users/data
- `super_admin` — platform operator; the only role that can deactivate a
  hospital (`PATCH /hospitals/{id}`)

The JWT from step 3 carries the user's hospital ID and role — every other
endpoint trusts *only* what's inside that signed token, never a
client-supplied hospital ID, so a logged-in user can't act on another
hospital's data by changing a request parameter.

For the full endpoint reference (what's auth-gated, request/response
shapes, the vitals-upload and export flows) see
`module1-auth/README.md`.
