# Security model

## Human authentication

Module 1 hashes passwords with bcrypt and issues HS256 JWTs signed with
`FEDMED_JWT_SECRET`. Login also sets the `fedheal_token` httpOnly cookie.
The React app keeps only an in-memory access token and uses
`credentials: include`; it does not persist JWTs in localStorage.

Roles are `super_admin`, `hospital_admin`, and `clinician`. Public registration
is disabled unless `FEDHEAL_ALLOW_PUBLIC_REGISTRATION=true`.

## Service authentication

Internal calls use `X-Service-Key` containing a short-lived HS256 service JWT.
Claims include issuer `fedheal-service`, caller (`sub`), audience (`aud`),
expiry, issue time, id, and optional hospital scope (`hid`). Each hop has a
separate signing key. Missing/invalid/expired credentials produce 401; valid
credentials with a wrong caller/audience or hospital scope produce 403.

## Tenant isolation

The hospital id for human requests comes from the verified JWT, not a client
field. Module 1 routes and repository queries check `hospital_id` for cases,
history, vitals, scans, analyses, reviews, doctors, and exports. Module 3
tokens are scoped to one hospital. Module 8 forwards the caller's token when
reading Module 1 data. Module 7 stores aggregate platform data and proxies
hospital identity to Module 1.

Firestore client rules deny all direct reads/writes. This is an additional
boundary, not a replacement for application-level tenant checks.

## Limits and browser controls

The shared upload limits include, by default, 5 MiB JSON, 5 MiB CSV, 5,000
records, 50 fields per record, and 256 characters per field. Limits are
configurable with `FEDHEAL_MAX_JSON_BODY_BYTES`, `FEDHEAL_MAX_CSV_BYTES`,
`FEDHEAL_MAX_RECORDS`, `FEDHEAL_MAX_RECORD_FIELDS`, and
`FEDHEAL_MAX_FIELD_CHARS`. Oversized inputs return 413.

Login has an in-memory sliding-window limiter. It is per process and is not a
shared distributed limiter. CORS origins come from
`FEDHEAL_DASHBOARD_ORIGIN`; wildcards are rejected and non-local deployments
must use HTTPS origins. Secure cookies are forced outside development/test.

## Validation and audit

Module 2 rejects forbidden identifying keys before schema parsing, checks
plausibility and cross-field consistency, optionally requires labels, and
batch-flags statistical outliers. Module 1 and Module 2 contain audit
helpers. Module 7 receives count/reason summaries rather than raw flagged
records. Rejection records are not stored as an independently queryable
patient-level rejection log.

## Secrets and known gaps

Use placeholders in documentation and generate real values with a local
secrets generator. Outside development/test, `FEDHEAL_ENV` requires
non-placeholder secrets of at least the configured minimum length. The
repository uses `.env.example` files; a production secrets manager is not
implemented.

Known gaps verified from code:

- service keys are shared configuration values, not managed by a secrets
  manager;
- login rate limiting is in-memory;
- secure aggregation and a formal DP guarantee are absent;
- Compose Flower transport is plaintext by default;
- no production load, multi-machine, or real-Firestore security exercise was
  verified here;
- uploaded scans are stored as metadata/files but no validated imaging model
  analyzes their bytes.
