# LMS

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
| `just prod-dev-up` | `prod-dev` | `https://local.yourdomain.example.com` | Gunicorn + Caddy, local TLS |
| `just prod-up` | `prod` | `https://yourdomain.example.com` | Production image from GHCR |

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

POSTGRES_DB=lms_db
POSTGRES_USER=lms_user
POSTGRES_PASSWORD=...

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

DOMAIN=yourdomain.example.com
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
just install                  # sync dependencies
just translate                # compile .po translation files
just create-admin             # create a new admin user (local)
just make-admin <username>    # promote an existing user to full admin (Docker dev)
just build                    # rebuild Docker images
just logs                     # follow app-dev logs
```

## Admin permission tiers

There are three access levels:

| Level | Condition | What they see |
|---|---|---|
| Full admin | `is_admin=True`, `admin_permissions=NULL` | Everything, including the Permissions page |
| Sub-admin | `is_admin=True`, `admin_permissions=[list]` | Only their assigned sections |
| Regular user | `is_admin=False` | No admin access |

Permissions are managed at `/admin/user_permissions/` (full admins only). The 8 available permissions are: `user_management`, `course_management`, `certificate_management`, `forum_management`, `builder_management`, `moxo_test_management`, `resource_management`, `limitations_management`.

To promote an existing user to full admin on staging/production (SSH into server first):

```bash
docker compose --profile staging run --rm \
  -v $(pwd)/scripts:/app/scripts \
  -e DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db-staging:5432/${POSTGRES_DB} \
  -e GOOGLE_REDIRECT_URI=https://localhost/unused \
  app-staging python scripts/admin/make_full_admin.py <username>
```

## Deployment

### Promote staging to production

```bash
git checkout main
git merge staging
git push origin main


#vise versa:

git checkout staging
git merge main
git push origin staging
```

This triggers the GitHub Actions workflow which deploys to production.

### How CI/CD works

Pushes to `main` and `staging` trigger GitHub Actions which:
1. Build and push the image to `ghcr.io/lms-sdc/lms`
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
ssh user@host "cd ~/deploy/production/lms && \
  docker compose run --rm migrate-prod flask db stamp head"
```

### Uploading certificate templates

Certificate templates are private (not in git). Upload them to each server separately:

```bash
# Staging
scp lms/static/certificates/moxo_template.jpeg lms/static/certificates/moxo_template_legacy.png magsud@yourdomain.example.com:~/deploy/staging/lms/data/cert-templates/

# Production
scp lms/static/certificates/moxo_template.jpeg lms/static/certificates/moxo_template_legacy.png magsud@yourdomain.example.com:~/deploy/production/lms/data/cert-templates/
```

No restart needed — the volume is live. Templates appear in the admin certificate tuning picker immediately.

To remove an old template:

```bash
# Staging
ssh magsud@yourdomain.example.com "rm ~/deploy/staging/lms/data/cert-templates/moxo_template.png"

# Production
ssh magsud@yourdomain.example.com "rm ~/deploy/production/lms/data/cert-templates/moxo_template.png"
```

### Restoring production data

```bash
scp seed.sql user@host:~/deploy/production/lms/
ssh user@host
cd ~/deploy/production/lms
docker compose exec -T db psql -U lms_user -d lms_db < seed.sql
```

### Backups

```bash
# Manual
./deploy/backup.sh

# Restore
./deploy/restore.sh path/to/backup.dump

# Scheduled — add to crontab on server
0 3 * * * cd ~/deploy/production/lms && ./deploy/backup.sh >> ~/logs/backup.log 2>&1
```

## DNS setup

| Machine | File | Entry |
|---|---|---|
| Production server | `/etc/dnsmasq.d/lms.conf` | `address=/.yourdomain.example.com/127.0.0.1` |
| Developer machine | `/etc/dnsmasq.d/lms-local.conf` | `address=/local.yourdomain.example.com/127.0.0.1` |

After installing local dnsmasq config, trust Caddy's CA once:

```bash
just prod-dev-trust
```

## Project layout

```
lms/              Flask application package
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
