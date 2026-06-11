# Developer Reference Guide

A practical guide to the tools and concepts used in this project.
Each section explains the *why*, the *how*, and shows where it appears in the codebase.

---

## Table of Contents

1. [SSH — Remote access and tunnels](#1-ssh)
2. [Docker — Containers and images](#2-docker)
3. [Docker Compose — Combining services](#3-docker-compose)
4. [SSL Certificates — HTTPS in development](#4-ssl-certificates)
5. [Development Flow — Build, commit, deploy](#5-development-flow)
6. [Just — Task runner](#6-just)
7. [Project Structure — Keeping it clean](#7-project-structure)
8. [Databases — Migrations, backups, restores](#8-databases)
9. [Working with LLMs — Getting what you want](#9-working-with-llms)
10. [Environment Variables — Configuration without chaos](#10-environment-variables)
11. [Development Environment — Your local machine](#11-development-environment)

---

## 1. SSH

### What it is

SSH (Secure Shell) is an encrypted protocol for executing commands on remote machines.
It is not just for "opening a terminal" — it is the backbone of automated deployments, database tunnels, and file transfers.

### Key concepts

**Basic connection:**
```bash
ssh user@hostname          # interactive shell
ssh user@hostname "ls -la" # run one command and exit
```

**Port forwarding (tunnels):**
Port forwarding lets you access a service on a remote machine *as if it were local*.
```
Local port  →  SSH tunnel  →  Remote port
5438        →  encrypted   →  5438 (Postgres on server)
```
This is critical for security: the database is never exposed to the internet — only to localhost on the server.

**SCP — copying files:**
```bash
scp local_file.txt user@host:/remote/path/
scp user@host:/remote/file.txt ./local/
```

### How we use it here

**`Justfile` — database tunnels to production/staging:**
```justfile
db-tunnel-prod:
    ssh -L 5439:127.0.0.1:5439 yonca-sdc.com -N

db-tunnel-staging:
    ssh -L 5438:127.0.0.1:5438 yonca-sdc.com -N
```
`-L local:remote_host:remote_port` — forwards traffic from your local port through the tunnel.
`-N` — don't open a shell, just hold the tunnel open.

**`Justfile` — pull database directly from a running container:**
```justfile
db-pull-staging:
    ssh yonca-sdc.com "docker compose ... exec -T db pg_dump ..." \
      | docker compose exec -T db pg_restore ...
```
Notice the pipe `|`. The `pg_dump` output is streamed through SSH directly into `pg_restore` locally — no temp file needed.

**`deploy.yml` — GitHub Actions deploys via SSH:**
```yaml
- name: Deploy via SSH
  uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.SSH_HOST }}
    key: ${{ secrets.SSH_PRIVATE_KEY }}
    script: |
      cd ~/deploy/staging/yonca
      docker compose up -d
```
The CI server connects to the production server with a private key stored as a GitHub secret. It runs shell commands remotely, exactly like you would in a terminal.

### Common mistake

Never put database ports directly on `0.0.0.0` in production. Notice in `docker-compose.yml`:
```yaml
ports:
  - "127.0.0.1:${POSTGRES_PORT:-5432}:5432"
```
`127.0.0.1:` prefix means only localhost can connect. Without it, anyone on the internet could try to reach your database.

---

## 2. Docker

### What it is

Docker packages an application and all its dependencies into an **image** — a portable, reproducible snapshot.
A running image is called a **container**. Containers are isolated from the host OS but share its kernel.

**The key promise:** "works on my machine" becomes "works everywhere" because the machine *is* the image.

### Dockerfile anatomy

A `Dockerfile` is a recipe for building an image. Instructions run top to bottom; each creates a layer.

```dockerfile
FROM python:3.13-slim AS builder   # start from an official base image
WORKDIR /app                        # all subsequent commands run here

COPY pyproject.toml uv.lock ./      # copy dependency spec
RUN uv sync --frozen --no-dev       # install dependencies (creates a layer)

COPY . .                            # copy application code

EXPOSE 8000                         # documentation: this port is used
CMD ["gunicorn", "..."]             # default command when container starts
```

### Multi-stage builds

Our `Dockerfile` uses two stages:

```dockerfile
# Stage 1: builder — installs all dependencies
FROM python:3.13-slim AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev     # creates /app/.venv

# Stage 2: final — copies only the built venv, discards the build tools
FROM python:3.13-slim
COPY --from=builder /app/.venv /app/.venv
COPY . .
CMD ["gunicorn", "--config", "deploy/gunicorn_config.py", "app:app"]
```

Why? The `builder` stage may pull compilers, build tools, header files. None of that belongs in production. The final image only has the venv and app code — smaller, faster, fewer attack vectors.

### Common mistakes

- **Copying the entire directory before installing deps** — this busts the layer cache every time any file changes. Always copy `pyproject.toml` and lock file first, run install, *then* copy the rest.
- **Running as root** — not done here, but worth knowing: add a non-root user for production images.
- **Storing secrets in the image** — never `COPY .env` into a Dockerfile. Secrets go in at runtime via environment variables.

---

## 3. Docker Compose

### What it is

Docker Compose defines and runs **multiple containers together** as a single application.
It replaces a wall of `docker run` commands with one declarative YAML file.

### Core concepts

| Concept | Meaning |
|---|---|
| `services` | Each container — app, database, proxy |
| `volumes` | Persist data outside the container lifecycle |
| `networks` | Isolated communication between services |
| `profiles` | Groups of services; only start what you need |
| `depends_on` | Start order and health checks |
| `env_file` | Load environment variables from a file |

### How we use it here

**`docker-compose.yml` — service dependency chain:**
```yaml
migrate:
  profiles: [dev]
  build: .
  command: flask db upgrade
  depends_on:
    db:
      condition: service_healthy   # waits until postgres is actually ready

app-dev:
  profiles: [dev]
  depends_on:
    migrate:
      condition: service_completed_successfully  # waits until migrations ran
```

The application never starts with a stale schema. The chain is: `db healthy → migrate completes → app starts`.

**Profiles — dev vs prod from the same file:**
```yaml
# dev: build from source, mount volumes for live reload
app-dev:
  profiles: [dev]
  build: .

# prod: pull pre-built image from registry
app:
  profiles: [prod]
  image: ghcr.io/${GHCR_OWNER}/yonca:${IMAGE_TAG:-latest}
```

```bash
docker compose --profile dev up    # starts dev services
docker compose up   # starts production services
```

**Volumes — data survives container restarts:**
```yaml
db:
  volumes:
    - ./data/postgres:/var/lib/postgresql/data  # host path : container path
```
If the container is deleted, the data is still in `./data/postgres` on the host.

**Networks — multi-app shared proxy:**
```yaml
# app's docker-compose.yml
networks:
  yonca-proxy:
    external: true      # this network already exists, we just join it

# caddy's docker-compose.yml (deploy/caddy/docker-compose.yml)
networks:
  yonca-proxy:
    name: yonca-proxy   # this one owns and creates the network
```

Caddy lives in its own compose project but shares the `yonca-proxy` network with the app. Caddy can reach the app container by its hostname. No ports need to be exposed to the internet — only ports 80 and 443 on Caddy.

---

## 4. SSL Certificates

### Why HTTPS matters

HTTPS encrypts traffic between the browser and server. Without it:
- Passwords are sent in plain text
- Session cookies can be stolen
- Google OAuth refuses to work (it requires HTTPS for redirect URIs)

### How certificates work

A certificate says: "I am `yonca-sdc.com` and this authority (CA) vouches for me."
Browsers trust certificates signed by well-known CAs. Self-signed certificates trigger browser warnings.

### Development vs production

| Environment | Tool | How |
|---|---|---|
| Production | Caddy (auto) | Caddy fetches Let's Encrypt certs automatically — zero config |
| Local dev | mkcert | Creates a locally-trusted cert signed by a local CA you install once |

### How we use it here

**Production — Caddy handles everything automatically:**
```
yonca-sdc.com {           # Caddy sees this domain, auto-fetches Let's Encrypt
  reverse_proxy yonca-sdc-com:8000
}
```
No certificate files to manage. Caddy renews them automatically before expiry.

**Local dev — `mkcert` generates trusted local certs:**

From `Justfile`:
```justfile
certs:
    #!/usr/bin/env bash
    DOMAIN="${LOCAL_DOMAIN:-local.yonca-sdc.com}"
    if [ -f ".local/certs/local.crt" ]; then
      echo "Certs already exist — skipping."
      exit 0
    fi
    mkdir -p .local/certs
    mkcert -install                         # install local CA into system trust store (once)
    mkcert -cert-file .local/certs/local.crt \
           -key-file  .local/certs/local.key \
           "$DOMAIN"
```

The cert is then mounted into Caddy:
```yaml
# docker-compose.yml
caddy-dev:
  volumes:
    - ./.local/certs:/certs:ro

# Caddyfile
{$LOCAL_DOMAIN} {
  tls /certs/local.crt /certs/local.key   # use our mkcert cert
  reverse_proxy app-dev:8000
}
```

Result: `https://local.yonca-sdc.com` works in your browser with no warnings, enabling real Google OAuth callbacks during development.

---

## 5. Development Flow

### The pipeline

```
Write code  →  Test locally  →  git commit  →  git push  →  GitHub Actions  →  Production
```

### Branch strategy

| Branch | Environment | URL |
|---|---|---|
| `main` | Production | yonca-sdc.com |
| `staging` | Staging | staging.yonca-sdc.com |

Push to either branch triggers an automated deploy. **Never push broken code to `main`.**
Work on a feature branch, test on `staging`, merge to `main` when confident.

### What happens on push

From `.github/workflows/deploy.yml`:

```yaml
on:
  push:
    branches: [main, staging]

jobs:
  deploy:
    steps:
      # 1. Build Docker image and push to GitHub Container Registry
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          tags: |
            ${{ env.IMAGE }}:${{ github.ref_name }}   # staging or main
            ${{ env.IMAGE }}:${{ github.sha }}         # exact commit hash
            ${{ env.IMAGE }}:latest                    # only for main

      # 2. Copy compose file and scripts to the server
      - name: Copy app files
        uses: appleboy/scp-action@v0.1.7
        with:
          source: "docker-compose.yml,deploy/backup.sh,deploy/restore.sh"
          target: /home/.../deploy/staging/yonca

      # 3. SSH in, write .env, backup DB, pull new image, restart
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          script: |
            ./deploy/backup.sh ~/backup/yonca/staging    # backup BEFORE deploy
            docker compose pull
            docker compose up -d --remove-orphans
            docker image prune -f
```

Notice that a **database backup runs before every deploy**. If something goes wrong with a migration, you can restore.

### Tagging images with git SHA

```yaml
tags: ${{ env.IMAGE }}:${{ github.sha }}
```

Every image is tagged with the exact commit hash that built it. You can always roll back to any previous commit by redeploying its image tag.

---

## 6. Just

### What it is

`just` is a command runner — like `make` but without the ancient baggage. It reads a `Justfile` and lets you run named recipes with `just <name>`.

**Why not just write shell scripts?** You could, but then you'd have a `scripts/` folder full of files nobody runs consistently. `just` keeps all common operations in one discoverable place with `just --list`.

### Justfile anatomy

```justfile
set dotenv-load                     # auto-load .env file

_ssh_host := env('SSH_HOST', 'yonca-sdc.com')  # variable with default

# Recipe with dependencies: `just up` will run `certs` first
up: certs
    docker compose --profile dev up -d

# Recipe with a parameter (default value provided)
makemigrations message="auto":
    docker compose --profile dev run --rm migrate flask db migrate -m "{{message}}"

# Multi-line bash recipe
certs:
    #!/usr/bin/env bash
    if [ -f ".local/certs/local.crt" ]; then
      echo "Certs already exist — skipping."
      exit 0
    fi
    mkcert -install
    mkcert -cert-file .local/certs/local.crt ...
```

### Useful recipes in this project

```bash
just dev              # start local dev server on :5000
just up               # start full dev stack with Caddy TLS
just migrate          # run pending migrations
just makemigrations   # generate new migration
just makemigrations "add user avatar"  # with a message
just translate        # compile translation files
just db-tunnel-staging  # open SSH tunnel to staging DB
just db-pull-staging    # replace local DB with staging data
just logs             # tail app logs
```

### When to add a recipe

Any multi-step command you run more than twice deserves a recipe. If you find yourself explaining to a teammate "first you do X, then you do Y, but only if Z", that's a `just` recipe waiting to be written.

---

## 7. Project Structure

### The principle

A good project structure is one where you can answer "where does X live?" in 3 seconds.
Files should be grouped by **what they are** or **what feature they belong to** — not by when you created them.

### This project's layout

```
yonca/                    # Python package — the Flask application
├── __init__.py           # app factory: create_app()
├── config.py             # environment-based configuration classes
├── models/               # SQLAlchemy models (one file per domain object)
├── routes/               # Flask blueprints (one file per feature area)
├── templates/            # Jinja2 HTML templates
├── translations/         # i18n .po/.mo files
├── admin/                # Flask-Admin customization
└── *.py                  # services: translation_service.py, job_manager.py

migrations/               # Alembic migration files — never edit by hand
deploy/                   # Everything needed to run in production
├── gunicorn_config.py
├── caddy/                # Shared reverse proxy config
├── backup.sh
└── restore.sh
scripts/                  # One-off utility scripts
static/                   # CSS, JS, images
docs/                     # Documentation
.github/workflows/        # CI/CD pipeline definitions
```

### Rules to live by

**One concern per file.** A file called `utils.py` that grows to 800 lines is a graveyard.
If a function doesn't clearly belong in a file, it needs its own home or a better-named module.

**Config never goes in code.** Hardcoded URLs, ports, credentials, and feature flags belong in environment variables or config files — never in Python files.

**Scripts are not the application.** One-off admin tools live in `scripts/`, not mixed with application code in `yonca/`.

**Migrations are generated, not written.** The `migrations/versions/` folder is managed by Alembic. Don't create files there manually unless you know exactly what you're doing.

**`deploy/` is not `scripts/`.** Deployment artifacts (server configs, backup scripts) live in `deploy/` because they need to be copied to the server. Utility scripts that only run locally live in `scripts/`.

### The LLM problem

LLMs (including the one helping you now) have a strong tendency to generate code that "works" but creates clutter:
- Dumping everything into `app.py` or `utils.py`
- Creating one-off helper functions inline instead of in the right module
- Adding commented-out code "just in case"
- Creating new files for things that belong in existing ones

**When an LLM proposes creating a new file, ask:** "Where exactly does this belong in the existing structure, and why can't it go there?"

---

## 8. Databases

### Why you can't avoid migrations

When you add a column to a SQLAlchemy model, the Python class changes but the actual database table does not. Next time the app runs, it crashes trying to read a column that doesn't exist.

**Migrations are version-controlled SQL changes.** They describe the exact steps to get from database schema version N to version N+1 (and back, via downgrade).

```
Model change  →  flask db migrate  →  new migration file  →  flask db upgrade  →  DB updated
```

The migration file is committed to git. Every environment (local, staging, production) can reach the same schema state by running `flask db upgrade`.

### Migration anatomy

From `migrations/versions/20260317_0028_drop_legacy_tab_label_fields.py`:

```python
revision = 'a1c3e5f7b2d4'        # this migration's ID
down_revision = 'b9b29e2f764f'   # the migration this builds on (linked list)

def upgrade():
    # what runs on `flask db upgrade`
    with op.batch_alter_table('course') as batch_op:
        batch_op.drop_column('tab_content_label')
        batch_op.drop_column('tab_announcements_label')

def downgrade():
    # what runs on `flask db downgrade` (rollback)
    with op.batch_alter_table('course') as batch_op:
        batch_op.add_column(sa.Column('tab_content_label', sa.String(50)))
        batch_op.add_column(sa.Column('tab_announcements_label', sa.String(50)))
```

Always write the `downgrade()` function. You will need it someday.

### The workflow

```bash
# 1. Change a model in yonca/models/something.py
# 2. Generate migration
just makemigrations "describe what changed"

# 3. Review the generated file in migrations/versions/
# 4. Apply it
just migrate

# 5. Commit both the model change AND the migration file together
git add yonca/models/something.py migrations/versions/...
git commit -m "add avatar field to user"
```

**Never apply migrations to production before backup.** The deploy script does this automatically, but if you ever apply manually, run `backup.sh` first.

### Backup and restore

**Backup** (`deploy/backup.sh`):
```bash
docker compose exec -T db \
  pg_dump -U yonca_user -Fc yonca_db > backup_2026-03-17.dump
```
`-Fc` = custom binary format, smaller and faster than plain SQL.
The script keeps the 7 most recent backups and deletes older ones.

**Restore** (`deploy/restore.sh`):
```bash
docker compose exec -T db \
  pg_restore -U yonca_user -d yonca_db --clean --if-exists \
  < backup_2026-03-17.dump
```
`--clean` drops existing objects before recreating them.
`--if-exists` skips errors if objects don't exist yet.

**Pull staging DB to local** (for debugging production data issues):
```bash
just db-pull-staging   # streams directly from server, no temp file
```

---

## 9. Working with LLMs

### The core problem

An LLM will confidently generate code that:
- Works in isolation but breaks your architecture
- Adds complexity you didn't ask for
- Ignores constraints it wasn't told about
- Looks reasonable but subtly misunderstands the goal

The model does not know your codebase, your deployment, your constraints, or your taste — unless you tell it.

### What to say

**State the constraint first, then the task:**
> "We use Flask blueprints. Don't suggest restructuring into a single routes file. Add an endpoint to `yonca/routes/courses.py` that..."

**Name the files you're working in:**
> "In `yonca/models/user.py`, add a `last_seen` timestamp column. Don't touch the migration — I'll generate it with `just makemigrations`."

**Describe what you don't want:**
> "Don't add comments. Don't add error handling for cases that can't happen. Don't refactor anything I didn't ask about."

**Specify the scope explicitly:**
> "Only change the function I'm about to show you. Leave everything else exactly as is."

### What not to do

**Don't paste the whole codebase and say "fix it."**
You'll get back a rewritten version with different variable names, new abstractions you didn't ask for, and five new files.

**Don't accept "improvements" you didn't ask for.**
If you asked to fix a bug and got back a refactored class, reject it and ask for the minimal change.

**Don't assume the first output is correct.**
Run it. Test it. Read it. The confidence of the output has nothing to do with its correctness.

### Useful prompt patterns

```
Context: [what file/function/feature you're working in]
Goal: [exactly what you want]
Constraints: [what must not change, what patterns to follow]
Output: [just the changed code / just the function / a diff]
```

For this project specifically, always mention:
- "This is a Flask app with blueprints"
- "Use SQLAlchemy models in `yonca/models/`"
- "Migrations are managed with Alembic — don't write raw SQL"
- "Env vars come from `.env`, accessed via `os.environ` in `config.py`"

---

## 10. Environment Variables

### Why they exist

Your code runs in multiple environments: your laptop, a teammate's laptop, staging, production.
Each has different database passwords, API keys, domain names, and debug flags.

If those values are hardcoded in the source code:
- Secrets end up in git history (permanent, irrecoverable)
- Changing any value requires a code change and a redeploy
- Different environments need different branches of code

**Environment variables decouple configuration from code.**

### The pattern in this project

**`.env.example`** — committed to git, shows what variables exist with placeholder values:
```bash
SECRET_KEY=change-me
POSTGRES_DB=yonca_db
POSTGRES_USER=yonca_user
POSTGRES_PASSWORD=changeme
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
DOMAIN=yonca-sdc.com
```

**`.env`** — your actual values, never committed to git (in `.gitignore`):
```bash
SECRET_KEY=a-real-random-secret
POSTGRES_PASSWORD=hunter2
GOOGLE_CLIENT_ID=123456789.apps.googleusercontent.com
```

**`yonca/config.py`** — reads vars and fails loudly if required ones are missing:
```python
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is not set")

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL environment variable is not set")
```

Failing at startup with a clear error is better than failing at runtime with a cryptic one.

### Scope: where variables live

| Scope | How set | Visible to |
|---|---|---|
| Shell session | `export FOO=bar` | Current terminal and child processes |
| `.env` file | `set dotenv-load` in Justfile | Recipes that run via `just` |
| `docker-compose.yml` `environment:` | In the YAML | That container only |
| `docker-compose.yml` `env_file: .env` | Loads from file | That container only |
| GitHub Secrets | Repository settings UI | GitHub Actions workflows |

**Key insight:** a variable in your `.env` is not automatically available inside a Docker container — you have to explicitly pass it in `environment:` or `env_file:`. See `docker-compose.yml`:

```yaml
app-dev:
  env_file: .env                     # load everything from .env
  environment:
    DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    # ^ constructed from other vars — overrides anything in env_file
```

### Adding a new variable

1. Add it to `.env.example` with a placeholder value and a comment
2. Add it to your local `.env` with the real value
3. Add it to `config.py` if it's app configuration
4. Add it to `docker-compose.yml` `environment:` if it's needed inside a container
5. Add it to GitHub Secrets if it's needed in CI/CD
6. Document it

If you skip step 1, the next person to set up the project will have a mystery crash with no hint about what's missing.

---

## 11. Development Environment

### Why it matters

A messy dev environment causes:
- "Works on my machine" bugs
- Conflicts between projects using different Python/Node versions
- Lost time debugging environment issues instead of actual code
- Fear of touching the global setup

A clean one means you can clone a repo and be running it in 10 minutes on any machine.

### The golden rules

**Never install project packages globally.** Use virtual environments (Python), or node_modules (Node). Each project carries its own dependencies.

**Use a version manager.** `pyenv` for Python, `nvm` or `volta` for Node. When a project needs Python 3.13 and another needs 3.11, you need to be able to switch.

**Pin your versions.** This project uses `uv` with a `uv.lock` file. The lockfile records exact versions of every dependency. Commit it. Never delete it.

**Use a `.env` file.** Never export secrets in your shell profile (`~/.zshrc`). They'll leak into every process you run and are hard to rotate.

**Keep project data inside the project.** Database data lives in `./data/postgres/`, certs in `./.local/certs/`. When you're done with a project, `rm -rf` the directory and nothing leaks.

### This project's tooling

| Tool | Purpose | Install |
|---|---|---|
| `uv` | Python package manager, virtualenv | `curl -Lsf https://astral.sh/uv/install.sh \| sh` |
| `just` | Task runner | `brew install just` or `cargo install just` |
| `mkcert` | Local TLS certificates | `brew install mkcert` |
| `docker` + `docker compose` | Containers | Docker Desktop or `docker-ce` |

### First-time setup

```bash
git clone <repo>
cd yonca
cp .env.example .env          # fill in real values
just install                  # uv sync — installs dependencies
just up                       # starts postgres + migrate + app + caddy
```

That's it. `just --list` shows all available commands.

### Signs your environment needs cleaning

- You have a `venv/`, `.venv/`, `env/` folder in your home directory
- You run `pip install` without activating a virtualenv
- Your `~/.zshrc` has hardcoded API keys or database passwords
- Running a command works in one terminal but not another
- You've installed the same package 3 times trying to fix an import error

When something breaks: **read the error message first**, then check if the relevant service is running (`docker compose ps`), then check if the `.env` has all the required variables.
