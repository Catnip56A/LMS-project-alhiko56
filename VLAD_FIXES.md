# Fixes — 2026-05-19

## Translation System

### `yonca/constants.py`
- Added `az` (Azerbaijani) to `SUPPORTED_LANGUAGES` and `LANGUAGE_NAMES`, then commented it out after quality was deemed insufficient. Easy to re-enable.

### `yonca/core_translator.py`
- Added `translate_batch()` — sends up to 50 strings per HTTP request instead of one per string. Massively speeds up PO file translation.
- Replaced broken `{PROTECTED_0}` placeholder scheme with `{YONCA}` (all-caps, no underscores). LibreTranslate was converting the underscore to a space, producing `{PROTECTED 0}` which could never be restored.
- Simplified `PROTECTED_TERMS` from three redundant case variants to one IGNORECASE pattern.

### `scripts/translations/auto_translate_po.py`
- Switched to `translate_batch()` — O(N/50) HTTP calls instead of O(N).
- `en → en` entries now handled by copying `msgid → msgstr` with no API call.
- Removed `time.sleep(0.2)` (was leftover Google rate-limit delay, irrelevant for local LibreTranslate).

### `scripts/translations/fix_placeholders_v2.py`
- Full rewrite using `polib` instead of hand-rolled regex PO parser. Old version had three bugs: multiline entries included raw quotes, reconstruction corrupted files, positional fix was fragile.
- Added `fix_protected_artifacts()` — replaces leftover `{PROTECTED N}` / `{PROTECTED_N}` patterns with "Yonca".
- Path now uses `Path(__file__).parent...` so it works from any directory.

### `Justfile`
- Added `_libre_url` variable (reads `LIBRETRANSLATE_URL` env, falls back to `http://localhost:5050`).
- Added `libre-ready` recipe — polls `/languages` every 3s up to 2 minutes before proceeding. Fixes race condition where translation started before LibreTranslate models finished loading.
- Fixed `translate-all` order: was compiling `.mo` before translating (useless). Now: clear → extract → update → **translate** → **fix placeholders** → **compile** → stop LibreTranslate.
- `az` removed from `--load-only` since it's disabled.

### `.dockerignore`
- Added exclusions for `.po`, `.po.*` (backups), and `messages.pot`. Only compiled `.mo` files needed at runtime.

### `migrations/versions/20260519_fix_protected_placeholders_in_translation_cache.py`
- Alembic data migration that cleans `{PROTECTED N}` / `{PROTECTED_N}` artifacts from both `translation` and `content_translation` tables using SQLAlchemy (no raw SQL). Runs automatically on deploy via `flask db upgrade`.

### DB hotfix (manual, staging)
- Fixed 9 broken rows in `translation` table and 15 in `content_translation` table where `{PROTECTED 0}` appeared instead of "Yonca".

---

## UI — `yonca/templates/index.html`

### Navbar
- Removed the broken `auth-toggle-btn` popup mechanism (`‹auth-section.show›` was `position: absolute; left: 50%` — appeared in the middle of the page).
- `nav-auth-container` changed from `flex-direction: column` to `flex-direction: row`: nav links left-aligned next to logo, auth pushed to far right via `margin-left: auto`.
- Language picker: two CSS pill buttons (EN / RU) — no Bootstrap needed since index.html doesn't load Bootstrap.
- `auth-section` hidden at mobile (`max-width: 768px`); hamburger menu handles it.
- Mobile header: `flex-direction: row`, logo left (`margin-left: 1rem`), hamburger right (`margin-left: auto`). Was previously stacking vertically with logo centered.
- Logo position tuned: `margin-left: 0.875rem`, `margin-right: 3.625rem`, `transform: translateY(0.4rem)`.
- Auth section: `transform: translateY(5px)`, extra `margin-left: 0.75rem` between lang pills and login.
- `.nav-link` border-radius: `20px → 6px` to match hamburger button.
- `.mobile-nav-menu .nav-link` border-radius: `20px → 6px`.

### Gallery carousel (What's New)
- Wrapped `gallery-container` and controls in `gallery-outer` (`display: flex; align-items: center`). Controls are now siblings of the container, not inside it — they appear outside the video strip on desktop.
- Controls: `flex-shrink: 0`, `margin: 0 1.25rem`, `transform: translateY(-25px)`.
- Mobile override: `gallery-outer` becomes `display: block; position: relative`; controls revert to `position: absolute` overlaid on video at `top: 38%`, `left/right: calc(3% + 20px)`.
- `gallery-container` width on mobile: `94%`, `margin: 0 auto`.
- `--gallery-item-width: 100%` on mobile (no side-peek), `gallery-media-viewport` full width.
- `margin-bottom: 1.5rem` on gallery container (mobile).

### Features section ("Points of interest")
- Added `padding: 0 1.5rem` to `.features-section` so cards don't touch viewport edges.

### Header mobile
- `margin-bottom: 1.5rem` on header to separate navbar from content.

---

## UI — `yonca/templates/components/navbar.html`

- Language picker: standalone Bootstrap dropdown (`🌐 EN ▼`) — separate from user dropdown.
- Logged-out state: visible "Login" link instead of invisible empty dropdown toggle.
- User dropdown: language removed, only profile actions remain.
- Mobile: language shown as two pill buttons side-by-side (EN / RU) with `active` highlight.
- `.mobile-nav-menu .nav-link` border-radius: `20px → 6px`.
- `.navbar .nav-link` border-radius: `20px → 6px`.
- Mobile lang pill styles moved to `static/css/site.css` (shared with index.html).

### `static/css/site.css`
- Added `.mobile-lang-picker` and `.mobile-lang-btn` styles (shared between navbar component and index.html's standalone header).
