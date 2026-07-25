# Module 4 — Hospital Dashboard

Deliberately plain: one HTML file, no build step, no framework — the goal
this sprint is wiring a real login + status request to Module 1's API, not
visual polish. Swap this for the real React/Next.js dashboard once the API
contract (see Module 1's README) is stable and you don't want to keep
rewriting fetch calls through a build pipeline.

## Run it

1. Start Module 1's auth API first (`cd ../module1-auth && uvicorn main:app --port 8001`).
2. Create a hospital + user against it (see Module 1's README for the curl commands),
   or just use the pre-filled `doc@general.com` / `hunter2` if you followed that README exactly.
3. Serve this folder:
   ```bash
   cd module4-dashboard
   python -m http.server 8080
   ```
4. Open http://localhost:8080 — log in, see `/me` and `/training-status` rendered.

## Why plain HTML/JS for now

No npm install, no build step, nothing to get out of sync with Module 1's
API while it's still changing shape day to day. `AUTH_API_BASE` at the top
of `index.html`'s `<script>` is the only thing you'll need to change if the
auth service moves.

## Next sprint (not yet done here, on purpose)

- Rebuild in React/Next.js once the team is ready to invest in a real
  frontend stack (per the original proposal).
- Replace `localStorage` token storage with something not readable by any
  injected JS (httpOnly cookie set by the server) before this touches real
  hospital data.
- Render Module 3's real per-round training status instead of Module 1's
  `FAKE_TRAINING_STATUS_DB` placeholder.
- Add the upload flow for Module 2's validation endpoint (CSV/JSON vitals upload).
