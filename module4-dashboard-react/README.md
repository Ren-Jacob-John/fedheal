# Module 4 — Federation Map

The project's one hospital dashboard, built in React + Vite. Log in,
upload vitals, see your hospital's status — plus a live view of the whole
federation for the platform operator, fully wired to Module 1 and
Module 7's real APIs.

## Why spatial

FedHeal's entire value proposition is a spatial fact: patient data stays
put, only model *weights* travel, and they only travel to one place. A
form-and-table dashboard hides that. This UI makes it literal:

- **Federation map** — every hospital is a node in orbit around the shared
  global model (the core). Distance in isn't decorative: hospitals with
  more validated data sit closer to the core they're actively training.
  Node color is live status (teal = ready for training, amber =
  collecting data, coral = inactive). A thin animated beam runs from each
  active hospital in to the core — that beam is the *only* thing this UI
  ever implies crosses the line, on purpose, because that's the only thing
  that actually does.
- **Round pulses** — triggering a federated round sends a ring of light
  outward from the core, the same way the newly-averaged global model
  actually gets broadcast back out to every hospital.
- **Rounds rail** — federated rounds plotted as a small spatial timeline
  (bar height = global accuracy) instead of a plain table, so an
  improving trend is something you see, not something you read.
- **Architecture view** — a second, static spatial map of all eight
  modules and exactly what crosses each line between them (a JWT, a
  validated record, weights-only, synthesis report), for anyone trying to
  understand the whole system, not just the hospital-facing slice of it.
- **Privacy is visible, not just true** — a non-admin hospital user sees
  every other hospital as a real node in the federation (so it's obvious
  they're not alone), but those nodes carry no status, no record counts,
  nothing — because Module 1's API genuinely never sends that data to
  anyone outside that hospital. The UI can't leak what it was never given.

## Running it

Needs Module 1 (`:8001`) and, for the super-admin view, Module 7
(`:8005`) already running — see the repo root README.

```bash
cd module4-dashboard
npm install
cp .env.example .env.local   # only needed if you changed the default ports
npm run dev                  # http://localhost:5173
```

`npm run build` produces a static `dist/` you can serve however you like
— it's a client-only SPA.

## What's role-gated, and why

| Data | Visible to |
|---|---|
| Hospital directory (name, active/inactive) | Everyone — `GET /hospitals` on Module 1 has no auth, by design |
| A hospital's own record count / status / last upload | That hospital's own users, or the super admin |
| Overview stats, rounds history, validation flags, trigger-round | Super admin only — these live behind `require_super_admin` on Module 7 |
| Vitals upload | The logged-in hospital's own users, for their own hospital only |

The UI doesn't invent any access the API doesn't already grant — every
gate you see here is enforced server-side first; this app just doesn't
render UI for data it was never going to receive.

## Notes on the "trigger round" flow

`POST /admin/rounds/trigger` kicks off `simulate.py` as a background
subprocess and returns immediately (see Module 7's own docstring). This
UI reflects that honestly: the button shows "round in progress" and polls
`/admin/rounds` every few seconds until a new round number shows up (or
gives up after ~75s), rather than pretending the round completed
synchronously.

## Files

```
src/
  api.js                 fetch wrappers for Module 1 + Module 7
  App.jsx                session state, polling, screen composition
  components/
    LoginGate.jsx         entry screen
    TopHUD.jsx             brand, role, live overview stats, view switch
    FederationMap.jsx      the orbital map (SVG)
    RoundsRail.jsx          bottom timeline of federated rounds
    DetailDrawer.jsx        right-hand panel for the selected node
    UploadPanel.jsx          vitals upload form (used inside the drawer)
    SystemMap.jsx           static architecture view of all 7 modules
  styles/
    tokens.css              design tokens (color, type, spacing)
    global.css               resets + shared motion/utility classes
    app.css                   component styles
```
