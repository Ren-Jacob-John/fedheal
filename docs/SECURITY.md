# FedHeal security model

Scope: the P0 hardening pass. Everything here reuses the platform's one login
system (Module 1's JWT, `require_role`) and its existing service-to-service
pattern (the `X-Service-Key` header). No second authentication system was
added.

## Identities

| Identity | Credential | Where verified |
|---|---|---|
| Human user (clinician / hospital_admin / super_admin) | Module 1 JWT — httpOnly cookie for the dashboard, or `Authorization: Bearer` | Module 1 issues; Modules 7 and 8 verify with the same `FEDMED_JWT_SECRET` |
| Service, hospital-scoped | Signed service token in `X-Service-Key` (HS256, claims: `sub` caller, `aud` endpoint, `hid` hospital, `exp`). One signing key **per hop** | `service_auth.py` |
| Service, unscoped ingest (M2→M7, M3→M7) | Static per-hop key in `X-Service-Key`, compared in constant time | Module 7 |

Failure semantics everywhere: missing / malformed / forged / expired → **401**;
authenticated but wrong role, wrong service, wrong endpoint or wrong hospital →
**403**. A user JWT is never accepted as a service credential, or vice versa.

## Endpoint access table

| Endpoint | Caller | Authentication | Authorization | Tenant scope | Public / Internal |
|---|---|---|---|---|---|
| M1 `GET /health` | probes | none | — | none | Public |
| M1 `POST /register` | new user | none (self-registration) | role forced to `clinician` | user picks a hospital id | Public *(see risks)* |
| M1 `POST /token`, `POST /logout` | user | credentials / cookie | — | — | Public |
| M1 `GET /me` | user | JWT | any role | own | Public API (authenticated) |
| M1 `POST /hospitals` | super_admin | JWT | `require_role(SUPER_ADMIN)` | platform | Public API (admin) |
| M1 `PATCH /hospitals/{id}` | super_admin | JWT | `require_role(SUPER_ADMIN)` | platform | Public API (admin) |
| M1 `GET /hospitals` | any logged-in user, or Module 3 | JWT **or** scoped service token | any role; service token limited to its `hid` (only the operator's directory-audience token sees all) | directory (id, name, active, requires_label) | Public API (authenticated) |
| M1 `POST /admin/users` | super_admin | JWT | `require_role(SUPER_ADMIN)` | platform | Public API (admin) |
| M1 `POST /vitals/upload`, `/vitals/upload/csv` | clinician / hospital_admin | JWT | hospital-bound user; hospital active | own hospital (from JWT) | Public API |
| M1 `GET /vitals/flagged` | any hospital-bound user | JWT | user must belong to a hospital (unchanged) | own hospital (from JWT) | Public API |
| M1 `POST /vitals/{id}/review` | hospital_admin / super_admin | JWT | `require_role`; body `decision` ∈ {approve, reject} else 422; other hospital's record → 403 | own hospital | Public API |
| M1 `GET /docs` | anyone | none | — | none | Public (API docs page; see risks) |
| M1 `GET /training-status` | user | JWT | any role | own hospital | Public API |
| M1 `GET /vitals/export` | Module 3 | scoped service token (`aud=module1:vitals-export`, `sub=module3`) | `hid` in token must equal `hospital_id` query param, else 403; wildcard never valid | **one hospital per token** | **Internal** |
| M2 `POST /validate/vitals`, `/validate/vitals/csv` | Module 1 | scoped service token (`aud=module2:validate`, `sub=module1`), minted per upload from the uploader's JWT hospital | body/form `hospital_id`, if sent, must equal token `hid` (else 403); token must be single-hospital | **from token** | **Internal** |
| M2 `GET /health` | probes | none | — | none | Internal |
| M7 `GET /admin/rounds`, `/admin/flags`, `/admin/overview`, `PATCH /admin/hospitals/{id}`, `POST /admin/rounds/trigger` | super_admin | JWT (cookie or bearer) | role must be `super_admin` | platform | Public API (admin) |
| M7 `POST /admin/flags` | Module 2 | signed token (`FEDHEAL_SVC_SIGNING_KEY_M2_M7`, aud `module7:flag-report`, 60 s) | caller + audience + expiry | **hospital-scoped**: token `hid` must equal the flag's hospital, else 403 | **Internal** |
| M7 `POST /admin/rounds`, `POST /admin/models/candidates` | Module 3 | signed token (`FEDHEAL_SVC_SIGNING_KEY_M3_M7`, aud `module7:round-report` / `module7:model-candidate`) | caller + audience + expiry | platform-level aggregates only (`hid="*"`) | **Internal** |
| M7 `GET /admin/models/promoted` | Module 8 | signed token (`FEDHEAL_SVC_SIGNING_KEY_M8_M7`, aud `module7:promoted-model`) | caller + audience + expiry | platform-level (weights + provenance, no patient data) | **Internal** |
| M1 `GET /vitals` | any hospital-bound user | JWT | hospital from JWT only (no hospital parameter); super_admin without a hospital → 400 | own hospital | Public API |
| M1 `GET /vitals/{id}` | any user (Module 8 forwards the user's own JWT) | JWT | other hospital's record → 403 + `cross_tenant.attempt` audit | own hospital | Public API |
| M8 `POST /synthesize/record` | any logged-in user | JWT (cookie or bearer); forwarded to Module 1 to read the record | tenancy decided by Module 1; only `passed` records | own hospital (via Module 1) | Public API (authenticated) |
| M8 `GET /models/status` | any logged-in user | JWT | any role | none (model metadata) | Public API (authenticated) |
| M8 `POST /synthesize/heart_disease` | — | JWT | — | — | Retired: always 410 (manual feature entry removed) |

**Module 5 → 6 and 6 → 8 are not network calls.** Modules 5 and 6 are
in-process libraries (`registry.py`, `condition_router.py`) imported by
Module 8; they expose no HTTP endpoints, so there is nothing to authenticate
between them. Module 8's single endpoint is the only door.

**Module 7 → other services:** Module 7 forwards the *caller's own* JWT to
Module 1 (`hospitals_client.py`); it holds no service credential of its own.

## Tenant isolation, concretely

The vulnerability: Module 3's one shared key authorised `GET /vitals/export`
for *any* `hospital_id` the caller typed.

The fix: a token now carries the hospital (`hid`). Module 1 takes the hospital
**from the token**, and treats the `hospital_id` query parameter only as a
claim to check against it. There is no all-hospitals export token — the minting
function refuses one, and Module 1 rejects a wildcard even if one were forged
with the right key.

* A hospital's own Module 3 client holds a token minted for it
  (`module1-auth/mint_service_token.py --hospital-id <id>`), delivered as
  `FEDHEAL_SVC_TOKEN_M3_M1`.
* The central operator's pooled simulation holds the signing key and mints one
  short-lived token per hospital. That key must never reach a hospital machine.
* Rotating `FEDHEAL_SVC_SIGNING_KEY_M3_M1` revokes every outstanding token.

## Configuration and secrets

`FEDHEAL_ENV` = `development | test | staging | production`. **Unset is treated
as production.** In staging/production every service refuses to start if a
required secret is missing, shorter than 32 characters, or looks like a
placeholder; `FEDHEAL_DASHBOARD_ORIGIN` must be set with `https://` origins;
the session cookie is always `Secure`. Development falls back to clearly named
`dev-only-…` values and logs a warning naming the *variable* (never the value).

| Variable | Used by |
|---|---|
| `FEDMED_JWT_SECRET` | M1, M7, M8 |
| `FEDHEAL_SVC_SIGNING_KEY_M3_M1` | M1 (verify), M3 operator (mint) |
| `FEDHEAL_SVC_TOKEN_M3_M1` | one hospital's M3 client (pre-minted, hospital-scoped) |
| `FEDHEAL_SVC_SIGNING_KEY_M1_M2` | M1 (mint), M2 (verify) |
| `FEDHEAL_SVC_SIGNING_KEY_M2_M7` | M2 → M7 |
| `FEDHEAL_SVC_SIGNING_KEY_M3_M7` | M3 → M7 |
| `FEDHEAL_SVC_SIGNING_KEY_M8_M7` | M8 → M7 |
| `FEDHEAL_DASHBOARD_ORIGIN` | M1, M7, M8 (CORS) |

The old `FEDHEAL_SVC_KEY_M3_M1` is retired; setting it now only logs a warning.

## CORS

Explicit origins from `FEDHEAL_DASHBOARD_ORIGIN` (never `*`; credentialed
requests), methods limited to what each service's browser callers use
(M1/M7: GET, POST, PATCH; M8: GET, POST), headers limited to `Authorization`
and `Content-Type`. Module 2 grants **no** browser CORS — browsers never call it.

## Request limits

Defaults (env-tunable): 5 MiB JSON body, 5 MiB CSV, 5,000 records, 50 fields per
record, 256 characters per string field. Oversize → **413**. The body-size check
runs as ASGI middleware before the body is parsed; it also counts streamed bytes
when no `Content-Length` is sent. Module 1 rejects before forwarding to Module 2.

## Audit log

One JSON line per event on the `fedheal.audit` logger (stdout by default). Fields
are an allow-list — anything else passed is dropped — so passwords, JWTs, keys,
e-mail addresses and patient values cannot be logged by accident. Login failures
record a 12-character hash of the login name, not the name.

Events: `hospital.create`, `hospital.update`, `admin.user_create`, `login`
(success/failure/rate_limited), `authn.failure`, `authz.denied`,
`service_authn.failure`, `cross_tenant.attempt`, `vitals.upload`,
`vitals.upload_csv`, `vitals.export`, `vitals.review`, `validate`,
`validate_csv`, `rounds.trigger`, `synthesis.run`.

## Known remaining risks

See the final report of the hardening task; the main ones are listed there
(open self-registration, static M2→M7 / M3→M7 keys with no tenant scope,
in-memory login rate limiting, no revocation list for individual tokens).

## P0 clinical-workflow additions (2026-10-06/07)

| Control | State |
|---|---|
| Public self-registration | **Closed by default** (`FEDHEAL_ALLOW_PUBLIC_REGISTRATION=true` re-opens it, development only). Onboarding: super_admin → hospital + hospital_admin → hospital_admin creates doctors |
| Doctor creation by hospital_admin, own hospital only (foreign `hospital_id` → 403 + audit) | Implemented, tested |
| Disabled accounts: login refused and existing tokens rejected | Implemented, tested |
| Cases / history / scans / case vitals / reviews scoped to the caller's hospital; other hospital → 403 + `cross_tenant.attempt` audit | Implemented, tested both directions on every sub-resource, and across the real M1/M2/M8 services |
| Admins have no patient-level access (clinical data is `clinician` only) | Implemented, tested |
| Service-to-service: scoped signed tokens for M2→M7 (per hospital), M3→M7, M8→M7; static shared keys removed | Implemented, tested (wrong key, wrong audience, expiry, hospital mismatch) |
| Audit events carry ids only (no history/note/vitals/scan content) | Implemented, tested |
| Scan upload: extension allow-list, magic-byte sniffing, declared-MIME check, size cap, server-generated paths, hospital-scoped, ids-only audit | Implemented, tested; files are stored unencrypted on local disk |
| Registry refuses raw-data-shaped payloads and verifies weights against their hash | Implemented, tested |
| Demo model only behind an explicit flag, labelled NON-CLINICAL | Implemented, tested |

Known gaps: no rate limiting beyond `/token`; no malware scanning or image re-encoding of uploads;
`/cases/*` JSON bodies are bounded by field validation rather than the body-size middleware;
scans are not encrypted at rest; TLS is not implemented (see FEDERATED_PRIVACY.md); the bootstrap
super_admin password is passed via environment; no password reset flow.
