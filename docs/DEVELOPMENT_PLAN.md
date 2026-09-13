# FedHeal — Development Plan to Launch (Target: October 12)

**Prepared:** September 13, 2026
**Horizon:** September 14 – October 12, 2026 (4 weeks, 3 phases)
**Team assumption:** 4 members (per project README), working roughly in parallel
module ownership rather than one person per phase.

---

## 1. Where the project actually stands today

This is an honest snapshot from reading the current codebase, not a generic
template. It's the starting point every date below is built from.

**Solid / working end-to-end:**
- Module 1 (Auth) — JWT issuance, hospital multi-tenancy, httpOnly cookie
  session, rate-limited login, CSV/JSON vitals upload, forwards to Module 2.
- Module 2 (Validation) — full 5-stage pipeline (de-identification →
  schema → plausibility → cross-field → isolation-forest outlier flag) with
  best-effort reporting to Module 7.
- Module 3 (Fed Learning) — single-process FedAvg simulation
  (`simulate.py`) proven to run end-to-end across 3 simulated hospitals,
  with a real logistic-regression model whose weights are actually
  averaged.
- Module 4 (Dashboard) — React app with login, federation map, rounds
  rail, upload panel, flagged-record review, and a super-admin system map,
  wired against Modules 1 and 7.
- Module 6 (Condition Router) & Module 8 (Synthesis) — condition →
  specialist(s) → explainer(s) → structured, clinician-facing report, with
  honest `is_stub` / `requires_clinician_review` flags carried all the way
  through.
- Module 7 (Admin) — hospital oversight, round history, rolled-up
  validation-flag counts, overview endpoint.

**Real, but not yet proven — the biggest risk block:**
- Module 5's imaging specialists (chest X-ray, retina, skin, segmentation)
  and Module 6's histopathology/genomic specialists are **architecturally
  complete but never actually trained or run** — `torch`/`torchvision`/
  `nnunetv2`/`evo2`/`timm` aren't installed in the dev sandbox, so every one
  of them has only ever executed its `ImportError` fallback path. They
  degrade cleanly to a labeled `StubSpecialistModel`, which is good
  engineering — but it means **no specialist model in the "current tier"
  has been validated against real data yet.**
- `module3-fedlearning/real_data.py` labels real hospital data with a
  **rule-based placeholder** (`_placeholder_label`), not a real clinical
  outcome — documented honestly in the code, but still a gap for anything
  claiming to be a real diagnostic result.
- `module5-modelzoo/router.py`'s `ClassifierBasedRouter` and
  `server.py`'s real networked Flower server are reference
  implementations, not yet exercised.

**Missing outright:**
- No automated tests anywhere in the repo (no `tests/`, no `pytest`
  config) for any of the 8 modules.
- No CI pipeline, no Dockerfiles/`docker-compose.yml`, no deployment
  scripts or infra-as-code.
- `docs/model-algorithm-catalog.md` and `docs/foundation-models-status.md`
  are referenced repeatedly by the root README but the `docs/` folder is
  empty — these don't exist yet.
- No per-module `README.md`/`EXPLANATION.md` files (this is what part 2 of
  this deliverable fixes).
- No production secrets/config story beyond `.env.example` placeholders,
  no HTTPS/TLS termination, no centralized logging, no backup/DR plan for
  the Postgres/Supabase store.

**Implication for the plan below:** four weeks is enough to take the
**core federated-learning + validation + dashboard + tabular-specialist
pipeline** to a tested, deployed, demo-ready state. It is **not** enough to
also fully train and clinically validate every imaging/genomic foundation
model from scratch. The plan therefore scopes the October 12 release
around the tabular/vitals pipeline (TabPFN/XGBoost — genuinely installable
and runnable today) plus the routing/explanation/synthesis architecture
running honestly in **stub-aware mode** for the imaging/genomic
specialists, with foundation-model training explicitly logged as
post-launch roadmap. This is a scoping decision the team should confirm
in the kickoff meeting below, not something to discover in week 3.

---

## 2. Timeline at a glance

| Phase | Dates | Duration | Focus |
|---|---|---|---|
| Kickoff & scope lock | Sep 14 (Mon) | 1 day | Confirm scope decision above, assign module owners |
| **Phase 1 — Development** | Sep 15 – Sep 27 | 2 weeks | Close functional gaps, wire missing pieces, write the two missing docs |
| **Phase 2 — Testing & Hardening** | Sep 28 – Oct 5 | 8 days | Unit/integration/E2E tests, security pass, cross-module dry runs |
| **Phase 3 — Deployment** | Oct 6 – Oct 11 | 6 days | Containerize, deploy to staging → prod, load-check, rehearse demo |
| **Launch / handover** | Oct 12 (Mon) | — | Go-live, final demo, sign-off |

---

## 3. Phase 1 — Development (Sep 15 – Sep 27)

Goal: every module does, in practice, what its README already claims —
no more "architecturally correct but never executed" code paths in the
launch scope.

### 3.1 Module 1 — Auth
- [ ] Confirm `FEDHEAL_COOKIE_SECURE` and CORS origin are environment-driven
      and correctly set per deploy target (local/staging/prod).
- [ ] Move the in-memory login rate limiter to a shared store (Redis, or
      accept single-worker deployment explicitly and document the
      limitation) before multi-worker deployment.
- [ ] Add a `/health` endpoint (Modules 2 and 7 already have one; Module 1
      doesn't) so the deployment phase has something to probe.

### 3.2 Module 2 — Validation
- [ ] No functional gaps found. Add structured logging of rejection
      reasons (already returned per-record; not yet persisted anywhere
      queryable) so Module 7's flag counts can be audited later.

### 3.3 Module 3 — Federated Learning
- [ ] Decide and document the launch-scope model: keep the
      `SGDClassifier` baseline (proven, explainable) as the reference
      model for the demo; confirm XGBoost swap is **out of scope** for
      Oct 12 unless capacity allows (see Module 5 note below — the
      registry-level XGBoost/TabPFN work is separate from this
      simulation's own baseline).
- [ ] Run `simulate_real.py` end-to-end against real uploaded hospital
      data at least once before Phase 2, to catch integration issues
      between Module 2's validated records and Module 3's feature
      extraction.
- [ ] Explicitly document (in the module's own README — see deliverable
      2) that `_placeholder_label` is a known, intentional limitation for
      this release, not a silent bug — and record what a real clinical
      label source would need to look like for the next release.
- [ ] `server.py` (real networked Flower) stays **reference-only** for
      this release; do not attempt real multi-machine networking in this
      window — flag as Phase-2-post-launch roadmap.

### 3.4 Module 4 — Dashboard
- [ ] Wire the dashboard's build against the actual deployed API URLs
      (currently defaults to `localhost`); add a staging `.env` file.
- [ ] Add basic error boundaries around `FederationMap`/`SystemMap` so a
      malformed API response doesn't blank the whole page.
- [ ] Quick accessibility pass on `LoginGate`/`UploadPanel` forms (label
      associations, focus states) — cheap now, expensive to retrofit.
- [ ] Production build (`npm run build`) verified to run clean with no
      console warnings.

### 3.5 Module 5 — Model Zoo
- [ ] On a machine with disk/GPU headroom (not the dev sandbox), install
      `torch`/`torchvision` and confirm `imaging_chest_xray.py` /
      `imaging_retina.py` / `imaging_skin.py` / `imaging_segmentation.py`
      at least **instantiate and run a forward pass** on dummy input —
      this alone will catch any latent bugs in code that has literally
      never executed.
- [ ] Training data for these imaging models is **not currently
      available in this repo** — training real weights is out of scope
      for Oct 12. Launch scope = these specialists run in `is_stub` mode
      honestly, which the dashboard and synthesis layer already surface
      correctly. Confirm this is acceptable to stakeholders at kickoff.
- [ ] TabPFN/XGBoost vitals specialist (`tabular_vitals*.py`) — this one
      **is** installable and runnable today with no GPU. Prioritize
      getting this specialist fully working end-to-end (real prediction,
      not stub) since it's the one realistic "real model" story for the
      Oct 12 demo.
- [ ] Recreate `docs/model-algorithm-catalog.md` and
      `docs/foundation-models-status.md` — referenced throughout the root
      README and this module's own code comments, but currently missing
      from the repo. Content already implicit in `registry.py`'s comments
      and the root README's algorithm table; this is consolidation work,
      not new research.

### 3.6 Module 6 — Condition Router
- [ ] Same imaging/genomic caveat as Module 5 — histopathology and
      genomic-variant specialists stay stub-tier for this release.
- [ ] SHAP explainer — confirm it runs against the real
      TabPFN/XGBoost vitals specialist once that's wired live (3.5
      above); this is the one explainer that can be end-to-end real for
      launch.
- [ ] Grad-CAM and knowledge-graph reasoner stay documented as
      stub-degraded pending real imaging weights.

### 3.7 Module 7 — Admin
- [ ] No functional gaps found. Confirm `seed_demo.py` produces a
      convincing, realistic dataset for the Oct 12 demo (multiple
      hospitals, several rounds of history, a mix of clean and flagged
      records).

### 3.8 Module 8 — Synthesis
- [ ] No functional gaps found. Add one integration test exercising the
      full Module 6 → Module 8 path with a mix of real and stub findings,
      confirming `used_any_stub_models` and `requires_clinician_review`
      are always correctly set (this is the module whose entire purpose
      is not misleading a clinician, so it deserves the most scrutiny in
      Phase 2 even though it has no functional gap today).

### 3.9 Cross-cutting (all modules)
- [ ] Write the two missing `docs/` files (3.5 above).
- [ ] Write per-module `README.md`/`EXPLANATION.md` files — see the
      companion deliverable to this plan.
- [ ] Stand up a shared `docker-compose.yml` covering Modules 1, 2, 3, 4,
      7 (the services that run continuously) for local/staging parity.

**Exit criteria for Phase 1:** every module's own documentation
accurately describes what the code does when actually run, the vitals
(TabPFN/XGBoost) path produces a real (non-stub) prediction end-to-end
through Modules 1→2→5→6→8, and `docker compose up` brings up all five
backend/frontend services locally with no manual patching.

---

## 4. Phase 2 — Testing & Hardening (Sep 28 – Oct 5)

Goal: confidence that the system behaves correctly under real use and
adversarial input, not just on the happy path a developer tried once.

### 4.1 Unit tests (per module, target ≥70% coverage on business logic)
- Module 1: token issuance/expiry, rate limiter, role checks, CSV/JSON
  upload parsing edge cases (malformed rows, duplicate `patient_ref`).
- Module 2: each of the 5 pipeline stages independently — forbidden
  fields, boundary values on plausibility ranges, cross-field
  contradictions, isolation-forest flagging on synthetic outliers.
- Module 3: `get_model_parameters`/`set_model_parameters` round-trip,
  `partition_for_hospitals`'s non-IID split, one full `HospitalClient.fit`
  call against fixture data.
- Module 5/6: registry fallback logic (`ImportError`/`OSError`/
  `NotImplementedError` → `StubSpecialistModel`) — this is the single
  most safety-critical piece of logic in the whole model zoo and
  currently has zero test coverage.
- Module 7: overview aggregation math, flag rollup counts.
- Module 8: `used_any_stub_models` / `requires_clinician_review`
  invariants under every combination of real/stub findings.

### 4.2 Integration tests
- Module 1 → Module 2: a batch with one forbidden field, one
  out-of-range value, and one clean record — confirm exactly the right
  per-record outcome.
- Module 1 → Module 7: hospital status changes reflected in admin
  overview within one poll cycle.
- Module 5 → Module 6 → Module 8: full condition query (e.g. "breast
  cancer") producing a `SynthesisReport` with correct disclaimer and
  completeness flags.
- Module 4 against a running Module 1 + Module 7: login → upload →
  review-flagged-record → trigger round → see it reflected in the
  federation map, as one scripted flow (Playwright or Cypress).

### 4.3 End-to-end / system test
- Full `simulate_real.py` run against a seeded multi-hospital dataset,
  producing a federated-vs-solo accuracy comparison, with the dashboard
  open and polling live during the run.

### 4.4 Security & privacy review
- Confirm the JWT secret, per-caller service keys
  (`FEDHEAL_SVC_KEY_M3_M1`, `FEDHEAL_SVC_KEY_M2_M7`, `FEDHEAL_SVC_KEY_M3_M7`)
  are unique, non-default values in every non-local environment.
- Confirm CORS origins are locked to the real deployed dashboard URL, not
  `*`, in staging and prod.
- Re-run the de-identification field list (`rules.FORBIDDEN_FIELDS`)
  against a real hospital export format if one becomes available, to
  catch any institution-specific identifying field not yet on the list.
- Dependency audit (`pip-audit` / `npm audit`) across all `requirements.txt`
  and `package.json` files.

### 4.5 Performance / load check
- Module 2's isolation-forest batch flagging and Module 1's rate limiter
  under a simulated burst upload (a few thousand records) — this is the
  most likely real-world bottleneck given both are currently
  single-process/in-memory.
- Dashboard poll interval (`POLL_MS = 12000`) against however many
  hospitals the demo/launch will actually seed — confirm it doesn't
  hammer Module 1/7 under the real hospital count.

**Exit criteria for Phase 2:** all Phase 1 exit-criteria flows pass under
automated test, no known default/placeholder secret remains in any
non-local config, and the team has a written record of what load level
was actually tested (so Phase 3 doesn't deploy blind).

---

## 5. Phase 3 — Deployment (Oct 6 – Oct 11)

Goal: the system is reachable at a real URL, by real (or realistic demo)
hospital users, in a state the team is comfortable calling "launched."

| Day | Task |
|---|---|
| Oct 6 (Tue) | Finalize `docker-compose.yml` / Dockerfiles for all 5 services; build images |
| Oct 7 (Wed) | Deploy to a staging environment (staging Supabase project, staging URLs); run the Phase 2 test suite against staging, not just local |
| Oct 8 (Thu) | Fix anything staging surfaces that local didn't; confirm HTTPS/TLS on every public-facing service; lock CORS to prod dashboard origin |
| Oct 9 (Fri) | Deploy to production; run `seed_demo.py`-equivalent realistic demo data (or real onboarded hospitals, if any are ready) |
| Oct 10 (Sat) | Full dry-run of the Oct 12 demo/handover script end-to-end in prod; freeze scope — bug fixes only from here |
| Oct 11 (Sun) | Buffer day for anything the dry run surfaced; finalize handover documentation |
| **Oct 12 (Mon)** | **Launch / final demo / sign-off** |

### 5.1 Deployment checklist
- [ ] Environment variables for all four backend services set from a
      secrets manager, not committed `.env` files.
- [ ] Database migrations applied to the production Postgres/Supabase
      instance (currently no migration tool in the repo —
      `Base.metadata.create_all` is fine for dev, but a production launch
      should use Alembic or equivalent so future schema changes don't
      require a manual reconcile).
- [ ] Logging aggregated somewhere queryable (even a simple hosted log
      drain) — right now each service just prints/raises locally.
- [ ] A written rollback plan: what to do if a deployed round of the
      dashboard or a backend service needs to be reverted mid-demo.
- [ ] Backup schedule confirmed for the production database.

**Exit criteria for Phase 3 / launch:** every module reachable over
HTTPS at its production URL, the full login → upload → validate → train
round → review → synthesis flow works against production data, and the
team has a rehearsed answer for "what's stubbed and why" for any
imaging/genomic specialist a stakeholder asks about live.

---

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Imaging/genomic specialists never get real trained weights before Oct 12 | High (near-certain given no training data/GPU access documented) | Medium — mitigated by honest stub-labeling already built in | Scope launch around the vitals/TabPFN path (already decided above); present imaging/genomic tier explicitly as roadmap, not a gap discovered late |
| Real clinical labels for `real_data.py` don't materialize in time | Medium | Medium | Keep placeholder label, document it prominently in Module 3's README and in any external-facing demo materials |
| Single-process rate limiter / isolation forest doesn't hold up under real multi-hospital load | Medium | Medium | Load-test explicitly in Phase 2 (4.5); have Redis-backed limiter as a fallback plan if staging load test fails |
| No CI pipeline means regressions ship silently during the compressed testing window | Medium | High | Stand up a minimal GitHub Actions workflow (lint + unit tests) in the first two days of Phase 1, not as an afterthought |
| Four-week timeline for 8 modules across a 4-person team is tight | High | High | Module ownership split 2 people/module-pair rather than 1:1, so Phase 2 testing of a module isn't blocked on the same person who wrote it |

---

## 7. Suggested ownership split (4-person team)

- **Owner A** — Module 1 (Auth) + Module 4 (Dashboard) — the
  user-facing login/upload/review path.
- **Owner B** — Module 2 (Validation) + Module 7 (Admin) — the
  data-quality and operator-oversight path.
- **Owner C** — Module 3 (Fed Learning) — the core FedAvg pipeline, plus
  the real-data integration test in 4.3.
- **Owner D** — Module 5 + Module 6 + Module 8 — the model
  zoo/routing/synthesis chain, and the two missing `docs/` files.

All four share Phase 3 deployment work and the Oct 10 dry run.
