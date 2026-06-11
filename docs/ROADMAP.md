# Yonca — Development Roadmap

A chronological record of what was built and when, grouped by phase. Each phase reflects a natural shift in focus visible across the git history.

---

## Phase 1 — Foundation (Dec 5–14, 2025)

**`Initial commit`** — Repository created with `.gitattributes` only.

**`New structure, logins, courses, many to many system of users to courses`** *(Dec 14)* — The real starting point: the full Flask application skeleton was put in place. This commit introduced `app.py`, `yonca/__init__.py`, blueprints (`routes/`, `admin/`, `auth.py`, `api.py`), `models/__init__.py`, `create_user.py`, `init_db.py`, `requirements.txt`, and the first static HTML pages (`index.html`, `login.html`). Users, courses, and a many-to-many enrollment relationship were all defined here.

**`Resources update + site style changes`** *(Dec 14)* — First resource/file upload capability added; initial site styling.

**`Forum fixes` / `Forum & home (+dashboard) update`** *(Dec 14–24)* — A forum feature was built and stabilised. The home page and an admin dashboard home view (`admin home page dashboard v.1`) were also added.

**`Translation of Forum` / `Translation removal` / `Animation update`** *(Dec 24–25)* — Initial translation support was explored, then partially reverted. A background animation was added to the landing page.

**`Course major update` / `course dropdown update` / `course update and {description} tag page`** *(Dec 26)* — Courses received a major rework: course dropdowns, a dedicated description/tag page, and significant model changes.

**`PostgreSQL connected` / `PostqreSQL locally connected`** *(Dec 29–30)* — Switched the database from SQLite to PostgreSQL. Local and remote connections were both wired up.

---

## Phase 2 — Deployment & Auth Basics (Jan 1–15, 2026)

**`VPC deploy infrastructure` / `host change` / `deploy.sh`** *(early Jan)* — Early deployment scripts and systemd service configuration were added for running Yonca on a VPS. Multiple rounds of host/env-var fixes ensued (`load env`, `env vars in yonca.service`, `wsgi.py load env var`).

**`Google OAuth / Admin Google login`** *(~Jan 7–11)* — Google OAuth2 was integrated for user login. An admin-specific Google login flow was added separately (`Admin google Oauth`, `google drive update`, `login with google page changes`).

**`Secure courses` / `course url generation v2`** *(Jan 15)* — Course URLs were hardened (slug-based or token-based generation v2) and access was secured behind authentication.

**`reviews` / `reviews fix`** *(Jan 15)* — A course review/rating system was added and bugs were fixed the same day.

**`gallery` / `privacy policy and gallery`** *(Jan 15)* — A home-page gallery section was added. The Privacy Policy page was introduced.

**`Terms of service`** *(Jan)* — Terms of Use page added.

**`locking folders behind assignments`** *(Jan 23)* — Folder visibility in course contents was gated by assignment completion — folders become accessible only after the student submits their assignment.

---

## Phase 3 — Google Drive Integration & Course Contents (Jan 20–31, 2026)

**`course contents`** *(Jan 20)* — A full course contents system was implemented: files, folders, and a hierarchy visible to enrolled students.

**`drag & drop` / `root folders drag and drop` / `delete with contents`** *(Jan 22)* — Course content management got drag-and-drop reordering for files and folders, plus recursive delete.

**`bulk fix` / `select in course contents`** *(Jan 21–22)* — Bulk operations (bulk select, bulk move) on course content items.

**`file preview, no download in course contents`** *(Jan)* — Files could be previewed inline in the browser without allowing direct download, using a file viewer component.

**`import folder google drive`** *(Jan)* — Admin could import an entire Google Drive folder structure directly into a course, pulling files through the Drive API.

**`filtering on resources`** *(Jan 31)* — Resource library got a filter/search bar.

**`password hammering`** *(Jan 31)* — Rate-limiting or brute-force protection added to the login endpoint.

**`navbar update` / `footer`** *(Jan 31 – Feb)* — Navbar and footer redesigned; footer was also added to the enrolled course view.

---

## Phase 4 — Visual Overhaul & Gallery (Feb 2026)

**`bg update` / `color change` / `overflow x hide`** *(Feb 12)* — Several visual polish commits: new background, color adjustments, horizontal overflow fix.

**`gallery-popup.css` / `circle` / `logo fix`** *(Feb 12)* — A gallery popup/lightbox was styled. Profile images got a circular frame treatment. Logo positioning fixed.

**`Navbar in courses` / `fix assignments etc`** *(Feb 18)* — The navbar was added to the in-course enrolled view. Assignment submission flow bugs were fixed across about a dozen sequential fix commits (`fix`, `fix2` … `fix11`).

**`update logic CourseDesc` / `footer added to courseEnabled`** *(Feb 18)* — The course description display logic was updated; footer reached the enrolled view.

**`renewal of yonca features`** *(Feb 10)* — A broad features-page refresh on the home/about section.

**`google drive scope reduced`** *(Feb 21)* — Google Drive OAuth scope was narrowed to the minimum required permissions.

**`translation update`** *(Feb 21)* — Translation strings updated/compiled.

**`overflow scrollbar fix` / `footer update`** *(Feb 26)* — Minor responsive fixes and footer content update.

---

## Phase 5 — Page Builder & Migration Fixes (Mar 2026)

**`Course-desc update (drag & drop builder)`** *(Mar 9)* — A drag-and-drop page builder was introduced for course descriptions, allowing admins to compose rich content blocks.

**`Add page_builder.html` / `Add page_builder_utils.py`** *(Mar 9)* — The admin UI template and the backend rendering utilities for the page builder were committed.

**`migration fixes` × ~10 commits** *(Mar 9)* — A large batch of Alembic migration chain fixes: broken cycles, incorrect `down_revision` pointers, and merge conflicts across multiple migration files were all linearized and repaired.

**`migrations rewamp`** *(Mar 14)* — The migration directory was restructured for a cleaner chain going forward.

**`strip .env` × 5 commits** *(Mar 14)* — `.env` files were removed from the repository history (secrets cleanup).

**`jobman` / `backup`** *(Mar 14)* — A background job manager and a database backup utility were added.

**`shared caddy`** *(Mar 17)* — Caddy reverse proxy configuration was refactored to be shared between staging and production containers.

**`db fixes` × 3** *(Mar 17)* — Database schema or connection fixes after the Caddy/Docker restructure.

**`instructions for Magsud`** *(Mar 17)* — Developer onboarding notes committed (a collaborator was being brought on).

**`Translations`** *(Mar 19)* — Full translation pipeline run; `.po`/`.mo` files updated.

**`translation tags fix` / `trash removed`** *(Mar 22–25)* — Translation placeholder tag bugs fixed. Leftover trash/debug code removed.

**`google permissions and format fix` / `html mobile fix` ×3** *(Mar 25)* — Google Drive permission handling corrected. A round of HTML/mobile layout fixes.

**`arrow visual update` / `course title visibility`** *(Mar 23)* — Visual polish on the course listing page.

**`cleanup` × 14 commits** *(Mar 29)* — Large-scale code cleanup sweep: dead code, unused imports, and old debug statements removed.

**`youtube fix + navbar fix + page builder feature added`** *(Mar 13)* — YouTube embed support added to the page builder. Navbar bug fixed.

---

## Phase 6 — Stability, Translations & Mobile (Apr 2026)

**`wrapper fix for mobile`** *(Apr 2)* — Mobile layout wrapper fixed for the page builder hero section.

**`visual update hero` / `height change hero page builder`** *(Apr 2)* — Hero block height and visual appearance tuned in the page builder.

**`language update: AZ removed`** *(Apr 20)* — Azerbaijani was disabled as a supported language (translation quality was insufficient).

**`translations + constants`** *(Apr 22)* — Language constants updated; new translatable strings compiled.

**`visual update 1` / `logo spacing`** *(Apr 23)* — Logo spacing fixed; general visual refresh on home and about pages.

**`Google drive permission and URI fix`** *(Apr 23)* — A Google Drive OAuth URI mismatch and permission scope error fixed in production.

**`interface course content enrolled`** *(Apr 28)* — The enrolled student's view of course contents was redesigned for better usability.

**`privacy policy and terms of use Updated`** *(Apr 30)* — Legal pages content revised.

**`FIX translations az to work in legal pages`** *(Apr 30)* — Even though `az` is disabled globally, the legal pages now fall back gracefully.

---

## Phase 7 — Analytics & Optimizations (May 2026)

**`analytics v.1`** *(May 18)* — First version of course analytics: an admin view showing enrollment counts, course activity, and progress metrics with chart rendering.

**`Fix: analytics button and chart rendering`** *(May 17)* — Analytics chart rendering and the trigger button were fixed after the initial rollout.

**`optimizations fix 2.0`** *(May 18)* — Performance optimizations to the course pages (likely query reduction or lazy loading improvements).

**`Course analytics search-bar addition`** *(May 19)* — A search/filter bar was added to the analytics view so admins can find specific courses.

**`color list for analytics update`** *(May 19)* — The analytics chart color palette was updated.

**`fixed enrolled course page`** *(May 12)* — The enrolled course view was broken and repaired.

**`login + language dropdown in course enrolled view fix`** *(May 15)* — Login redirect and language switcher inside the enrolled view were fixed.

**`whatsapp invert colors`** *(May 19)* — WhatsApp button icon color scheme inverted for better contrast.

**`visual update user and language dropdowns`** *(May 21)* — User profile and language-switcher dropdowns restyled.

**`content translation moxo`** *(May 24)* — Content translation table (`content_translation`) was fixed or extended.

**`about company gallery 2`** *(May 24)* — A second gallery section was added to the About Company page.

**`buttons gallery 1+2 fix`** *(May 24)* — Navigation buttons for both gallery sections fixed.

**`file viewer limits applied`** *(May 25)* — File viewing was rate-limited or restricted based on user role/enrollment status.

**`footer privacy policy link added + translation of legal docs to azeri fixed`** *(May 25)* — Footer now links to the privacy policy. Azerbaijani translations for legal docs corrected in `.po` files.

**`decline submissions function added`** *(May 26)* — Admins/instructors can now formally decline a student's assignment submission (previously only approval existed).

**`newline in course assignments' description implemented`** *(May 26)* — Assignment descriptions now preserve line breaks when displayed.

**`bulk move fix`** *(May 26)* — Bulk-move of course content items was broken and fixed.

**`course page enrolled assignments fixes`** *(May 25)* — Several bugs in the enrolled view's assignments panel fixed.

**`deleting folders in courses fix`** *(May 25)* — Recursive folder deletion in course contents was broken and repaired.

**`Fix: Remove broken duplicate gallery_2 migration` / `Rechain gallery_2 migration` / `Repair broken auto-generated migrations`** *(May 25)* — Another round of Alembic migration chain repairs after the gallery 2 columns caused cycle conflicts.

**`limitation page — ADMIN page for limiting the users' access to pages`** *(May 27)* — A new admin panel was added allowing admins to restrict which application pages specific users or user groups can access.

---

## Phase 8 — UI Polish & Contact (Jun 2026)

**`contact us`** *(Jun 10)* — A Contact Us page/form was added to the site.

**`whatsapp button`** *(Jun 10)* — A floating WhatsApp contact button was added across the site and on course pages.

**`remove content translation from description of courses`** *(Jun 10)* — Course descriptions were removed from the content-translation system (they don't need live translation).

**`course hero fix`** *(Jun 10)* — The hero banner on course detail pages was fixed.

**`carousel rework`** *(Jun 10)* — The home-page carousel was significantly reworked for better behaviour and visual consistency.

**`icons added` / `last ui icons` / `file type icons` / `removed system icons`** *(Jun 10)* — A comprehensive icon pass: file-type icons (PDF, video, etc.) were introduced in the course content view; system navigation arrow icons were replaced or removed.

**`button size + hero bg fix`** *(Jun 10)* — Button sizing standardised; hero background colour fixed.

**`opacity bg tweak` / `visual update`** *(Jun 10)* — Background opacity and general visual polish.

**`mobile fix` / `mobile builder fix`** *(Jun 10)* — Mobile layout fixes on general pages and inside the page builder.

**`zoom reduced page builder`** *(Jun 10)* — The page builder canvas zoom level was reduced for a better editing experience on normal screens.

**`indent fix` / `margin fix` × 3** *(Jun 9)* — Text indentation and spacing fixed in the enrolled course view.

**`update of course enrolled`** *(Jun 9)* — Visual and UX update to the enrolled course page.

**`useless icon removed + icons added`** *(Jun 11)* — Further icon cleanup; new icons added where needed.

**`courses length of items logic reworked`** *(Jun 11)* — The logic for displaying item counts (files, folders) in course listings was reworked for accuracy.

**`rework of enrolled icon`** *(Jun 11)* — The enrolled-status icon was redesigned.

**`fonts (montserrat)`** *(Jun 11)* — Montserrat was set as the primary font family (flagged as subject to future change).

**`visual fixes`** *(Jun 11)* — General visual cleanup pass.

**`wheel gallery 1 about us fix`** *(Jun 11)* — The circular/wheel-style gallery on the About Us section was fixed.

**`limits added + po translation fix`** *(Jun 11)* — Enrollment or file-access limits were applied to more areas; `.po` translation file corrected.

---

## Ongoing / Cross-Cutting

- **Translation pipeline** — LibreTranslate-backed gettext translations (`az` disabled, `ru`/`en` active) were continuously maintained throughout. The two-table system (`translation` for gettext, `content_translation` for page builder content) evolved across many commits.
- **Migration fixes** — Alembic migration chains broke repeatedly as features were developed in parallel; multiple dedicated fix sessions occurred (Jan, Mar, May 2026).
- **Cleanup sweeps** — A pattern of rapid feature development followed by cleanup/debug-removal commits appears throughout.
- **Google Drive** — The Drive integration evolved from a basic service-account setup → full OAuth2 → import folders → scope reduction → URI fixes over roughly four months.
- **Deployment** — The stack moved from a simple VPS systemd service → nginx → Caddy → Docker Compose with GitHub Actions CI/CD pushing to GHCR and SSH-deploying to staging and production.
