# Career Catalyst

Track every job application in one place, see how well each job matches your profile, and keep your
search moving: from saved, to applied, to interview, to offer.

> Work in progress. Jobs, applications and their stage history are tracked through a versioned REST API; job intake and matching are next.

## Architecture

```
apps/api   FastAPI service (Python 3.13, SQLAlchemy 2 async, PostgreSQL)
```

Layers inside the API: `route → service → repository`. Configuration comes from environment
variables through a typed settings object.

## Run it

```bash
docker compose up --build
curl localhost:8000/health   # {"status":"ok"}
curl localhost:8000/ready    # {"status":"ready","database":"up"}
```

API docs: http://localhost:8000/docs

| Method | Path | What it does |
|---|---|---|
| POST | `/api/v1/jobs` | Save a job posting (same URL twice → 409) |
| GET | `/api/v1/jobs`, `/api/v1/jobs/{id}` | List (paginated) or fetch postings |
| POST | `/api/v1/applications` | Start tracking a job (one application per job → 409) |
| GET | `/api/v1/applications`, `/api/v1/applications/{id}` | List or fetch applications |
| PATCH | `/api/v1/applications/{id}` | Update referral and notes (only the fields sent) |
| POST | `/api/v1/applications/{id}/transitions` | Move to the next stage, e.g. `{"to": "interview", "note": "Round 1"}` (not allowed → 422 listing the allowed stages) |
| GET | `/api/v1/applications/{id}/events` | Stage history, oldest first |

## Develop

```bash
cd apps/api
uv sync
docker compose up -d db
uv run pytest            # unit tests; integration tests run when DATABASE_URL is set
uv run ruff check . && uv run mypy src
```

## Design decisions

- **Separate liveness and readiness.** `/health` only says the process is alive, so an orchestrator restarts a hung
  container. `/ready` also checks PostgreSQL, so traffic is routed only when the service can actually serve it.
  Restarting a container because its database is down would make things worse, which is why the two are separate.
- **Lazy database engine.** The engine is created on first use, so importing the app for tests or tooling never
  opens a connection.
- **Uniqueness lives in the database.** "One posting per URL" and "one application per job" are unique constraints, not just
  code checks. The service checks first for a friendly error, and still handles the constraint violation when two requests
  race, so duplicates are impossible rather than unlikely.
- **Migrations run on container start.** `alembic upgrade head` is idempotent, so restarts are safe; every migration is
  tested up → down → up.
- **Stages are an explicit state machine with full history.** The allowed moves live in one table in the service layer
  (saved → applied → assessment / interview → offer; rejected and withdrawn are final), and every move is written to
  `application_events` in the same transaction as the stage change. A transition locks the application row
  (`SELECT ... FOR UPDATE`) before checking the rule, so two simultaneous requests run one after the other and the second
  is judged against the first one's result instead of both applying.
- **Layers:** routes only translate HTTP, services hold the rules and raise domain errors (mapped to 404/409/422 in one place),
  repositories are the only code that writes SQL.
