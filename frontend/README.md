# AI Campaign Orchestration Frontend

React/Vite UI prototype for the GM-facing campaign orchestration app.

## Flow implemented

- Login page
- After-login campaign dashboard
  - Campaigns you own
  - Campaigns shared with you
  - Campaigns you are running
- Campaign workspace after selecting/opening a campaign
  - Campaign Overview
  - World Builder with all 18 requested category tabs
  - Session Prep
  - Session Notes
  - GM Review Queue
  - Canon Browser
  - Settings

The UI no longer shows a raw JSON preview to the user. Users enter normal form data; the backend will generate separate session JSON documents behind the scenes. Session 0 is initial world setup, and Session 1+ documents represent later play sessions or update submissions.

## Commands

```bash
npm install
npm test
npm run build
npm run dev -- --port 5173
```

## Connect the development API

The UI calls its `/v1` API client for all campaign, entry, prep, note, review,
and canon interactions. MSW mocks are enabled by default for UI-only work.

To use the FastAPI development backend instead, start it from the repository
root in one terminal:

```bash
backend/.venv/bin/uvicorn backend.app:app --reload --port 8000
```

Then copy `.env.example` to `.env` (or export `VITE_USE_MOCKS=false`) and run
the Vite app normally. Vite proxies `/v1` to port 8000. Campaigns can be
persisted in PostgreSQL using the repository-root setup in `README.md`; the
remaining workspace state and development jobs are still in memory, and the
real LLM worker is the next production implementation step.
