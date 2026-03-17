set dotenv-load

_ssh_host := env('SSH_HOST', 'yonca-sdc.com')

# SSH tunnels for remote DBs
db-tunnel-prod:
    ssh -L 5439:127.0.0.1:5439 {{_ssh_host}} -N

db-tunnel-staging:
    ssh -L 5438:127.0.0.1:5438 {{_ssh_host}} -N

# Pull DB from staging live (streams directly, no temp file)
db-pull-staging:
    ssh {{_ssh_host}} "docker compose --profile prod -f ~/deploy/staging/yonca/docker-compose.yml exec -T db pg_dump -U ${POSTGRES_USER} -Fc ${POSTGRES_DB}" \
      | docker compose exec -T db pg_restore -U ${POSTGRES_USER} -d ${POSTGRES_DB} --clean --if-exists --no-owner --no-acl
    just db-stamp

# Pull latest backup from server
db-pull-backup:
    ssh {{_ssh_host}} "cat \$(ls -t ~/backup/yonca/staging/*.dump | head -1)" \
      | docker compose exec -T db pg_restore -U ${POSTGRES_USER} -d ${POSTGRES_DB} --clean --if-exists --no-owner --no-acl
    just db-stamp

# Derived vars for local (non-Docker) execution — mirrors docker-compose behaviour
_db_url  := "postgresql://" + env('POSTGRES_USER', 'yonca_user') + ":" + env('POSTGRES_PASSWORD', 'changeme') + "@localhost:5432/" + env('POSTGRES_DB', 'yonca_db')
_redir   := "http://localhost:5000/auth/google/callback"

# Install dependencies
install:
    uv sync

db:
    docker compose --profile dev up db migrate -d
# Run dev server (local, no Docker)
dev: db
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
up: certs
    docker compose --profile dev up -d

down:
    docker compose --profile dev down

build:
    docker compose build

logs:
    docker compose --profile dev logs -f app-dev

# Generate local TLS cert if not already present
certs:
    #!/usr/bin/env bash
    DOMAIN="${LOCAL_DOMAIN:-local.yonca-sdc.com}"
    if [ -f ".local/certs/local.crt" ] && [ -f ".local/certs/local.key" ]; then
      echo "Certs already exist — skipping. Delete .local/certs/ to regenerate."
      exit 0
    fi
    mkdir -p .local/certs
    mkcert -install
    mkcert -cert-file .local/certs/local.crt -key-file .local/certs/local.key "$DOMAIN"

# calls uv sync
sync:
    uv sync