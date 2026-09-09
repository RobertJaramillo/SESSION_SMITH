# Session Smith

Session Smith is an AI-assisted campaign copilot for tabletop role-playing game
masters. It helps a GM build a campaign world, turn session notes into proposed
canon updates, review those proposals, and generate session-prep drafts from
approved campaign memory.

The core rule is simple: **the AI can propose; the GM decides what becomes
canon.** Raw notes, pending proposals, and approved canon are kept separate.

## What you can do

- Create and organize campaigns in a GM-facing workspace.
- Build a world across 18 categories, then review and seal it.
- Submit session notes and receive proposed canon updates.
- Approve, edit, or reject proposals before they affect campaign memory.
- Generate and approve session-prep drafts using approved canon.
- Export a sealed world's canon as Markdown or PDF.

## Stack

- React + Vite frontend
- FastAPI (Python) backend
- PostgreSQL for durable campaign data
- Docker Compose for the local full stack
- A provider-agnostic AI layer with an offline demo provider and optional OpenAI
  provider

## Quick start

### Prerequisites

Install and start [Docker](https://www.docker.com/products/docker-desktop/)
with Docker Compose v2. No API key is required for the default demo mode.

### Start the app

From the repository root, run:

```bash
./run
```

The script checks Docker, starts the Compose stack, applies migrations, and seeds
the demo campaign. Once it is ready, visit <http://localhost:8080>.

When prompted for an OpenAI API key, either enter one to use live AI generation
or press Enter to use the built-in, offline deterministic demo provider. The
key, if provided, is saved only to the gitignored `.env` file.

Useful lifecycle commands:

```bash
./run down    # stop the containers; retain PostgreSQL data
./run reset   # stop containers, remove the local database volume, and rebuild
docker compose logs -f api  # follow backend logs
```

`./run reset` permanently removes the local Docker database volume. Use it only
when you want a fresh local environment.

## Run the tests

Create the backend virtual environment once:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

Then run either the full suite or a single layer:

```bash
./test
./test backend
./test frontend
```

Tests use the offline demo provider and frontend mocks, so they do not make
live AI calls. Some PostgreSQL-backed backend tests self-skip unless
`DATABASE_URL` is configured.

## Local development without the full stack

For UI-only work, run the frontend with its default browser mocks:

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

For the FastAPI backend's in-memory development mode, use the virtual
environment created above:

```bash
backend/.venv/bin/uvicorn backend.app:app --reload --port 8000
```

To use PostgreSQL while developing outside Docker Compose, first start the
database and run the migrations:

```bash
docker compose up -d db
export DATABASE_URL='postgresql://campaign_app:change-me-local-only@localhost:5432/campaign_orchestration'
backend/.venv/bin/python -m backend.migrate
backend/.venv/bin/python -m backend.seed_demo
backend/.venv/bin/uvicorn backend.app:app --reload --port 8000
```

Then start Vite with the real API enabled; its development proxy forwards `/v1`
requests to port 8000:

```bash
cd frontend
VITE_USE_MOCKS=false npm run dev -- --port 5173
```

## AI providers

The default `LLM_PROVIDER=demo` mode is offline and deterministic. It is useful
for demos, development, and tests, but its generated content is intentionally
simple. To use OpenAI, set these values in `.env` or the environment:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
```

The `./run` helper can configure both values interactively. Do not commit `.env`
or API keys.

For the in-app private-beta experience, see [BYOK onboarding](docs/BYOK_ONBOARDING.md).
It explains the session-only OpenAI key flow, Gemini's current status, and why a
future hosted-AI subscription needs hard usage limits.

## Repository guide

| Path | Purpose |
| --- | --- |
| `frontend/` | React/Vite application and frontend tests |
| `backend/` | FastAPI API, AI workflows, migrations, and backend tests |
| `backend/evaluation/` | Evaluation pipeline, datasets, and reports |
| `docs/AI_ARCHITECTURE.md` | AI design: retrieval, prompting, validation, and GM review |
| `docs/DATA_MODEL.md` | Campaign-memory data model |
| `docs/KNOWN_LIMITATIONS.md` | Current gaps and scaling limits |
| `scripts/` | PostgreSQL backup, restore, and Markdown-to-PDF utilities |
| `session-notes/` | Example campaign session notes |

## Documentation note

`docs/SOFTWARE_ARCHITECTURE.md` describes a longer-term DigitalOcean deployment
target that uses Go services and a separate worker. The runnable code in this
repository currently uses Python/FastAPI and executes AI jobs through its
backend workflow implementation. Treat the code and `compose.yaml` as the
source of truth for local setup.

## License

See [LICENSE](LICENSE).
