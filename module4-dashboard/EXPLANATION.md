# Module 4 — Hospital Dashboard: Full Explanation

## What this module is for

This is what a clinician or hospital admin actually sees and clicks on.
Everything the other modules do — validating data, training models,
tracking rounds — is invisible unless there's a real interface for a
hospital user to log in, upload their data, and see what's happening with
their own hospital's status. That's this module's job.

## How it works

A single HTML file with inline JavaScript — no framework, no build step.
That's a deliberate choice for this stage, not an oversight: while
Module 1's API contract was still changing week to week, adding a
React/Next.js build pipeline on top would have meant constantly rewriting
generated code to match. Plain `fetch()` calls against Module 1's API were
faster to keep in sync and easier for a non-frontend-specialist teammate to
read.

The page has three states:

1. **Login** — a form that posts to Module 1's `/token` endpoint (which
   expects an OAuth2 password form, not JSON — the page handles that
   translation) and stores the returned JWT.
2. **Status** — once logged in, calls `/me` (who am I, what hospital, what
   role) and `/training-status` (how many validated records does my
   hospital have, is it ready for a training round) and renders both.
3. **Upload vitals** *(added during the data-flow integration sprint)* —
   a form where a hospital user pastes a JSON array of vitals records and
   clicks "Validate & upload." That call goes to Module 1's
   `POST /vitals/upload`, which forwards to Module 2 for the real
   validation rules and stores whatever passes. The page shows exactly how
   many records passed, were flagged, or were rejected, then refreshes the
   status panel so the "validated records" count updates live.

## How other modules depend on it

This module is a pure client — nothing else in the system depends on it.
It depends entirely on Module 1's API (login, status, upload), which in
turn depends on Module 2 (validation) behind the scenes.

## What's real vs. what's a known prototype simplification

Real: the full login → status → upload flow, all wired to Module 1's
actual API, not mocked data. Documented as next-sprint work in this
folder's `README.md`: this needs a real frontend rebuild
(React/Next.js) once the team is ready to invest in that stack; the JWT
is stored in `localStorage`, which is fine for local development but
readable by any injected JavaScript — before this touches real hospital
data it needs to move to an httpOnly cookie set by the server; and the
upload form takes pasted JSON rather than a real file picker/CSV upload,
which is a reasonable demo shortcut but not a real clinician's workflow.
