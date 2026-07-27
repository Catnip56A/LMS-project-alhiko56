# LMS — Claude Instructions

## Project
Flask LMS (Learning Management System). Python 3.13, PostgreSQL 17, Bootstrap 4, Jinja2.
See `docs/PROJECT.md` for full context.

## Dev commands
```
just up                    # Docker dev stack (recommended)
just dev                   # Local Flask dev server on :5000
just migrate               # Run DB migrations
just translate-all         # Full translation pipeline (needs DEEPL_API_KEY in .env)
just make-admin <username> # Promote an existing user to full admin (Docker dev)
```

## Architecture rules
- Application factory in `lms/__init__.py`
- Blueprints: `routes/__init__.py` (main), `routes/api.py`, `routes/auth.py`, `admin/__init__.py`
- Models all in `lms/models/__init__.py`
- `core_translator.py` — no Flask/DB dependency, used by both runtime and dev scripts
- `translation_service.py` — runtime only, requires app context and DB

## Admin permission tiers
Three tiers: **Full admin** (`is_admin=True`, `admin_permissions=NULL`) → **Sub-admin** (`is_admin=True`, `admin_permissions=[list]`) → **Regular user** (`is_admin=False`).

- `user.has_perm('key')` — use this everywhere for gate checks; returns False if not `is_admin`, True if full admin, checks list for sub-admins
- `user.is_full_admin` — True only if `is_admin=True` AND `admin_permissions=NULL`
- `user.any_admin` — True if `is_admin=True` (regardless of permissions)
- Permission keys defined in `ADMIN_PERMISSIONS` constant in `admin/__init__.py`
- Each `SecureModelView` subclass sets `permission = 'key'`; each `BaseView` overrides `is_accessible()` to call `has_perm('key')`
- Only full admins can access `/admin/user_permissions/` to assign permissions to other admins
- Regular users (`is_admin=False`) cannot be sub-admins — `admin_permissions` on a non-admin has no effect

## Template structure
- `index.html` is **standalone** — no Bootstrap, no jQuery, no `site.css`. Has its own inline CSS/JS.
- All other pages extend `base.html` and include `components/navbar.html`
- `base.html` loads Bootstrap 4, Font Awesome, `site.css`
- Mobile styles shared across both: `static/css/site.css`

## Translation pipeline
Order matters: **clear → extract → update → translate → fix-placeholders → compile**

Backend: DeepL (`DEEPL_API_KEY` in `.env`) — no local service to run, just needs the key set.
Protected brand term: `{LMS}` placeholder in `core_translator.py`.

Two translation caches in DB: `translation` table (gettext strings) and `content_translation` table (page builder content). If placeholders appear in the UI, check both tables.

Course content translation is queued through the RQ job system (`lms/job_manager.py`), not
synchronous: a `translate_course` job fires right after a course create/edit (the
"threshold" trigger), and a `translate_content` full-catalog sweep re-schedules itself every
24h (the "interval" trigger, bootstrapped by `lms/worker.py` via `ensure_translation_sweep_scheduled()`
using RQ's built-in scheduler — no extra process). The admin panel's "Translate" button still
queues an on-demand `translate_content` job too.

Azerbaijani (`az`) has been removed entirely — DeepL doesn't support it, and the prior
engine's translation quality for it was insufficient anyway. It's gone from
`constants.py`, the locale selector, `.po` files, and the legal pages — re-adding it would
mean a different translation engine plus UI/legal-page work, not just a flag flip.

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
