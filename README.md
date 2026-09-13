# FedHeal — Federated Learning Healthcare AI

Developed by a team of 4 members

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
2. The hospital uploads a batch of vitals, problems(diesease/condition) faced and medical history records. Module 1 forwards them
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

## How to Run FedHeal

FedHeal is eight independent services/libraries, not one app — some are
long-running HTTP services, some are scripts you run once, and some are
plain Python libraries other modules import. This section is the single
place that ties the whole thing together and gets you from a fresh clone
to a working, end-to-end demo.

### Prerequisites

- **Python 3.11+** (each backend module has its own `requirements.txt`;
  a separate virtualenv per module, or one shared one, both work)
- **Node.js 18+** and npm, for the dashboard
- A **Postgres/Supabase** connection string for anything beyond local
  dev, **or** just leave the database URL unset in each module and it
  falls back to local SQLite — the fastest way to try the whole system
  end-to-end
- No GPU is required to run the core demo (auth, validation, federated
  simulation, dashboard, tabular/vitals specialist). A GPU plus
  `torch`/`transformers`/Hugging Face Hub access is only needed if you
  want to exercise the imaging/genomic/foundation-model specialists in
  `module5-modelzoo`/`module6-condition-router` beyond their stub
  fallback — see those modules' own `README.md` for exactly what each
  one needs.

### 1. Configure environment variables

Every backend module ships a `.env.example` — copy it to `.env` in that
same folder and fill it in:

```bash
cp module1-auth/.env.example        module1-auth/.env
cp module7-admin/.env.example       module7-admin/.env
cp module4-dashboard-react/.env.example module4-dashboard-react/.env.local
```

Module 2 and Module 3 don't require a `.env` for local/demo use, only
optional reporting URLs.

A handful of values **must match exactly** across the modules that share
them — this is the most common source of "why is this 401'ing" during
first setup:

| Variable | Must be identical in | Purpose |
|---|---|---|
| `FEDMED_JWT_SECRET` | Module 1, Module 7 | Module 7 only verifies tokens Module 1 issues |
| `FEDHEAL_SVC_KEY_M3_M1` | Module 1, Module 3 (`real_data.py`) | lets Module 3 call Module 1's `/vitals/export` |
| `FEDHEAL_SVC_KEY_M2_M7` | Module 2, Module 7 | lets Module 2 post rolled-up validation flags |
| `FEDHEAL_SVC_KEY_M3_M7` | Module 3, Module 7 | lets Module 3 post round/accuracy history |
| `FEDHEAL_DASHBOARD_ORIGIN` | Module 1, Module 7 | must equal the dashboard's real origin (default `http://localhost:5173`) so CORS allows it |

For a first local run, the `.env.example` defaults already agree with
each other — you only need to change values if you're deploying beyond
one machine, or want Postgres instead of the SQLite fallback.

### 2. Install dependencies

```bash
# each backend module:
for m in module1-auth module2-validation module3-fedlearning module5-modelzoo module6-condition-router module7-admin; do
  (cd $m && pip install -r requirements.txt)
done

# dashboard:
cd module4-dashboard-react && npm install
```

(Use a virtualenv per module, or one shared one — nothing here requires
isolation, it's just good practice given differing dependency pins.)

### 3. Start the long-running services, in this order

Each of these is its own terminal/process. Start them in this order so
each service's dependencies are already up when it needs them:

| # | Module | Command | Port | Why this order |
|---|---|---|---|---|
| 1 | Module 1 — Auth | `cd module1-auth && uvicorn main:app --reload --port 8001` | 8001 | Everything else trusts its tokens |
| 2 | Module 2 — Validation | `cd module2-validation && uvicorn main:app --reload --port 8002` | 8002 | Module 1 forwards every upload here |
| 3 | Module 7 — Admin | `cd module7-admin && uvicorn main:app --reload --port 8005` | 8005 | Proxies Module 1, receives reports from 2 & 3 |
| 4 | Module 4 — Dashboard | `cd module4-dashboard-react && npm run dev` | 5173 | Needs 1 and 7 up to have anything to show |

Modules 3, 5, 6, and 8 are **not** long-running servers — see step 4/5.

Check everything is actually up before moving on:
```bash
curl http://localhost:8001/docs   # Module 1 Swagger UI
curl http://localhost:8002/health
curl http://localhost:8005/health
```

### 4. Seed some demo data (optional but recommended)

```bash
cd module7-admin && python seed_demo.py
```

This populates a few hospitals, some training-round history, and a mix
of clean/flagged records, so the dashboard isn't empty on first login.

### 5. Run a federated learning round

Module 3 is script-driven, not a long-running server, for the current
single-process simulation:

```bash
cd module3-fedlearning
python simulate.py          # synthetic data, no other services required
# or, against real uploaded/validated hospital data (needs Module 1 up
# and FEDHEAL_SVC_KEY_M3_M1 configured):
python simulate_real.py
```

Either script reports each round's progress to Module 7 (best-effort —
runs fine standalone if Module 7 isn't up), and you can also trigger a
round directly from the dashboard's super-admin view or via
`POST /admin/rounds/trigger` on Module 7, which launches the same script
as a subprocess.

The **real networked** version (separate Flower server + one client
process per hospital machine, instead of one local script) is
`module3-fedlearning/server.py` + `client_runner.py` — see that module's
own `README.md` before using this path; it's a reference implementation
for a real multi-machine deployment, not part of the default local demo.

### 6. Try the model zoo / condition router / synthesis layer

These three (Modules 5, 6, 8) are plain Python libraries, imported
directly rather than run as services — each has a runnable `demo.py`:

```bash
cd module5-modelzoo          && python demo.py
cd ../module6-condition-router && python demo.py
cd ../module8-synthesis        && python demo.py
```

Expect `[STUB]`-labeled output for the imaging/genomic specialists unless
you've installed `torch`/`transformers`/etc. and have GPU + Hugging Face
Hub access — see each module's `README.md` for exactly which
dependencies unlock which specialist, and `docs/model-algorithm-catalog.md`
/ `docs/foundation-models-status.md` for the full picture of what's real
vs. stub-tier today.

### 7. Log in to the dashboard

Open `http://localhost:5173`. Use the credentials `seed_demo.py` created
(check its output / source for the demo login), or register a hospital
via `POST /register` on Module 1 first if you haven't seeded demo data.
From there: upload vitals, review flagged records, trigger a training
round, and watch the federation map / rounds rail update.

### Shutting everything down

Each service is a normal foreground process (`Ctrl+C` to stop). There's
no shared process manager yet — see `DEVELOPMENT_PLAN.md` for the
planned `docker-compose.yml` that will bring all of the above up/down
with one command.

### Troubleshooting

- **401s between services** → check the shared-variable table in step 1
  — a mismatched `FEDMED_JWT_SECRET` or service key is the most common
  cause.
- **CORS errors in the browser console** → `FEDHEAL_DASHBOARD_ORIGIN` on
  Modules 1 and 7 must exactly match the URL the dashboard is actually
  running at (including port).
- **Module 3 can't reach Module 1's `/vitals/export`** → confirm Module 1
  is up first and `FEDHEAL_SVC_KEY_M3_M1` matches in both `.env` files.
- **Everything in Module 5/6 shows `[STUB]`** → expected without
  `torch`/GPU/Hugging Face Hub access in your environment; this is the
  registry's safe fallback behavior, not a bug. See those modules'
  `README.md`.

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
