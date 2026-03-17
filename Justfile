set dotenv-load

_ssh_host := env('SSH_HOST', 'yonca-sdc.com')

# SSH tunnels for remote DBs
db-tunnel-prod:
    ssh -L 5439:127.0.0.1:5439 {{_ssh_host}} -N

db-tunnel-staging:
    ssh -L 5438:127.0.0.1:5438 {{_ssh_host}} -N

# Derived vars for local (non-Docker) execution — mirrors docker-compose behaviour
_db_url  := "postgresql://" + env('POSTGRES_USER', 'yonca_user') + ":" + env('POSTGRES_PASSWORD', 'changeme') + "@localhost:5432/" + env('POSTGRES_DB', 'yonca_db')
_redir   := "http://localhost:5000/auth/google/callback"

# Install dependencies
install:
    uv sync

# Run dev server (local, no Docker)
dev:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run flask run --debug --host=0.0.0.0 --port=5000

# Run with gunicorn (local, no Docker)
serve:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run gunicorn --config deploy/gunicorn_config.py app:app

# Flask shell (local)
shell:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run flask shell

# Create admin user (local)
create-admin:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run python scripts/admin/create_admin.py

# Database migrations (via Docker)
migrate:
    docker compose --profile dev run --rm migrate

makemigrations message="auto":
    docker compose --profile dev run --rm migrate flask db migrate -m "{{message}}"

# Mark DB as up-to-date without running migrations (use after squash on existing DB)
db-stamp:
    docker compose --profile dev run --rm migrate flask db stamp head

# Compile translations
translate:
    pybabel compile -d yonca/translations

extract-messages:
    pybabel extract -F yonca/babel.cfg -o yonca/translations/messages.pot .

# Docker — dev
up:
    docker compose --profile dev up -d

down:
    docker compose --profile dev down

build:
    docker compose build

logs:
    docker compose --profile dev logs -f app-dev

# Docker — prod-dev (local end-to-end, https://local.yonca-sdc.com)
prod-dev-up:
    docker compose --profile prod-dev up -d

prod-dev-down:
    docker compose --profile prod-dev down

prod-dev-logs:
    docker compose --profile prod-dev logs -f app-prod-dev

# Trust Caddy's local CA — run once per machine after first prod-dev-up
prod-dev-trust:
    docker compose --profile prod-dev exec caddy-local caddy trust

# Docker — prod
prod-up:
    docker compose --profile prod up -d

prod-down:
    docker compose --profile prod down

prod-logs:
    docker compose --profile prod logs -f app
