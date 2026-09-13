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
  routing between the federation map and system map.
- `src/api.js` — thin fetch wrappers for Module 1 (`authApi`) and Module
  7 (`adminApi`) endpoints, plus a shared `ApiError` class.
- `src/components/LoginGate.jsx` — the login form.
- `src/components/TopHUD.jsx` — the persistent top bar (hospital/role
  identity, refresh/trigger-round controls).
- `src/components/FederationMap.jsx` — the spatial view: hospitals as
  nodes orbiting the shared model, live status.
- `src/components/SystemMap.jsx` — the architecture view of all 8
  modules, shown to super-admins.
- `src/components/RoundsRail.jsx` — round-by-round training history
  (accuracy over time).
- `src/components/DetailDrawer.jsx` — the per-hospital detail panel; this
  is what actually renders `UploadPanel` and `FlaggedReview` when a
  hospital node is selected.
- `src/components/UploadPanel.jsx` — the vitals upload form (JSON/CSV),
  calling Module 1's upload endpoints.
- `src/components/FlaggedReview.jsx` — lists a hospital's flagged
  records and lets an admin clear them (calls Module 1's
  `/vitals/{id}/review`).
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

## How it depends on / is depended on by other modules

- **Calls:** Module 1 (login, upload, flagged-record review, training
  status, hospital list) and Module 7 (overview, round history — only
  for `super_admin` role).
- **Depended on by:** nothing downstream — this is the top of the stack,
  the thing a human actually looks at.

## Known limitations / current status

- No automated (Playwright/Cypress) end-to-end tests yet.
- No error boundaries around the map components — a malformed API
  response can blank the relevant panel rather than showing a friendly
  fallback.
- Accessibility (label associations, focus management) hasn't had a
  dedicated pass yet.
- Defaults assume `localhost` API URLs; a staging/production `.env` needs
  to be created and wired into the deployment pipeline.
