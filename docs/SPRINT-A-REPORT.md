# Sprint A — Completion Report

**Sprint:** Sep 14 – Sep 20 (finish week 10, start week 13)
**Status:** Both workstreams complete.
**Plan reference:** `docs/DEVELOPMENT_PLAN.md` §3, Sprint A.

---

## TL;DR

Both Sprint A items landed and are verified. Two things need a decision
before Sprint B planning:

1. **The UCI seed covers 3 of 8 features, not 8.** The plan called
   Cleveland "structurally compatible with the vitals schema". It's
   compatible on the label and on three features; it has no equivalent
   for the other five. This caps achievable accuracy well below published
   Cleveland results. → [Decision 1](#decision-1--do-we-widen-the-vitals-schema)
2. **`GET /vitals/export` changed its default behaviour.** Unlabeled
   records are now excluded unless explicitly requested. This is
   intentional and is the point of the sprint item, but it's a breaking
   change for any caller we don't know about.
   → [Decision 2](#decision-2--confirm-the-export-default-change)

---

## Workstream 1 — Real datasets & labels (P2 + P3)

### 1a. Placeholder labels are no longer the default path

The plan asked to "make the placeholder fallback an explicit, logged,
clearly-flagged exception rather than silent default behavior."

What was actually happening before: `real_data.py` substituted a
rule-based label (`systolic >= 140 or medication_mg_total >= 300`) for
any record without one, silently. The default end-to-end path therefore
trained partly on labels no clinician ever produced, and nothing in the
output said so.

Four changes, at four layers, so this can't be defeated by one of them
being bypassed:

| Layer | Change |
|---|---|
| Module 1 (tenant config) | `hospitals.requires_label` — an explicit per-hospital declaration that it has real outcomes |
| Module 2 (validation) | `rules.check_required_label` — **rejects** unlabeled records from a label-supplying hospital, at upload time |
| Module 1 (storage + export) | `vitals_records.label_source`; `/vitals/export` defaults `labeled_only=true` |
| Module 3 (training) | `UnlabeledDataError` by default; `--allow-placeholder-labels` to override; `LabelProvenance` returned alongside every partition |

Three design choices worth recording, because each was a fork:

- **`label_source` has no `"placeholder"` value.** Only `"hospital"` or
  `"missing"`. The placeholder is computed at training time and never
  written back, so the database physically cannot assert that a made-up
  label is a clinical fact.
- **`requires_label` defaults to false and is never inferred.** Inferring
  it from "did labels show up in the last upload?" would silently switch
  the rule off the first time a hospital's export broke — the exact
  failure it exists to catch.
- **The required-label check rejects rather than flags.** A flagged record
  is still stored and still reachable by training after human review. An
  unlabeled record from a hospital that promised labels is a broken
  export, not a borderline measurement.

The loader functions now return provenance as a third element
(`X, y, provenance`). Making it a *required* return rather than an
optional kwarg was deliberate: every call site has to acknowledge label
provenance instead of inheriting a silent default.

### 1b. UCI Heart Disease seed

Vendored at `module3-fedlearning/datasets/heart_cleveland_islr.csv`,
SHA-256 pinned, cited (Janosi et al. 1989, DOI 10.24432/C52P4X, CC BY
4.0), with the full provenance chain in `datasets/README.md`.

Verified as the genuine Cleveland subset against four published markers,
not a Kaggle re-derivation: 303 records, 164/139 class split, `age` 29–77
/ `trestbps` 94–200 / `thalach` 71–202, and exactly 6 missing values (4
`ca`, 2 `thal`).

`seed_uci_heart.py` uploads it **through Module 1's real
`POST /vitals/upload`**, as a logged-in hospital user, rather than
inserting rows into the database. A direct insert would have been far
faster and would have proven nothing; going through the front door means
the demo data has passed the same five-stage Module 2 gate production
data does, and that running the seed is itself an end-to-end integration
test.

Result of the real seed run: **303/303 records stored, 0 rejected, 100%
real labels**, 16 soft-flagged as batch outliers by the isolation forest
(expected for real clinical data).

---

## Workstream 2 — Alembic setup (P1)

Set up in `module1-auth/` with two revisions:

- `0001_baseline` — the schema as it existed at week 9. Contains no new
  work on purpose; it exists so databases already built by `create_all`
  have something to `alembic stamp`.
- `0002_label_provenance` — adds the two columns from workstream 1.

Three details that matter:

- **The URL comes from `FEDHEAL_DATABASE_URL`**, the same env var
  `database.py` reads, not from `alembic.ini` (which is left empty). One
  source of truth for "which database", and no Supabase password in
  version control.
- **`render_as_batch=True`**, because SQLite can't `ALTER TABLE` to add
  constraints. Without it, migrations work against Supabase and fail for
  every teammate on the SQLite default — the worst place to find out.
- **`0002` backfills rather than relying on its server default.** Adding
  `label_source` defaulting to `'missing'` would have marked
  already-labeled historical records as unlabeled, and the new
  `labeled_only=true` export default would then have silently shrunk
  every hospital's usable dataset. The migration derives the value from
  whether `label` is actually populated.

`create_all` is gated behind `FEDHEAL_AUTO_CREATE_TABLES` (default true)
rather than removed. Both mechanisms being live is deliberate for this
transitional sprint and should not outlive Sprint B — if both stay,
`create_all` will silently create any table a forgotten migration missed,
and the schema Alembic believes is deployed will drift from the one
actually deployed.

---

## Verification performed

Everything below was run, not reasoned about.

| Check | Result |
|---|---|
| Fresh DB → `alembic upgrade head` | Both revisions apply; schema correct |
| Existing `create_all` DB (6 records: 4 labeled, 2 unlabeled) → `stamp` + `upgrade` | Applies cleanly; **backfill correct, 0 mismatches** |
| `downgrade` → `upgrade` round trip | All 6 records preserved; backfill re-derived correctly |
| `alembic revision --autogenerate` against the migrated schema | **Empty** — migrations match `models.py`, no drift |
| Both services booted on a migration-built DB with `create_all` **disabled** | Healthy |
| Seed 303 UCI records through the real upload path | 303 stored, 0 rejected, 100% labeled |
| Unlabeled upload to a `requires_label` hospital | **Rejected**, with the explanatory reason |
| Same record with a label | Stored, `label_source="hospital"` |
| `/vitals/export` default | Unlabeled excluded; `labeled_only=false` restores old behaviour |
| Hospital with only unlabeled records, Module 3 default | Skipped and reported, not silently placeholder-labeled |
| Same, with `allow_placeholder_labels=True` | Included, `WARNING` banner to stderr, provenance 19/19 placeholder |
| `simulate_real.py` against the seeded stack | Runs; provenance reported as 288/288 real |
| `test_client_runner_matches_simulation.py` (existing regression test) | **PASS** — real networked path 0.916700 vs in-process 0.916667 |

---

## Findings that affect the Oct 12 demo

### Finding 1: only 3 of 8 features are real

Cleveland has 13 attributes; the vitals schema has 8 features. Only four
columns genuinely correspond:

| FedHeal field | Cleveland | Notes |
|---|---|---|
| `age_years` | `age` | Identical. |
| `systolic_bp` | `trestbps` | Identical (resting systolic, mmHg). |
| `heart_rate_bpm` | `thalach` | **Exercise maximum** HR, not a resting vital. Real, but not the measurement a ward nurse records. |
| `label` | `num > 0` | Real clinical outcome. |

Cleveland measures nothing corresponding to `diastolic_bp`, `height_cm`,
`weight_kg`, `medication_count`, or `medication_mg_total`. Those five are
set to fixed constants pinned to `real_data._FEATURE_MEAN`, so after
normalization they are **exactly 0.0** and contribute nothing. Verified
empirically: 8-column and 3-column accuracy are identical to four decimal
places.

They were not back-filled from other Cleveland columns. Putting
cholesterol in the `weight_kg` slot because both are numbers would be
fabrication, not a mapping.

**Consequence:** quote results as "3 real vitals features from Cleveland",
never as "UCI Heart Disease accuracy". Published Cleveland results using
all 13 attributes reach ~85%; we should not be compared against that
number.

### Finding 2: a single run of the comparison is not a result

The first run (`--seed 42`) showed federation *losing*: 0.574 vs a solo
baseline of 0.603. A different seed showed it winning. Neither is the
answer.

Over 20 seeds (3 hospitals, non-IID α=3.0):

| | Mean | SD | Range |
|---|---|---|---|
| Federated | **0.614** | 0.084 | 0.457 – 0.761 |
| Solo baseline | **0.536** | 0.043 | 0.457 – 0.616 |
| Delta | **+0.077** | 0.076 | — |

**Federation beat solo in 17 of 20 seeds.** Majority-class floor: 0.541.

So the project's central claim does hold — but the spread is wide enough
that any single run can contradict it. The cause is structural, not
noise: 303 records split three ways leaves a ~47-record global holdout,
where one misclassified patient moves accuracy by two points.

`compare_uci_heart.py --sweep 20` was added specifically so the
distribution is what gets reported. The single-run mode now prints
"ONE SEED IS NOT A RESULT" under its own output.

Also worth noting: the solo baseline mean (0.536) sits marginally *below*
the majority-class floor. A single `partial_fit` epoch on one hospital's
small skewed partition barely learns anything — which is a fair
illustration of the problem federation addresses, and is worth saying out
loud in the demo rather than hoping nobody computes the floor.

---

## Decisions needed

### Decision 1 — do we widen the vitals schema?

Adding Cleveland's genuinely-clinical columns (`chol`, `oldpeak`,
`exang`, `cp`) would lift accuracy substantially and make the demo far
more compelling.

**Recommendation: no, not before Oct 12.** It changes `N_FEATURES`, which
is the model contract — so it touches Module 3's model, Module 5's
specialists and fusion, Module 6's condition router, and Module 2's
rules. That is a schema migration across four modules during the sprint
where testing was already compressed (plan §5, row 3). The honest
3-feature result plus a clear explanation is a better position on Oct 12
than a broken integration.

Suggested placement: first post-launch item, alongside real imaging
training (cut list §4.1).

### Decision 2 — confirm the export default change

`GET /vitals/export` now defaults to `labeled_only=true`. Known callers
(Module 3's `real_data.py`) are updated. If anything else calls this
endpoint that isn't in this repo, it will see fewer records than before.

**Recommendation: keep the new default.** The old default was the bug.
But someone who knows the deployment should confirm there is no external
caller before Sprint B applies migrations to staging.

---

## Carried into Sprint B

Nothing from Sprint A slipped. These are the handoffs the plan already
scheduled:

- Apply migrations to staging, then set `FEDHEAL_AUTO_CREATE_TABLES=false`
  there and **remove the `create_all` block from `main.py` entirely**.
- Module 7 has its own database (`training_rounds`, `validation_flags`)
  with no migrations yet. Out of Sprint A's scope, which named Module 1
  only — but it's the same work and the pattern is now established.
- The dashboard doesn't yet surface `label_coverage` or the
  `awaiting_labels` status, so a hospital admin can't see the label gap
  in the UI. Fits naturally into Sprint B's frontend workstream (P4).
- `simulate_real.py` gained `--allow-placeholder-labels`; `server.py`
  has no equivalent flag, so the real networked path relies on each
  `client_runner.py` being invoked correctly. Worth a look when the
  cross-machine stretch goal is attempted.
