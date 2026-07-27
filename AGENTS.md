# AGENTS.md

Context for LLM assistants working on this codebase.

---

## Project

LMS is a Flask-based Learning Management System. Multi-language (en/ru), Google OAuth + Drive integration, admin panel, forum, course management, resource library.

**Stack:** Python 3.13, Flask, SQLAlchemy, Alembic, PostgreSQL 17, Caddy, Gunicorn, Docker Compose, uv, just.

---

## Repository layout

```
app.py                  Entry point (dev server / gunicorn via wsgi.py)
wsgi.py                 WSGI entry for gunicorn
pyproject.toml          Dependencies (uv)
Justfile                Task runner — read this first to understand workflows
docker-compose.yml      Three profiles: dev, prod-dev, prod
Dockerfile              Multi-stage, uv-based

lms/
  __init__.py           create_app() factory
  config.py             Config classes — reads from os.environ only
  models/__init__.py    All SQLAlchemy models (26 models)
  routes/
    __init__.py         main_bp — homepage, courses, forum, resources
    auth.py             auth_bp — login, Google OAuth
    api.py              api_bp  — REST API (/api/*)
  admin/__init__.py     Flask-Admin interface + Google OAuth for Drive
  templates/            Jinja2 templates
  translations/         Babel .po/.mo (en, ru only — az was removed)
  queue.py              RQ Queue + Redis connection
  worker.py             RQ worker entrypoint (separate process — see below)
  job_manager.py        Job definitions/dispatch (translation jobs), enqueues onto queue.py
  content_translator.py Auto-translation of dynamic content
  core_translator.py    Engine-agnostic translate_text/translate_batch (DeepL), no Flask/DB dep
  google_drive_service.py Google Drive API integration (worker-account or per-user OAuth)
  translation_service.py  Runtime translation service — DB-cached, requires app context

Caddyfile               Local dev reverse proxy config (mkcert TLS)
deploy/
  Caddyfile             Production/staging reverse proxy config (in deploy/caddy/)
  gunicorn_config.py    Gunicorn settings (bind, workers, timeouts)
  backup.sh             Dockerized pg_dump to local dir or GCS
  restore.sh            Restore from .dump or .sql
  dnsmasq/              Drop-in configs for local and prod DNS

migrations/
  versions/             Single initial migration (squashed)
  alembic.ini           file_template uses timestamp prefix

scripts/
  admin/                User management, Google token tools
  db/                   Schema, reset, check scripts
  translations/         Bulk translation, cache management
  testing/              Diagnostic scripts (not pytest)
```

---

## Environment variables

**Never set `DATABASE_URL` or `GOOGLE_REDIRECT_URI` in `.env`.** They are assembled by Docker Compose:

```yaml
DATABASE_URL:        postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db-<profile>:5432/${POSTGRES_DB}
GOOGLE_REDIRECT_URI: https://${DOMAIN}/auth/google/callback           # production
                     https://${DOMAIN}/auth/google/callback           # staging
                     http://localhost:5000/auth/google/callback       # dev
```

For local runs outside Docker (`just dev`), the Justfile prepends these derived vars inline.

**Required in `.env`:**
```
SECRET_KEY, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD,
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, DOMAIN
```

**Also used (optional/feature-gated):**
```
REDIS_PORT (dev only — default 6379), DEEPL_API_KEY (translation pipeline),
GOOGLE_API_KEY (Drive Picker)
```

**GitHub Actions secrets (same names, plus):**
`SSH_HOST, SSH_USER, SSH_PRIVATE_KEY, STAGING_DOMAIN` — currently unused; the SSH deploy
step in `deploy.yml` is commented out (no prod/staging server yet). Only image build+push
to GHCR actually runs.

---

## Docker Compose profiles

| Profile | Services | Use for |
|---|---|---|
| `dev` | db-dev, redis-dev → migrate-dev → app-dev, worker-dev, caddy-dev | Daily development |
| `staging` | db-staging, redis-staging → migrate-staging → app-staging, worker-staging | Staging deploy |
| `production` | db-production, redis-production → migrate-production → app-production, worker-production | Production deploy |

`migrate-*` run `flask db upgrade` and exit before the app starts (`service_completed_successfully`).
`worker-*` runs `python -m lms.worker` — a separate process from the Flask app, required for
any queued job (translation, etc.) to actually get processed.

`staging`/`production` use the image from GHCR: `ghcr.io/${GHCR_OWNER}/lms:${IMAGE_TAG}`.
`dev` builds locally.

---

## Key patterns and conventions

**Config is env-only.** `config.py` reads from `os.environ`. No `load_dotenv()` anywhere — it was removed. No fallback defaults for secrets (raises `ValueError`/`RuntimeError` if missing).

**Migrations own the schema.** `db.create_all()` was removed from `create_app()`. Always use `flask db upgrade`. When adding a model field: create a migration with `just makemigrations message="..."`.

**No hardcoded hostnames.** Google OAuth redirect URIs come from `GOOGLE_REDIRECT_URI` env var. `get_google_redirect_uri()` and `get_google_link_uri()` in `auth.py` and `admin/__init__.py` read this var and raise `RuntimeError` if absent.

**Proxy trust.** Gunicorn has `forwarded_allow_ips = "*"` — required for correct `request.remote_addr` and `request.is_secure` behind Caddy.

**Background jobs.** RQ + Redis (`lms/queue.py`), not an in-process thread. `lms/worker.py` is
its own process/container (`worker-dev`/`worker-staging`/`worker-production`, or `just worker`
locally) — it calls `create_app()` itself and pushes an app context for its whole lifetime.
Job status/progress is tracked in the `BackgroundJob` DB table regardless of which worker
picks a job up. The recurring translation sweep uses RQ's built-in scheduler
(`Worker.work(with_scheduler=True)`) — no separate scheduler process.

**Static files.** Served by Flask/Gunicorn from `/app/static/` inside the container. Caddy does not serve static directly (removed — was causing doubled-path 404s). `static/permanent/` contains design assets committed to git.

---

## Common tasks

```bash
just up                          # start dev environment (Docker)
just dev                         # run Flask locally (no Docker), needs `just redis` too
just worker                      # run the RQ worker locally (no Docker) — needed for queued jobs
just migrate                     # apply migrations (Docker)
just makemigrations message="x"  # generate migration (Docker)
just db-stamp                    # stamp alembic head (after restore)
just translate-all                # full .po translation pipeline (needs DEEPL_API_KEY)
```

---

## CI/CD

`.github/workflows/deploy.yml` — triggers on push to `main` or `staging`.

1. Builds image, pushes to GHCR with tags: `<branch>`, `<sha>`, `latest` (main only)
2. SSH deploy steps (SCP config, write `.env` from secrets, pull image, restart containers)
   are currently **commented out** — no prod/staging server provisioned yet. Deploying today
   means pulling the pushed image manually.

---

## Gotchas

**`uv run` breaks in Docker** when `.:/app` is volume-mounted (dev profile) because the venv Python path in the image doesn't match the system Python path seen by `uv`. Use `flask` / `gunicorn` directly in container commands. `UV_PYTHON_DOWNLOADS=never` is set in the Dockerfile final stage.

**Migration generation needs an empty DB.** `flask db migrate` compares models against the current DB state. If the DB already has all tables, it generates an empty migration. To generate a fresh initial migration, use a throwaway empty postgres container.

**`pg_isready` without `-d` logs FATAL.** The healthcheck uses `-d ${POSTGRES_DB}` to avoid spurious `database "lms_user" does not exist` errors in postgres logs.

**Heredoc indentation in GitHub Actions.** The `cat > .env << 'EOF'` block must have zero indentation on its content lines, otherwise leading whitespace becomes part of the variable names and env vars silently fail to load.

**Seed / restore workflow.** After restoring a dump from the old app, the `alembic_version` table contains an unknown revision ID. Clear it and stamp:
```bash
docker compose exec db psql -U lms_user -d lms_db -c "DELETE FROM alembic_version;"
just db-stamp
```

**`static/permanent/`** — design assets that must be committed to git. If they're missing from the image it means the build cache was stale. Run `docker compose build --no-cache`.

**Translation service.** `core_translator.py`/`translation_service.py` use DeepL (`DEEPL_API_KEY` in `.env`) — a cloud API, no local service to run.

---

## What NOT to do

- Do not add `db.create_all()` back to `create_app()`
- Do not add `load_dotenv()` anywhere
- Do not hardcode hostnames, paths, or credentials in Python files
- Do not edit `uv.lock` manually — run `uv add` / `uv sync`
- Do not `docker exec` into a running container and edit files
- Do not put application logic in Alembic migration files
- Do not set `DATABASE_URL` or `GOOGLE_REDIRECT_URI` in `.env`
