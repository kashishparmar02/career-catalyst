# Career Catalyst

Track every job application in one place, see how well each job matches your profile, and keep your
search moving: from saved, to applied, to interview, to offer.

> Work in progress. The API skeleton is in place; application tracking, job intake and matching are next.

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
