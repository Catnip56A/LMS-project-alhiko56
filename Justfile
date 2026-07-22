set dotenv-load

_ssh_host  := env('SSH_HOST', 'yourdomain.example.com')
_libre_url := env('LIBRETRANSLATE_URL', 'http://localhost:5050')

default:
   just --list

# SSH tunnels for remote DBs
db-tunnel-prod:
    ssh -L 5439:127.0.0.1:5439 {{_ssh_host}} -N

db-tunnel-staging:
    ssh -L 5438:127.0.0.1:5438 {{_ssh_host}} -N

# Pull DB from production live (streams directly, no temp file)
db-pull-production:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'echo "Error on line $LINENO"' ERR

    app_running=$(docker compose --profile dev ps -q app-dev 2>/dev/null)
    if [ -n "$app_running" ]; then
        echo "Stopping app-dev..."
        docker compose --profile dev stop app-dev
    fi

    echo "Restoring database from production..."
    ssh {{_ssh_host}} "docker compose -f ~/deploy/production/lms/docker-compose.yml exec -T db-production pg_dump -U lms_user -Fc lms_db" \
      | docker compose exec -T db-dev pg_restore -U lms_user -d lms_db --clean --if-exists --no-owner --no-acl
    echo "Database restored successfully"

    echo "Stamping database version..."
    docker compose --profile dev run --rm migrate-dev flask db stamp head || { echo "Stamp failed with $?"; exit 1; }
    echo "Database stamped successfully"

    if [ -n "$app_running" ]; then
        echo "Restarting app-dev..."
        docker compose --profile dev start app-dev
    fi

    echo "Done!"

# Pull DB from staging live (streams directly, no temp file)
db-pull-staging:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'echo "Error on line $LINENO"' ERR

    app_running=$(docker compose --profile dev ps -q app-dev 2>/dev/null)
    if [ -n "$app_running" ]; then
        echo "Stopping app-dev..."
        docker compose --profile dev stop app-dev
    fi

    echo "Restoring database from staging..."
    ssh {{_ssh_host}} "docker compose -f ~/deploy/staging/lms/docker-compose.yml exec -T db-staging pg_dump -U lms_user -Fc lms_db" \
      | docker compose exec -T db-dev pg_restore -U lms_user -d lms_db --clean --if-exists --no-owner --no-acl
    echo "Database restored successfully"

    echo "Stamping database version..."
    docker compose --profile dev run --rm migrate-dev flask db stamp head || { echo "Stamp failed with $?"; exit 1; }
    echo "Database stamped successfully"

    if [ -n "$app_running" ]; then
        echo "Restarting app-dev..."
        docker compose --profile dev start app-dev
    fi

    echo "Done!"

# Pull latest backup from server
db-pull-backup:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'echo "Error on line $LINENO"' ERR

    app_running=$(docker compose --profile dev ps -q app-dev 2>/dev/null)
    if [ -n "$app_running" ]; then
        echo "Stopping app-dev..."
        docker compose --profile dev stop app-dev
    fi

    echo "Restoring database from latest backup..."
    ssh {{_ssh_host}} "cat $(ls -t ~/backup/lms/staging/*.dump | head -1)" \
      | docker compose exec -T db-dev pg_restore -U lms_user -d lms_db --clean --if-exists --no-owner --no-acl
    echo "Database restored successfully"

    echo "Stamping database version..."
    docker compose --profile dev run --rm migrate-dev flask db stamp head || { echo "Stamp failed with $?"; exit 1; }
    echo "Database stamped successfully"

    if [ -n "$app_running" ]; then
        echo "Restarting app-dev..."
        docker compose --profile dev start app-dev
    fi

    echo "Done!"

# Derived vars for local (non-Docker) execution — mirrors docker-compose behaviour
_db_url  := "postgresql://" + env('POSTGRES_USER', 'lms_user') + ":" + env('POSTGRES_PASSWORD', 'changeme') + "@127.0.0.1:5432/" + env('POSTGRES_DB', 'lms_db')
_redir   := "http://localhost:5000/auth/google/callback"

# Install dependencies
install:
    uv sync

ensure-dirs:
    mkdir -p ./data/libretranslate ./data/caddy-local ./data/logs ./data/flask_session
    chmod a+rwx ./data/libretranslate ./data/caddy-local ./data/logs ./data/flask_session

db:
    docker compose --profile dev up db-dev migrate-dev -d
# Run dev server (local, no Docker)
dev: db
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run flask run --debug --host=0.0.0.0 --port=5000

# Run with gunicorn (local, no Docker)
serve:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run gunicorn --config deploy/gunicorn_config.py app:app

# Run app.py directly (local, no Docker)
app: db
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run python app.py

# Run wsgi.py with gunicorn (local, no Docker)
wsgi: db
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run gunicorn --config deploy/gunicorn_config.py wsgi:app

# Flask shell (local)
shell:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run flask shell

# Create admin user (local)
create-admin:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run python scripts/admin/create_admin.py

# Promote an existing user to full admin (Docker dev)
make-admin username:
    docker compose --profile dev run --rm \
      -v {{justfile_directory()}}/scripts:/app/scripts \
      -e DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db-dev:5432/${POSTGRES_DB} \
      -e GOOGLE_REDIRECT_URI=https://localhost/unused \
      app-dev python scripts/admin/make_full_admin.py {{username}}

# Analytics scripts (local)
analytics-views:
    DATABASE_URL={{_db_url}} GOOGLE_REDIRECT_URI={{_redir}} uv run python scripts/analytics/view_times.py

# Database migrations (via Docker)
migrate:
    docker compose --profile dev run --rm migrate-dev

makemigrations message="auto":
    docker compose --profile dev run --rm migrate-dev flask db migrate -m "{{message}}"

# Mark DB as up-to-date without running migrations (use after squash on existing DB)
db-stamp:
    docker compose --profile dev run --rm migrate-dev flask db stamp head

# Run LibreTranslate locally for dev-time translation (PO files, testing)
# Binds to localhost:5050. Stop with: docker stop lms-libretranslate
libre:
    #!/usr/bin/env bash
    mkdir -p ./data/libretranslate
    chmod a+rwx ./data/libretranslate
    if docker inspect lms-libretranslate > /dev/null 2>&1; then
      echo "LibreTranslate already running."
    else
      docker run -d --rm \
        --name lms-libretranslate \
        -p 127.0.0.1:5050:5000 \
        -v "$(pwd)/data/libretranslate:/home/libretranslate/.local/share" \
        libretranslate/libretranslate \
        --load-only en,ru  # az disabled — translation quality insufficient
      echo "LibreTranslate starting at http://localhost:5050 (may take a minute to load models)"
      echo "Stop with: docker stop lms-libretranslate"
    fi

# Poll LibreTranslate until it responds (max 2 min). Depends on libre so it
# can be used as a dependency instead of libre directly.
libre-ready: libre
    #!/usr/bin/env bash
    echo "Waiting for LibreTranslate to be ready..."
    for i in $(seq 1 40); do
        if curl -sf "{{_libre_url}}/languages" > /dev/null 2>&1; then
            echo "LibreTranslate is ready."
            exit 0
        fi
        echo "  ($i/40) not ready yet, retrying in 3s..."
        sleep 3
    done
    echo "ERROR: LibreTranslate did not become ready within 2 minutes."
    exit 1

# Compile translations
translate-compile:
    uv run pybabel compile -d lms/translations

extract-messages:
    uv run pybabel extract -F lms/babel.cfg -o lms/translations/messages.pot lms

translate-all: libre-ready
    uv run pybabel extract -F lms/babel.cfg -o lms/translations/messages.pot lms
    uv run pybabel update -i lms/translations/messages.pot -d lms/translations
    uv run python scripts/translations/auto_translate_po.py
    uv run python scripts/translations/fix_placeholders_v2.py
    uv run pybabel compile -f -d lms/translations
    docker stop lms-libretranslate

# Nuclear reset: clears ALL translations then re-translates everything from scratch
translate-reset: libre-ready
    uv run python scripts/translations/clear_all_po_translations.py
    uv run pybabel extract -F lms/babel.cfg -o lms/translations/messages.pot lms
    uv run pybabel update -i lms/translations/messages.pot -d lms/translations
    uv run python scripts/translations/auto_translate_po.py
    uv run python scripts/translations/fix_placeholders_v2.py
    uv run pybabel compile -f -d lms/translations
    docker stop lms-libretranslate

translate-fix-placeholders: libre-ready
    uv run python scripts/translations/fix_placeholders_v2.py


# Docker — dev
up: ensure-dirs certs
    docker compose --profile dev up -d

down:
    docker compose --profile dev down

build:
    docker compose build

rebuild: ensure-dirs certs
    docker compose --profile dev up -d --build

logs:
    docker compose --profile dev logs -f app-dev

# Generate local TLS cert if not already present
certs:
    #!/usr/bin/env bash
    DOMAIN="${LOCAL_DOMAIN:-local.yourdomain.example.com}"
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

# Push static/permanent/UI to GHCR as a private image (designer runs this after adding files)
# One-time setup: docker login ghcr.io -u <github-username> -p <PAT with write:packages scope>
ui-assets-push:
    #!/usr/bin/env bash
    set -euo pipefail
    owner=$(echo "${GHCR_OWNER:?set GHCR_OWNER in .env}" | tr '[:upper:]' '[:lower:]')
    docker build -f deploy/ui-assets.Dockerfile -t "ghcr.io/$owner/lms-ui-assets:latest" .
    docker push "ghcr.io/$owner/lms-ui-assets:latest"
    echo "Pushed ghcr.io/$owner/lms-ui-assets:latest"
    echo "First time only: on github.com, open the lms-ui-assets package settings and set visibility to Private."

# Pull the latest designer UI assets from GHCR into static/permanent/UI
# One-time setup: docker login ghcr.io -u <github-username> -p <PAT with read:packages scope>
ui-assets-pull:
    #!/usr/bin/env bash
    set -euo pipefail
    owner=$(echo "${GHCR_OWNER:?set GHCR_OWNER in .env}" | tr '[:upper:]' '[:lower:]')
    docker pull "ghcr.io/$owner/lms-ui-assets:latest"
    cid=$(docker create "ghcr.io/$owner/lms-ui-assets:latest")
    docker cp "$cid:/assets/." static/permanent/UI/
    docker rm "$cid" > /dev/null
    echo "Synced into static/permanent/UI/"
