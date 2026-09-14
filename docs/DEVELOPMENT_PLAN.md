# FedHeal — Development Plan (Merged): History + Oct 12 Launch

**Prepared:** September 14, 2026
**Supersedes:** the original `docs/DEVELOPMENT_PLAN.md` (4-week, Oct-12-only
plan) and the forward-looking portion (weeks 10–16) of
`docs/16-week-development-plan.md`. Weeks 1–9 of that plan were already
accurate and are carried forward here unchanged, so this is one
continuous document instead of three overlapping ones.

**If you're deciding what to do with the two old files:** replace
`docs/DEVELOPMENT_PLAN.md`'s content with this file, and either delete
`docs/16-week-development-plan.md` or keep it purely as a dated
historical record — nothing after this document should treat it as the
active plan.

---

## 1. Weeks 1–9 — what's already built (unchanged history)

| Week | Focus | Module(s) | Key deliverables | Status |
|---|---|---|---|---|
| 1 | Requirements & architecture | — | Problem statement, dataset shortlist, tech-stack decisions, repo scaffolding | ✅ Done |
| 2 | Authentication & multi-tenancy | Module 1 | Hospital/user models, JWT login, hospital-scoped auth pattern | ✅ Done |
| 3 | Data ingestion & validation | Module 2 | De-identification, schema/range/consistency checks, isolation-forest flagging | ✅ Done |
| 4 | Local training + FedAvg core | Module 3 | `HospitalClient`, manual FedAvg loop (`simulate.py`) on synthetic non-IID data | ✅ Done |
| 5 | Hospital dashboard v0 | Module 4 | Plain HTML/JS dashboard | ✅ Done (superseded by React rebuild) |
| 6 | Model zoo & task router | Module 5 | `SpecialistModel` interface, XGBoost, legacy imaging CNNs, metadata router, fusion | ✅ Done |
| 7 | Condition router & explainability | Module 6 | Condition → specialists + explainers auto-switch; SHAP, Grad-CAM, KG reasoner | ✅ Done |
| 8 | Admin / platform module | Module 7 | Hospital oversight, round history, flag summaries, trigger-round endpoint | ✅ Done |
| 9 | Data-flow integration | Modules 1, 3, 4 | Real pipeline: upload → validate → store → train on real data; DB-backed training status | ✅ Done |

Nothing in this section changes — it's included so this one document is
the complete story, not just the part that changed.

## 2. Why weeks 10–16 don't fit before Oct 12 as originally scoped

The original 16-week plan allotted **7 more calendar weeks** (10–16) to:
real datasets/labels, real imaging training, real networked FL, security
hardening, frontend rebuild, testing/deployment, and polish/demo.

Only **4 weeks** actually remain before Oct 12 (Sep 14 → Oct 12). That's
roughly 3 weeks of planned work that has to either compress, get cut, or
slip past the deadline. Since the last update, some of weeks 10–14 is
already further along than originally scoped (see the status column
below, carried from the 16-week plan) — which helps, but not enough to
close a 3-week gap on its own. Section 4 below is the explicit,
honest list of what doesn't make it by Oct 12 as a result.

**Current status of each remaining week, as of this merge** (unchanged
from the 16-week plan's own tracking — this document doesn't relitigate
what's already been assessed, just re-schedules it):

| Original week | Focus | Status going into this merge |
|---|---|---|
| 10 | Real datasets & labels | 🟡 Partial — real `label` field validated end-to-end (schema, CSV upload, human review); underlying feature set still synthetic-shaped, placeholder-label fallback still exists for missing labels |
| 11 | Imaging track goes live | ⬜ Planned — no real training has happened yet |
| 12 | Real networked federated learning | 🟢 **Now essentially done** — `server.py` + `client_runner.py` implemented and verified (see the module 3 update from this sprint); TLS still open |
| 13 | Security & infra hardening | 🟡 Partial — per-service credentials, CORS lockdown, rate limiting, httpOnly cookies done; Alembic migrations still open |
| 14 | Frontend rebuild | 🟡 Partial — federation map, operator views, upload, flagged-record review all live; explainer charts (Grad-CAM/SHAP) and Module 8 synthesis view still open |
| 15 | Testing, QA & deployment | ⬜ Planned |
| 16 | Polish, demo & submission | ⬜ Planned |

Week 12 moved from 🟡 to essentially 🟢 since the 16-week plan was
written, which is the main reason this merge is more optimistic on that
front than a strict 3-week shortfall would otherwise suggest — it's real
schedule slack the other weeks can borrow.

## 3. The recompressed plan: Sep 14 → Oct 12

### Sprint A — Sep 14 to Sep 20 (finish week 10, start week 13)

- **Real datasets & labels (P2 + P3):** stop relying on
  `real_data.py`'s placeholder label as the default path. Require a real
  label on upload where a hospital has one; make the placeholder
  fallback an explicit, logged, clearly-flagged exception rather than
  silent default behavior. Seed the demo/eval data using the **UCI Heart
  Disease dataset** (public, no access approval needed, structurally
  compatible with the vitals schema) so the federated-vs-solo accuracy
  comparison is demonstrated on a real, cited dataset rather than
  synthetic data, without waiting on anything outside the team's
  control. **MIMIC-III/IV integration does not fit this window** — see
  section 4.
- **Security & infra hardening, start (P1):** begin the Alembic
  migration setup in parallel — independent of the item above, so it
  doesn't compete for the same people's time.

### Sprint B — Sep 21 to Sep 27 (close out weeks 12 & 13, start week 14)

- **Real networked FL, close-out (P3 + P1):** the core work is done.
  Stretch goal only, not a launch blocker: run `client_runner.py` from
  at least two genuinely separate machines/VMs once, since everything
  verified so far (`run_local_smoke_test.sh`,
  `test_client_runner_matches_simulation.py`) is localhost/subprocess-
  based. If this doesn't fit, the localhost verification already done is
  sufficient evidence the path itself is correct — don't let this block
  anything else. **TLS stays out of scope** — see section 4.
- **Security & infra hardening, finish (P1):** Alembic migrations
  complete and applied to the staging database.
- **Frontend, start (P4):** build the Module 8 synthesis view (rendering
  a `SynthesisReport` — findings, disclaimer, stub markers — in the
  dashboard) and SHAP chart rendering, since SHAP is the one explainer
  that pairs with a genuinely real (non-stub) specialist today (the
  vitals/TabPFN path). **Grad-CAM heatmap UI is deferred** — see section
  4; there's no real imaging output yet for it to visualize.

### Sprint C — Sep 28 to Oct 4 (finish week 14, start week 15)

- **Frontend, finish (P4):** Module 8 synthesis view and SHAP charts
  fully wired and demoable end-to-end (upload → route → synthesize →
  view, in the dashboard, on real vitals data).
- **Testing, QA & deployment, start (whole team):**
  - Unit tests per module (prioritize Module 2's validation pipeline and
    Module 5/6's stub-fallback logic — highest safety value per record).
  - Integration tests across module boundaries (Module 1→2, 1→7,
    5→6→8, and the dashboard against a running backend).
  - Dockerfile per service; draft `docker-compose.yml` for full local
    stack.
  - Start the IRB/HIPAA/GDPR compliance write-up (documentation only —
    what a real deployment would require, not the approval process
    itself; the 16-week plan already scoped this correctly as
    documentation, and that stays true here).

### Sprint D — Oct 5 to Oct 11 (finish week 15, run week 16)

| Day | Task |
|---|---|
| Oct 5–6 | Finish `docker-compose.yml`; finish the CI pipeline (lint + unit tests on push); finish the compliance write-up |
| Oct 7 | Deploy to staging; run the full test suite against staging, not just local |
| Oct 8 | Fix whatever staging surfaces; lock down CORS/secrets for the real deployed origin |
| Oct 9 | Deploy to production; seed realistic demo data |
| Oct 10 | Full dry run of the Oct 12 demo/submission script in prod; freeze scope — bug fixes only from here |
| Oct 11 | Buffer day; finalize report/slides/demo video |
| **Oct 12** | **Launch / final demo / submission** |

## 4. What has to slip past Oct 12 (explicit cut list)

Being honest about this now is the entire point of merging these two
plans — better to name it here than discover it on Oct 10.

1. **Real imaging model training** (originally week 11 in full — fine-
   tuning ResNet50 on APTOS 2019, DenseNet201 on a ChestX-ray14 subset,
   etc.). This needs provisioned GPU time plus multi-day training/eval
   cycles *per specialist* — trying to force it into this window would
   put the whole rest of the plan at risk for a result that likely
   wouldn't even be fully validated by Oct 12 anyway. Module 5's imaging
   specialists continue running in their existing, honestly-labeled stub
   mode for the Oct 12 release. This becomes the first item of
   post-launch work.
2. **MIMIC-III/IV integration.** Physionet credentialing and a data-use
   agreement routinely take weeks and are outside engineering's control
   on any timeline. UCI Heart Disease (Sprint A, above) is the real,
   immediately-available substitute for Oct 12; MIMIC integration is
   scheduled as the first follow-on to Sprint A's work, not abandoned.
3. **TLS for the real networked FL server/client.** The plaintext gRPC
   path is correct and sufficient for a localhost/LAN demo — both
   `server.py` and `client_runner.py` already document this limitation
   themselves. Needed before any real hospital traffic crosses the open
   internet; not needed for Oct 12.
4. **Grad-CAM heatmap overlay UI.** Directly downstream of item 1 — with
   no real imaging weights, this UI would only ever render stub output,
   which isn't compelling demo material and isn't worth the frontend
   time this window. Revisit once item 1 has a real specialist to
   visualize.
5. **Real IRB approval, per-hospital data-governance agreements, and a
   production secrets manager.** The original 16-week plan already
   flagged these as outside a single team's control on any internal
   timeline — that's still true. Sprint C's compliance write-up
   documents what these would require; it doesn't (and can't) complete
   them.
6. **Cross-machine verification of the real networked FL path** is a
   stretch goal in Sprint B, not a requirement — see Sprint B above.

## 5. Risk register (updated)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| UCI Heart Disease swap (Sprint A) takes longer than a week and pushes into Sprint B's time | Medium | Medium | It's schedulable in parallel with Alembic work (different owners); if it slips, the existing validated-real-label path (already partially done) is an acceptable fallback demo story on its own |
| Alembic migration surfaces a schema mismatch against real seeded/demo data | Low–Medium | Medium | Run it against a staging copy of the data first, not directly against anything Sprint C/D depends on |
| Compressed testing window (Sprint C/D) means less time per module than the original plan's dedicated week 15 | Medium | High | Prioritize by safety value, not module order — Module 2 (data quality gate) and Module 5/6 (stub-fallback correctness) first, dashboard E2E and load testing if time remains |
| Frontend work (SHAP charts + synthesis view) is new UI, not a port of something existing, and could run long | Medium | Medium | Scope the first version to the minimum that makes the vitals→SHAP→synthesis story demoable; polish is a Sprint D/week-16 item, not a Sprint B/C blocker |
| Team morale/velocity risk from a visibly compressed timeline after a genuinely strong week-12 result | Low | Medium | This document's explicit cut list (section 4) exists partly for this reason — a clear, honest "here's what we're deliberately not doing and why" reads very differently from an unplanned scramble |

## 6. Ownership (unchanged from the 16-week plan's roles)

**P1** = Backend/Auth, **P2** = Data Engineer, **P3** = ML Engineer, **P4**
= Frontend — carried over from the existing team-assignment convention.
Sprint A/B/C/D above assign work by this same rotation; adjust to your
actual team size the same way the original plan already recommended.

## 7. Deployment checklist (Sprint D)

- [ ] Environment variables for all services set from a secrets manager
      in staging/prod, not committed `.env` files.
- [ ] Alembic migrations applied to the production database (this is
      the one item that changes here vs. the original 4-week plan, which
      still assumed `Base.metadata.create_all`).
- [ ] Logging aggregated somewhere queryable.
- [ ] Written rollback plan for a mid-demo revert.
- [ ] Backup schedule confirmed for the production database.
- [ ] CORS locked to the real deployed dashboard origin (already largely
      done per week 13's status — verify against the actual prod URL,
      not just staging).

**Exit criteria for Oct 12:** every module reachable at its production
URL, the full login → upload → validate → real-labeled training round
→ review → SHAP-explained synthesis flow works against production data,
CI is green, and the team has a rehearsed, honest answer — this
document — for anything a stakeholder asks about what's stubbed, what's
deferred, and why.
