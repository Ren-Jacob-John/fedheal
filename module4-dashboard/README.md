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
- The upload form takes pasted JSON, not a CSV file picker — fine for a
  demo, not for a clinician's actual workflow. Add real file upload once
  Module 2's CSV support (if any) is decided.

## Done this sprint (previously listed here as not-yet-done)

- Real per-hospital training status: `renderTrainingStatus` now shows
  Module 1's actual `records_available` / `status` / `last_upload`, not
  the old `FAKE_TRAINING_STATUS_DB` shape.
- Vitals upload flow: the "Upload vitals" section posts a pasted JSON
  array to Module 1's `POST /vitals/upload`, which validates via Module 2
  and stores passed/flagged records — see `module1-auth/README.md`.
