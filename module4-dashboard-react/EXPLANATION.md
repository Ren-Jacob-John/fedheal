# Module 4 — Federation Map Dashboard: Full Explanation

## What this module is for

FedHeal's value proposition is spatial: patient data stays at each hospital,
and only model weights travel to a central aggregator. A conventional
form-and-table dashboard hides that fact. This module is the hospital-
facing (and, for `super_admin` users, operator-facing) interface that
makes the federation literal — every hospital as a node orbiting the shared
global model, with animated beams showing the *only* thing that crosses
institutional boundaries.

It replaced an earlier plain-HTML `module4-dashboard/` once this React
version was confirmed fully wired to Module 1 and Module 7's real APIs.

## How it works

Built with **React + Vite** as a client-only SPA:

- **`api.js`** — thin `fetch` wrappers for Module 1 (auth, hospitals,
  training status, vitals upload) and Module 7 (overview, rounds, flags,
  trigger-round, hospital activate/deactivate). No server-side rendering;
  every gate is enforced by the APIs first, and the UI simply doesn't
  render data it was never going to receive.
- **`App.jsx`** — session state (JWT in `localStorage`), polling for live
  federation status, view switching between the orbital map and the static
  architecture diagram, and super_admin-only admin data loading.
- **`FederationMap.jsx`** — the core spatial visualization: hospitals in
  orbit, distance reflecting validated-record count, color reflecting
  training readiness, animated weight beams during active rounds.
- **`SystemMap.jsx`** — a static diagram of all eight modules and what
  crosses each boundary (JWT, validated records, weights-only, synthesis
  report).
- **`DetailDrawer.jsx` / `UploadPanel.jsx`** — per-hospital detail and
  vitals upload form, scoped to the logged-in user's hospital.
- **`RoundsRail.jsx` / `TopHUD.jsx`** — federated-round timeline and
  operator overview stats for `super_admin`.

## What's role-gated, and why

| Data | Visible to |
|---|---|
| Hospital directory (name, active/inactive) | Everyone — `GET /hospitals` on Module 1 is public by design |
| A hospital's own record count / status | That hospital's users, or `super_admin` |
| Overview, rounds, flags, trigger-round | `super_admin` only — Module 7 endpoints |
| Vitals upload | Logged-in users, for their own hospital only |

The UI never invents access the API doesn't grant.

## How other modules depend on it

- **Module 1** is the primary backend: login, profile, vitals upload,
  training status, hospital directory.
- **Module 7** supplies the operator slice: platform overview, round
  history, validation-flag summaries, federated-round trigger, hospital
  activate/deactivate (proxied through Module 7 to Module 1).
- **Module 8** (synthesis) is **not yet wired** — review packets from
  condition routing will eventually render here; `SystemMap.jsx` shows that
  edge as "planned."

## What's real vs. what's a known prototype simplification

Real: login, federation map, vitals upload, training-status display,
super_admin operator views (overview, rounds rail, trigger-round with
honest async polling), hospital activate/deactivate, architecture diagram
with all eight modules.

Documented as next-sprint work in this folder's `README.md` and
`docs/16-week-development-plan.md` week 14: CSV upload (JSON paste only
today), SHAP/Grad-CAM chart rendering from Module 6 explainer output,
Module 8 synthesis report rendering, and httpOnly-cookie token storage
instead of `localStorage` (week 13 security hardening).
