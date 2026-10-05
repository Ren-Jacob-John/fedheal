# Sprint C report (Sep 28 to Oct 4)

## Delivered

| Item | Result |
|---|---|
| Dockerfile per service | Added for Modules 1, 2, 3 (FL server), 4, 7, 8. Build context is the repo root because Modules 7 and 8 import sibling modules. Non-root user. Module 1 runs `alembic upgrade head` on start. |
| `docker-compose.yml` | Draft stack: Postgres, auth, validation, admin, synthesis, dashboard; FL server behind the `federation` profile. All secrets are required, none have defaults. `deploy/compose.env.example` lists them. |
| CI | `.github/workflows/ci.yml`: per-module pytest matrix, root integration tests, dashboard build. |
| Compliance write-up | `docs/COMPLIANCE.md` (HIPAA/GDPR/IRB mapping, 9 named gaps, claims the demo must not make). |
| Frontend | Dashboard builds; upload → record select → synthesize → SHAP/explanation flow is wired with error panels (incomplete data, not validated, specialist unavailable). Added favicon, robots.txt (noindex), title without em dash. |
| Tests | Added `tests/test_requirements_cover_siblings.py`. |

## Bug found and fixed

`module8-synthesis/requirements.txt` omitted `lightgbm` and `pandas`, which
Module 6 imports at load time. A clean install failed at test collection; it
passed on machines that happened to have them. Fixed and verified in a fresh venv
(27 passed). The new test prevents regression.

## Audit after update (standing rule)

Test results, run after all changes: M1 149, M2 38, M3 15, M5 6, M6 13, M7 21,
M8 27, root 14. **283 passed, 0 failed.**

Open findings, by priority:

1. **Not verified:** Docker images and compose were not built or run (no Docker
   here); YAML parses only. Do `docker compose up --build` once before Oct 7.
2. **Module 7 in a container:** `/rounds/trigger` spawns `simulate.py` from Module 3,
   but the Module 7 image has no Module 3 dependencies (flwr, pandas). That
   endpoint will fail in compose. Either install them or trigger via the
   `fl-server` service.
3. **Checklist, not done:** Privacy Policy and Terms pages (need real legal
   text, deliberately not invented), cookie notice, custom 404, OG image,
   sitemap, Lighthouse run, alt-text review, contrast check.
4. **Checklist, partial:** em dashes remain in about 20 UI strings (titles,
   badges, helper text); the "—" used as an empty-value placeholder in data
   cells is a separate case.
5. **Repo hygiene:** the uploaded archive contained 8 `.db`/`.pyc` files despite
   `.gitignore`. They are empty/compiled, but remove them from git history.
   `module3-fedlearning/seed_uci_heart.py` hardcodes a demo password
   (`uci-seed-demo-password`); acceptable for demo seeding, must never reach staging.
6. **Unchanged known risks:** see SECURITY.md and COMPLIANCE.md §3.
