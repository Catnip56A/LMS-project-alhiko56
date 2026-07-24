# Development Guide

This document explains the decisions, tools, and fixes made to bring LMS to a production-grade setup. It is written for the original developer of this project to explain what changed, why it changed, and what to keep in mind going forward.

---

## What changed and why

### Package management: `pip` → `uv` + `pyproject.toml`

**Before:** `requirements.txt` with unpinned versions like `Flask>=2.0.0`.

**Problem:** Unpinned versions mean different developers (and the production server) can end up running different versions of libraries. This causes subtle "works on my machine" bugs that are very hard to track down.

**Now:** `pyproject.toml` declares dependencies and `uv.lock` pins every package to an exact version. `uv` is also dramatically faster than `pip`. When you add a new dependency:

```bash
uv add some-package        # adds to pyproject.toml and updates uv.lock
uv sync                    # installs everything from the lockfile
```

Never edit `uv.lock` by hand. Commit it to git — it is the source of truth for reproducible installs.

---

### Task runner: `just`

**Before:** Scripts were run with `python create_admin.py`, `flask db upgrade`, etc. — you had to remember the exact commands and paths.

**Now:** `Justfile` at the project root contains all common commands. Run `just` with no arguments to see what's available. Recipes also load `.env` automatically via `set dotenv-load`.

---

### Docker and Docker Compose

The app now runs in Docker containers. This means the same image runs on your laptop, staging, and production — no more "it works on my machine but not on the server."

**Three profiles:**

- `dev` — for daily development. Flask's built-in dev server with hot reload. Source code is mounted into the container so edits take effect immediately without rebuilding.
- `prod-dev` — for testing the full production stack locally. Runs Gunicorn + Caddy with real HTTPS. Use this before shipping.
- `prod` — the real thing. Uses the image built by GitHub Actions and stored in the container registry.

**Services start in order.** The `migrate` service runs `flask db upgrade` and exits before the app starts. This ensures the schema is always correct before any request is served. The `depends_on: condition: service_completed_successfully` makes this guarantee explicit.

---

### Environment variables

This is one of the most important concepts for production applications. **Never hardcode secrets in source code.**

**Where variables come from:**

| Variable | Set by | Notes |
|---|---|---|
| `SECRET_KEY` | `.env` / GitHub secret | Flask session signing — must be secret and stable |
| `POSTGRES_*` | `.env` / GitHub secret | Raw DB credentials |
| `DATABASE_URL` | Docker Compose `environment:` | **Assembled** from `POSTGRES_*` — never set manually |
| `GOOGLE_CLIENT_ID/SECRET` | `.env` / GitHub secret | OAuth credentials |
| `GOOGLE_REDIRECT_URI` | Docker Compose `environment:` | **Assembled** from `DOMAIN` — never set manually |
| `DOMAIN` | `.env` / GitHub secret | The hostname Caddy serves on |

`DATABASE_URL` and `GOOGLE_REDIRECT_URI` are intentionally absent from `.env`. Docker Compose assembles them from their component parts. This means there is **one source of truth** for DB credentials (`POSTGRES_*`) instead of two (`POSTGRES_*` and `DATABASE_URL`).

**For local development without Docker**, `just dev` prepends the derived variables inline so Flask sees them correctly:

```
DATABASE_URL=postgresql://lms_user:...@localhost:5432/lms_db
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
```

---

### `python-dotenv` removed

**Before:** `app.py` and `wsgi.py` called `load_dotenv()` to read `.env`. `wsgi.py` even called `exit(1)` if the file wasn't found.

**Problem:** In Docker, environment variables are injected by Compose before Python starts. Calling `load_dotenv()` is unnecessary, and calling `exit(1)` when `.env` is missing caused the app to crash in production because there's no `.env` file in the container.

**Now:** Environment variables are read directly from `os.environ`. The `just` task runner loads `.env` for local use. Docker Compose loads it for container use. Python doesn't need to touch it at all.

---

## Bugs that were fixed

### 1. `db.create_all()` in `create_app()`

**What was there:**
```python
with app.app_context():
    db.create_all()
```

**Problem:** `db.create_all()` creates tables based on your models, but it has no concept of migrations. If you add a column to a model and call `db.create_all()`, the column does NOT get added to existing tables — it only creates tables that don't exist yet. This causes silent schema drift: your model says one thing, the database says another.

More critically, when running `flask db migrate` to generate a migration, `create_all()` ran first and created all tables on the empty test database, so Alembic found "no changes" and generated an empty migration.

**Fix:** Removed `db.create_all()` entirely. Alembic (`flask db upgrade`) is the only thing that should modify the schema.

---

### 2. Hardcoded paths and credentials

The codebase had several places with paths like `/home/magsud/work/LMS/` and a hardcoded database password `ALHIKO3325!56Catnip?!` in `deploy.sh` and `reset_db.py`. This is a serious security problem — anyone who reads the source code knows your production password.

**Fix:** All secrets are in environment variables. The scripts read from `os.environ`. Credentials are stored in GitHub secrets for CI/CD.

---

### 3. Hardcoded hostnames in OAuth redirects (`auth.py`, `admin/__init__.py`)

**What was there:**
```python
if is_local:
    redirect_uri = 'http://127.0.0.1:5000/auth/google/callback'
else:
    redirect_uri = 'https://beta.yourdomain.example.com/auth/google/callback'
```

**Problem:** `beta.yourdomain.example.com` is hardcoded — staging, production, and any future domain would all use the wrong redirect URI. OAuth would silently fail.

**Fix:** `get_google_redirect_uri()` reads `GOOGLE_REDIRECT_URI` from the environment. This is assembled by Compose from `DOMAIN` so it's always correct for whatever environment is running.

---

### 4. Gunicorn `forwarded_allow_ips` missing

**Problem:** Gunicorn was behind the Caddy reverse proxy but didn't know it. So `request.remote_addr` in Flask showed Caddy's container IP instead of the real visitor's IP. HTTPS detection (`request.is_secure`) also didn't work, which can cause redirect loops and cookie issues.

**Fix:** Added `forwarded_allow_ips = "*"` to `gunicorn_config.py`. This tells Gunicorn to trust the `X-Forwarded-For` and `X-Forwarded-Proto` headers from the proxy in front of it.

---

### 5. Caddy `handle` vs `handle_path` for static files

**What was there:**
```caddyfile
handle /static/* {
    root * /srv/static
    file_server
}
```

**Problem:** `handle /static/*` matches the request but keeps the full path. So a request for `/static/css/site.css` was served from `/srv/static/static/css/site.css` — doubled path. Static files 404'd silently.

**Fix:** Removed the static block entirely. Flask serves static files from inside the container. This is slightly less efficient than having the web server serve them directly, but it's reliable and correct.

---

### 6. Broken migration history

The migration files had a 3-way cycle (`95c → 312c → b510 → 95c`) and multiple disconnected heads. Alembic cannot traverse a cycle — `flask db upgrade` would fail with a cryptic error.

**Fix:** Deleted all migration files, generated a single clean `initial` migration from the current model state, and stamped existing databases so they don't re-run it.

The lesson: never manually edit migration files' `down_revision`. Always let Alembic generate them. If you need to squash, wipe and regenerate.

---

### 7. Background job worker calling `create_app()` inside itself

**What was there:**
```python
def _worker_loop(self):
    from lms import create_app
    app = create_app()     # creates a SECOND Flask app
    with app.app_context():
        ...
```

**Problem:** The worker created a completely separate Flask app instance with its own database connection pool, configuration, and extension state. This is wasteful and can cause subtle bugs.

**Fix:** The worker now receives the existing `app` instance: `job_manager.start_worker(app)`. One app, one connection pool.

Also: the worker is not started during CLI commands like `flask db upgrade`. Starting a background DB-polling thread during migrations is pointless and causes noisy error logs.

---

### 8. `pg_isready` healthcheck without `-d` flag

**What was there:**
```yaml
test: ["CMD-SHELL", "pg_isready -U lms_user"]
```

**Problem:** `pg_isready` without `-d` connects to the database named after the user (`lms_user`). If that database doesn't exist, Postgres logs `FATAL: database "lms_user" does not exist` — a scary error that is actually harmless (the healthcheck still passes) but extremely misleading.

**Fix:**
```yaml
test: ["CMD-SHELL", "pg_isready -U lms_user -d lms_db"]
```

---

## Things to always remember

**Never commit secrets.** `.env` is gitignored. Credentials go in GitHub secrets for production. If you accidentally commit a secret, assume it is compromised and rotate it immediately.

**Never put logic in migrations.** Migration files should only contain `op.add_column(...)`, `op.create_table(...)`, etc. Never put data transformations or application logic in migrations — they are hard to test and hard to reverse.

**`environment:` overrides `env_file:` in Compose.** When a service has both `env_file: .env` and `environment: DATABASE_URL: ...`, the `environment:` block wins. This is how assembled variables like `DATABASE_URL` work correctly even though the component parts come from `env_file`.

**The image is immutable.** In production, the running Docker image should be exactly what was built and tested. Never `docker exec` into a production container and edit files — the change will disappear on the next deploy. Code changes go through git → GitHub Actions → new image → deploy.

**Migrations run before the app.** If you add a column to a model, you must also create a migration (`just makemigrations`). If you deploy without the migration, the app will crash when it tries to use the new column. The `migrate`/`migrate-prod` services guarantee migrations run first.
