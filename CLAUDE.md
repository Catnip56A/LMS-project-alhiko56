# Yonca — Claude Instructions

## Project
Flask LMS (Learning Management System). Python 3.13, PostgreSQL 17, Bootstrap 4, Jinja2.
See `docs/PROJECT.md` for full context.

## Dev commands
```
just up          # Docker dev stack (recommended)
just dev         # Local Flask dev server on :5000
just migrate     # Run DB migrations
just translate-all  # Full translation pipeline (needs LibreTranslate)
```

## Architecture rules
- Application factory in `yonca/__init__.py`
- Blueprints: `routes/__init__.py` (main), `routes/api.py`, `routes/auth.py`, `admin/__init__.py`
- Models all in `yonca/models/__init__.py`
- `core_translator.py` — no Flask/DB dependency, used by both runtime and dev scripts
- `translation_service.py` — runtime only, requires app context and DB

## Template structure
- `index.html` is **standalone** — no Bootstrap, no jQuery, no `site.css`. Has its own inline CSS/JS.
- All other pages extend `base.html` and include `components/navbar.html`
- `base.html` loads Bootstrap 4, Font Awesome, `site.css`
- Mobile styles shared across both: `static/css/site.css`

## Translation pipeline
Order matters: **clear → extract → update → translate → fix-placeholders → compile**

Protected brand term: `{YONCA}` placeholder in `core_translator.py`. LibreTranslate must be running (`just libre-ready`) before translating.

Two translation caches in DB: `translation` table (gettext strings) and `content_translation` table (page builder content). If placeholders appear in the UI, check both tables.

Azerbaijani (`az`) is disabled — translation quality insufficient. To re-enable: uncomment in `constants.py` and `Justfile`.

## CSS conventions
- `transform: translateY()` to shift elements without affecting layout height (not `margin-top`)
- Nav link border-radius: `6px` (matches hamburger button)
- Brand colors: green `#337a2c`, dark green `#1e5919`, cream `#fffcf0`
- Nav link pill style: `background: #fffcf0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-radius: 6px`

## Linting
Always run `uv run ruff check` on edited Python files. Fix all errors before finishing.

## Migrations
- Schema migrations: `just makemigrations message="description"`
- Data migrations: write manually in `migrations/versions/`, use SQLAlchemy constructs (no raw SQL strings), `op.get_bind().execute(sa.update(...))`

## Deployment
Push to `main` → production, `staging` → staging. GitHub Actions builds Docker image → GHCR → SSH deploy. `migrate-prod` service runs `flask db upgrade` before app starts.

## Known quirks
- `index.html` has its own duplicate navbar — changes to `components/navbar.html` do **not** affect the home page
- Gallery carousel: desktop uses `gallery-outer` flex layout with controls as siblings; mobile overrides to `position: absolute` inside the container
- `just dev` uses the same Docker PostgreSQL as `just up`; both share the DB on port 5432
