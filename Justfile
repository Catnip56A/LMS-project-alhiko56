# Install dependencies
install:
    uv sync

# Run dev server
dev:
    uv run flask run --debug --host=0.0.0.0 --port=5000

# Run with gunicorn (production-like)
serve:
    uv run gunicorn --config deploy/gunicorn_config.py app:app

# Database migrations (dev)
migrate:
    docker compose --profile dev run --rm migrate

makemigrations message="auto":
    docker compose --profile dev run --rm migrate flask db migrate -m "{{message}}"

# Mark DB as up-to-date without running migrations (use after squash on existing DB)
db-stamp:
    docker compose --profile dev run --rm migrate flask db stamp head

# Compile translations
translate:
    uv run pybabel compile -d yonca/translations

extract-messages:
    uv run pybabel extract -F yonca/babel.cfg -o yonca/translations/messages.pot .

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

# Shell
shell:
    uv run flask shell

# Create admin user
create-admin:
    uv run python scripts/admin/create_admin.py
