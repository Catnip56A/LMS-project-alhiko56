# Yonca

Learning management platform built with Flask. Supports courses, forums, resources, and Google Drive integration with multi-language content (Azerbaijani, English, Russian).

## Requirements

- [Docker](https://docs.docker.com/get-docker/) + Compose v2
- [uv](https://github.com/astral-sh/uv) — for local development without Docker
- [just](https://github.com/casey/just) — task runner

## Quick start

```bash
cp .env.example .env   # fill in credentials
just up                # start db + migrations + Flask dev server
```

App available at **http://localhost:5000**

## Environments

| Command | Profile | URL | Notes |
|---|---|---|---|
| `just up` | `dev` | `http://localhost:5000` | Flask dev server, hot reload |
| `just prod-dev-up` | `prod-dev` | `https://local.yonca-sdc.com` | Gunicorn + Caddy, local TLS |
| `just prod-up` | `prod` | `https://yonca-sdc.com` | Production image from GHCR |

## Local development (no Docker)

```bash
uv sync
just dev       # Flask dev server against localhost postgres
just serve     # Gunicorn
just shell     # Flask shell
```

Requires postgres on `localhost:5432` — `just up` starts one via Docker if needed.

## .env variables

Copy `.env.example` and fill in:

```env
SECRET_KEY=...

POSTGRES_DB=yonca_db
POSTGRES_USER=yonca_user
POSTGRES_PASSWORD=...

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

DOMAIN=yonca-sdc.com
```

`DATABASE_URL` and `GOOGLE_REDIRECT_URI` are assembled automatically by Docker Compose — do not set them manually.

## Database

```bash
just migrate                         # apply pending migrations
just makemigrations message="..."    # generate new migration
just db-stamp                        # mark DB as up-to-date (after squash/restore)
```

## Common tasks

```bash
just install       # sync dependencies
just translate     # compile .po translation files
just create-admin  # create an admin user
just build         # rebuild Docker images
just logs          # follow app-dev logs
```

## Deployment

Pushes to `main` and `staging` trigger GitHub Actions which:
1. Build and push the image to `ghcr.io/yonca-sdc/yonca`
2. Copy `docker-compose.yml`, `Caddyfile`, and scripts to the server via SCP
3. Write `.env` from GitHub secrets
4. Pull the new image and restart containers

### First-time server setup

```bash
./scripts/bootstrap-server.sh <host> <user>
```

Then push to `main` or `staging` to trigger the first deploy.

On a fresh server with no prior data, stamp migrations after first deploy:

```bash
ssh user@host "cd ~/deploy/production/yonca && \
  docker compose run --rm migrate-prod flask db stamp head"
```

### Restoring production data

```bash
scp seed.sql user@host:~/deploy/production/yonca/
ssh user@host
cd ~/deploy/production/yonca
docker compose exec -T db psql -U yonca_user -d yonca_db < seed.sql
```

### Backups

```bash
# Manual
./deploy/backup.sh

# Restore
./deploy/restore.sh path/to/backup.dump

# Scheduled — add to crontab on server
0 3 * * * cd ~/deploy/production/yonca && ./deploy/backup.sh >> ~/logs/backup.log 2>&1
```

## DNS setup

| Machine | File | Entry |
|---|---|---|
| Production server | `/etc/dnsmasq.d/yonca.conf` | `address=/.yonca-sdc.com/127.0.0.1` |
| Developer machine | `/etc/dnsmasq.d/yonca-local.conf` | `address=/local.yonca-sdc.com/127.0.0.1` |

After installing local dnsmasq config, trust Caddy's CA once:

```bash
just prod-dev-trust
```

## Project layout

```
yonca/              Flask application package
  models/           SQLAlchemy models
  routes/           Blueprints (main, auth, api)
  templates/        Jinja2 templates
  translations/     Babel .po/.mo files (az, en, ru)
  admin/            Flask-Admin interface
migrations/         Alembic migration files
static/             CSS, JS, images
deploy/             Caddyfile, gunicorn config, backup/restore scripts
scripts/            Utility scripts (db, admin, translations, testing)
```
