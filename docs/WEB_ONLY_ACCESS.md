# Website-only accounts

Hospital admins (`hospital_admin`) and doctors (`clinician`) can use FedHeal only through the dashboard.
Platform admins (`super_admin`) are not restricted, because they create hospitals and hospital admins through the API.

## What is enforced
- **Origin check.** Every request from these roles, and their login, must carry an `Origin` header that matches
  `FEDHEAL_DASHBOARD_ORIGIN`. Browsers add it to dashboard calls and a web page cannot change it. Requests from
  `/docs`, curl, scripts or another website get `403` and an `authz.web_only` audit event. Module 1 (auth) and
  Module 8 (synthesis) both enforce it; Module 8 passes the dashboard origin on when it calls Module 1 for the user.
- **No login from scripts.** `POST /token` refuses these roles without the dashboard origin, so no token is issued.
- **API docs hidden.** `/docs` and `/openapi.json` exist in development/test only. In staging/production set
  `FEDHEAL_ENABLE_API_DOCS=true` to turn them back on (the platform admin has no screen for creating hospitals yet).

## What is not enforced
A command-line client that knows valid credentials can still send a forged `Origin` header. Stopping that needs
network controls (VPN, IP allow-list, mTLS), not application code.

## Tests
`server/auth/test_web_only.py`. Module 8's check was exercised by hand only.
