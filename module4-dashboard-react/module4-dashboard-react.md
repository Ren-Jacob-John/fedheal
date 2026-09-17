# Module 4 — Hospital Dashboard (React)

## What this module is for

The human-facing interface: what a hospital admin or clinician uses to
log in, upload vitals, review flagged records, and see their hospital's
status — and what a platform super-admin uses to see the whole
federation (every hospital as a node orbiting the shared model), round-
by-round training history, and an architecture view of all eight
modules.

This React + Vite app replaces an earlier plain-HTML `module4-dashboard/`
(removed after confirming full feature parity against Modules 1 and 7) —
this is now the single supported dashboard going forward.

## How it works internally

**Files:**
- `src/App.jsx` — top-level state and orchestration: auth bootstrap
  (checks `/me` against the httpOnly cookie on load, regardless of
  in-memory token state), polling loop (`POLL_MS = 12000`), and view
  routing between the federation map, system map, and (new in Sprint B)
  the synthesis view.
- `src/api.js` — thin fetch wrappers for Module 1 (`authApi`), Module 7
  (`adminApi`), and (new in Sprint B) Module 8 (`synthesisApi`)
  endpoints, plus a shared `ApiError` class.
- `src/components/LoginGate.jsx` — the login form.
- `src/components/TopHUD.jsx` — the persistent top bar (hospital/role
  identity, view tabs, refresh/trigger-round controls).
- `src/components/FederationMap.jsx` — the spatial view: hospitals as
  nodes orbiting the shared model, live status.
- `src/components/SystemMap.jsx` — the architecture view of all 8
  modules, shown to super-admins.
- `src/components/RoundsRail.jsx` — round-by-round training history
  (accuracy over time).
- `src/components/DetailDrawer.jsx` — the per-hospital detail panel; this
  is what actually renders `UploadPanel` and `FlaggedReview` when a
  hospital node is selected. Only shown in the federation-map view.
- `src/components/UploadPanel.jsx` — the vitals upload form (JSON/CSV),
  calling Module 1's upload endpoints.
- `src/components/FlaggedReview.jsx` — lists a hospital's flagged
  records and lets an admin clear them (calls Module 1's
  `/vitals/{id}/review`).
- `src/components/SynthesisView.jsx` (new in Sprint B) — the Module 8
  view: a case-entry form (the `vitals` specialist's own 8 features),
  calls `POST /synthesize/heart_disease`, and renders the resulting
  `SynthesisReport` — disclaimer, urgent-review flags, one card per
  specialist finding with a visible stub badge when a finding came from
  a placeholder model, missing-input list, and the
  `requires_clinician_review` line. Available to any logged-in user, not
  just super_admin — this is a per-case clinical tool, not an admin
  action.
- `src/components/ShapChart.jsx` (new in Sprint B) — a diverging SVG bar
  chart of one finding's SHAP per-feature contributions (positive =
  pushed the prediction toward the predicted class, negative = pushed
  away from it). No charting library added for this — see package.json;
  one dimension of data didn't justify the dependency.
- `src/styles/` — `tokens.css` (design tokens), `global.css`, `app.css`.

**Auth model:** the JWT is **not** kept in `localStorage` anymore (a past
design that was readable by any JS on the page, including an XSS
payload). Session persistence now comes entirely from the httpOnly
cookie Module 1 sets on login; the in-memory `token` state in `App.jsx`
is only used for the current tab's API calls, and a bootstrap effect
re-checks `/me` on every load regardless.

## How to run it

```bash
cd module4-dashboard-react
npm install
cp .env.example .env.local     # point at your running Module 1 / Module 7
npm run dev                    # http://localhost:5173
```

Production build: `npm run build` (outputs to `dist/`); preview with
`npm run preview`.

**Environment variables** (`.env.example`):
- `VITE_AUTH_API_BASE` — where Module 1 is reachable (default
  `http://localhost:8001`).
- `VITE_ADMIN_API_BASE` — where Module 7 is reachable (default
  `http://localhost:8005`).
- `VITE_SYNTHESIS_API_BASE` (new in Sprint B) — where Module 8's new HTTP
  service is reachable (default `http://localhost:8006`).

## How it depends on / is depended on by other modules

- **Calls:** Module 1 (login, upload, flagged-record review, training
  status, hospital list), Module 7 (overview, round history — only for
  `super_admin` role), and (new in Sprint B) Module 8 (synthesis for the
  `heart_disease` condition — any logged-in role).
- **Depended on by:** nothing downstream — this is the top of the stack,
  the thing a human actually looks at.

## Known limitations / current status

- The synthesis view (Sprint B) only supports the `heart_disease`
  condition, entered as the vitals specialist's own 8 raw features — it
  does not (yet) pull from a hospital's already-uploaded/flagged
  records, because Module 1's stored vitals-upload schema and the
  model's feature space aren't reconciled (see
  `docs/DEVELOPMENT_PLAN.md`'s Sprint A risk register). Wiring "pick an
  existing record" instead of hand-entering values is a natural Sprint C
  follow-on once that schema gap closes.
- The Grad-CAM explainer / imaging conditions have no UI yet — deferred
  per `docs/DEVELOPMENT_PLAN.md` section 4, item 4 (no real imaging
  output to visualize until a real specialist replaces the current
  stubs).
- No automated (Playwright/Cypress) end-to-end tests yet.
- No error boundaries around the map components — a malformed API
  response can blank the relevant panel rather than showing a friendly
  fallback.
- Accessibility (label associations, focus management) hasn't had a
  dedicated pass yet.
- Defaults assume `localhost` API URLs; a staging/production `.env` needs
  to be created and wired into the deployment pipeline.
