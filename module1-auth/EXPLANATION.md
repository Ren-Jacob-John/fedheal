# Module 1 — Authentication & Multi-Tenancy: Full Explanation

## What this module is for

Every hospital that joins FedHeal needs its own private, walled-off
account: its own login, its own users, and — critically — a guarantee
that its data can never be queried by another hospital, even accidentally.
This module is that foundation. It is deliberately the first thing built,
because every other module in the system (validation, training, the
dashboard, the admin view) trusts *this* module's answer to one question:
**"which hospital does this request belong to?"** No other service is
allowed to answer that question by trusting a value the client sent — it
has to come from a JWT this module issued.

## How it works

A **hospital** is a tenant: a row in the `hospitals` table with a name and
an active/inactive flag. A **user** belongs to exactly one hospital (except
the platform operator, whose account isn't tied to any single hospital)
and has a role — `clinician`, `hospital_admin`, or `super_admin`.

When a user logs in (`POST /token`), the service checks their password and
issues a signed JWT containing three things: their user ID, their
`hospital_id`, and their `role`. Every other endpoint in this module — and
by convention, every endpoint in every other module — reads the
`hospital_id` out of that token rather than accepting one in the request
body or query string. That's the whole multi-tenancy guarantee in one
sentence: **a client can claim to be anyone in the request payload, but it
can't forge a JWT it doesn't have.**

## What it actually stores and exposes

- **Hospitals**: name, active status. `super_admin` can activate/deactivate
  a hospital (used by Module 7's operator view).
- **Users**: email, hashed password (bcrypt, never stored in plaintext),
  role, hospital ID.
- **Vitals records** *(added during the data-flow integration sprint)*:
  once a hospital uploads vitals through `POST /vitals/upload`, this
  module forwards them to Module 2 for validation and stores whatever
  passes (or gets flagged for review) against that hospital's ID. This is
  the table Module 3 reads from when it trains on real data instead of
  synthetic partitions.
- **Training status**: computed live from the stored vitals count — how
  many validated records a hospital has, and whether that's enough to be
  worth a federated round.

## How other modules depend on it

- **Module 2** (validation) doesn't call this module directly — this
  module calls *it*, forwarding upload payloads for the actual rule
  checks.
- **Module 3** (federated learning) calls `GET /vitals/export` (using a
  shared service key, not a human login) to pull a hospital's validated
  data for real federated training.
- **Module 4** (dashboard) is this module's primary client: every login,
  status check, and vitals upload the dashboard shows a clinician goes
  through this service's API.
- **Module 7** (admin) proxies hospital list/activate-deactivate straight
  through to here, because this is the only place that data actually
  lives — Module 7 deliberately doesn't duplicate it.

## What's real vs. what's a known prototype simplification

Real: password hashing, JWT issuance/verification, hospital-scoped data
isolation, the vitals upload→validate→store pipeline, DB-backed training
status, and — as of this sprint — a real Supabase/Postgres backend
(`FEDHEAL_DATABASE_URL` in `.env`, falling back to local SQLite if unset).
Prototype-level, documented in this folder's `README.md` "Next sprint"
section: no Alembic migrations yet (schema changes mean a fresh table
today, not a safe upgrade of existing data), no rate limiting on login
attempts, wide-open CORS (fine for local dev, not for a real deployment),
and no real diagnosis/outcome label on uploaded vitals yet — see
`module3-fedlearning/real_data.py` for how that gap is handled downstream.
