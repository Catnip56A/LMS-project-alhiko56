# AGENTS.md

Context for LLM assistants working on this codebase.

---

## Project

Yonca is a Flask-based Learning Management System. Multi-language (az/en/ru), Google OAuth + Drive integration, admin panel, forum, course management, resource library.

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

yonca/
  __init__.py           create_app() factory
  config.py             Config classes — reads from os.environ only
  models/__init__.py    All SQLAlchemy models (19 models)
  routes/
    __init__.py         main_bp — homepage, courses, forum, resources
    auth.py             auth_bp — login, Google OAuth
    api.py              api_bp  — REST API (/api/*)
  admin/__init__.py     Flask-Admin interface + Google OAuth for Drive
  templates/            Jinja2 templates
  translations/         Babel .po/.mo (az, en, ru)
  job_manager.py        Background job worker (translation jobs)
  content_translator.py Auto-translation of dynamic content
  google_drive_service.py Google Drive API integration
  translation_service.py  Translation service abstraction

deploy/
  Caddyfile             Production reverse proxy config
  Caddyfile.local       Local prod-dev reverse proxy config
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
DATABASE_URL:        postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
GOOGLE_REDIRECT_URI: https://${DOMAIN}/auth/google/callback     # prod
                     https://${LOCAL_DOMAIN}/auth/google/callback # prod-dev
                     http://localhost:5000/auth/google/callback   # dev
```

For local runs outside Docker (`just dev`), the Justfile prepends these derived vars inline.

**Required in `.env`:**
```
SECRET_KEY, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD,
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, DOMAIN
```

**GitHub Actions secrets (same names, plus):**
`SSH_HOST, SSH_USER, SSH_PRIVATE_KEY, STAGING_DOMAIN`

---

## Docker Compose profiles

| Profile | Services | Use for |
|---|---|---|
| `dev` | db → migrate → app-dev | Daily development |
| `prod-dev` | db → migrate → app-prod-dev + caddy-local | End-to-end local testing |
| `prod` | db → migrate-prod → app + caddy | Production |

`migrate` / `migrate-prod` run `flask db upgrade` and exit before the app starts (`service_completed_successfully`).

`prod` uses image from GHCR: `ghcr.io/${GHCR_OWNER}/yonca:${IMAGE_TAG}`.
`dev` and `prod-dev` build locally.

---

## Key patterns and conventions

**Config is env-only.** `config.py` reads from `os.environ`. No `load_dotenv()` anywhere — it was removed. No fallback defaults for secrets (raises `ValueError`/`RuntimeError` if missing).

**Migrations own the schema.** `db.create_all()` was removed from `create_app()`. Always use `flask db upgrade`. When adding a model field: create a migration with `just makemigrations message="..."`.

**No hardcoded hostnames.** Google OAuth redirect URIs come from `GOOGLE_REDIRECT_URI` env var. `get_google_redirect_uri()` and `get_google_link_uri()` in `auth.py` and `admin/__init__.py` read this var and raise `RuntimeError` if absent.

**Proxy trust.** Gunicorn has `forwarded_allow_ips = "*"` — required for correct `request.remote_addr` and `request.is_secure` behind Caddy.

**Background worker.** `job_manager.start_worker(app)` is called in `create_app()` but skipped during CLI commands (`flask db`, `flask shell`, etc.). The worker reuses the passed `app` instance — it does not call `create_app()` itself.

**Static files.** Served by Flask/Gunicorn from `/app/static/` inside the container. Caddy does not serve static directly (removed — was causing doubled-path 404s). `static/permanent/` contains design assets committed to git.

---

## Common tasks

```bash
just up                          # start dev environment
just migrate                     # apply migrations (Docker)
just makemigrations message="x"  # generate migration (Docker)
just db-stamp                    # stamp alembic head (after restore)
just dev                         # run Flask locally (no Docker)
just prod-dev-up                 # full stack local test
just prod-dev-trust              # trust Caddy CA (once per machine)
```

---

## CI/CD

`.github/workflows/deploy.yml` — triggers on push to `main` or `staging`.

1. Builds image, pushes to GHCR with tags: `<branch>`, `<sha>`, `latest` (main only)
2. SCP: copies `docker-compose.yml`, `Caddyfile`, `backup.sh`, `restore.sh` to server
3. SSH: writes `.env` from secrets, pulls image, restarts containers

Deploy path: `/home/${SSH_USER}/deploy/${branch}/yonca/`

---

## Gotchas

**`uv run` breaks in Docker** when `.:/app` is volume-mounted (dev profile) because the venv Python path in the image doesn't match the system Python path seen by `uv`. Use `flask` / `gunicorn` directly in container commands. `UV_PYTHON_DOWNLOADS=never` is set in the Dockerfile final stage.

**Migration generation needs an empty DB.** `flask db migrate` compares models against the current DB state. If the DB already has all tables, it generates an empty migration. To generate a fresh initial migration, use a throwaway empty postgres container.

**`pg_isready` without `-d` logs FATAL.** The healthcheck uses `-d ${POSTGRES_DB}` to avoid spurious `database "yonca_user" does not exist` errors in postgres logs.

**Heredoc indentation in GitHub Actions.** The `cat > .env << 'EOF'` block must have zero indentation on its content lines, otherwise leading whitespace becomes part of the variable names and env vars silently fail to load.

**Seed / restore workflow.** After restoring a dump from the old app, the `alembic_version` table contains an unknown revision ID. Clear it and stamp:
```bash
docker compose exec db psql -U yonca_user -d yonca_db -c "DELETE FROM alembic_version;"
just db-stamp
```

**`static/permanent/`** — design assets that must be committed to git. If they're missing from the image it means the build cache was stale. Run `docker compose build --no-cache`.

**Translation service.** `translation_service.py` has hardcoded `127.0.0.1` URLs for LibreTranslate — that service is not part of this Docker setup and those code paths are unused. The active translation path uses `deep-translator` (Google Translate API).

---

## What NOT to do

- Do not add `db.create_all()` back to `create_app()`
- Do not add `load_dotenv()` anywhere
- Do not hardcode hostnames, paths, or credentials in Python files
- Do not edit `uv.lock` manually — run `uv add` / `uv sync`
- Do not `docker exec` into a running container and edit files
- Do not put application logic in Alembic migration files
- Do not set `DATABASE_URL` or `GOOGLE_REDIRECT_URI` in `.env`
