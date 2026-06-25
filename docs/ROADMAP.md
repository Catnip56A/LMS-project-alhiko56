# Yonca — Development Roadmap

A chronological record of what was built and when, grouped by phase. Each phase reflects a natural shift in focus visible across the git history.

---

## Phase 1 — Foundation (Dec 5–30, 2025)

**`Initial commit`** *(Dec 5)* — Repository created with `.gitattributes` only.

**`New structure, logins, courses, many to many system of users to courses`** *(Dec 14)* — The real starting point: the full Flask application skeleton was put in place. This commit introduced `app.py`, `yonca/__init__.py`, blueprints (`routes/`, `admin/`, `auth.py`, `api.py`), `models/__init__.py`, `create_user.py`, `init_db.py`, `requirements.txt`, and the first static HTML pages (`index.html`, `login.html`). Users, courses, and a many-to-many enrollment relationship were all defined here.

**`Resources update + site style changes`** *(Dec 14)* — First resource/file upload capability added; initial site styling applied.

**`Forum fixes`** *(Dec 14)* — A forum feature was scaffolded and stabilised: posts, threading, basic forum navigation.

**`Translation and forum replies update`** *(Dec 15)* — Forum reply functionality added. First attempt at a translation layer introduced.

**`Minor improvements (Structure, Log out buttons)`** *(Dec 23)* — Structural cleanup, logout buttons added across views, small UX improvements.

**`Repository structural update` / `ReadMe update`** *(Dec 23)* — Project file layout reorganised; README written.

**`admin home page dashboard v.1`** *(Dec 24)* — The Flask-Admin panel received a custom home dashboard showing a summary view of the application state.

**`Forum & home (+dashboard) update`** *(Dec 24)* — Forum and the main landing page were updated together; home page content expanded.

**`Animation update`** *(Dec 24)* — A background animation was added to the landing page for visual interest.

**`Translation removal` / `Translation of Forum`** *(Dec 24–25)* — Initial translation support was explored for the forum, then partially reverted as the approach needed rethinking.

**`Course major update` / `course dropdown update` / `course update and {description} tag page`** *(Dec 26)* — Courses received a major rework: course dropdowns for navigation, a dedicated description/tag detail page, and significant model changes to support richer course metadata.

**`PostgreSQL connected` / `PostqreSQL locally connected`** *(Dec 29–30)* — Switched the database from SQLite to PostgreSQL. Both a remote VPS connection and a local dev connection were wired up and tested.

---

## Phase 2 — Google Drive, Deployment & Auth (Jan 1–19, 2026)

### Early Infrastructure (Jan 1–6)

**`Courses Update (restoration)`** *(Jan 1)* — Course model and routes were restored/repaired after the Dec 26 rework caused regressions.

**`PIN changes` / `Full integration of google drive`** *(Jan 3)* — PIN-based access flow updated. Google Drive was fully integrated for the first time: service accounts, Drive API calls, and file linking to course resources.

**`cpanel.yml` / shared hosting fixes** *(Jan 4)* — A brief attempt to deploy on shared cPanel hosting (with five fix commits for shared-hosting shortcomings). This approach was quickly abandoned in favour of a VPS.

**`create_admin.py` / `reset_db.py` / `frontend update`** *(Jan 6)* — Management scripts added for creating admin users and resetting the database. Frontend received a visual update. PostgreSQL user was standardised (`alhiko56` → `postgres`).

**`host change` × 3 / `Initial plan`** *(Jan 5–6)* — VPS hostname/IP updated across configs. An initial plan document was committed describing the intended architecture.

### Google Drive Deep Integration (Jan 7–10)

**`google drive update` × 2** *(Jan 7)* — Drive API wrapper improved; file listing and access flow refined.

**`service account for google drive API`** *(Jan 8)* — Service account authentication finalised; supports all shared drives, not just personal drives.

**`Oauth2 google drive` / `Admin google Oauth` / `login with google page changes`** *(Jan 9)* — OAuth2 flow for Google Drive implemented. Admin-specific Google login added separately. Login page redesigned to accommodate Google sign-in button.

**`google drive update + google account binding` / `URI fix` / `drive_links`** *(Jan 10)* — Google accounts can now be bound to existing Yonca user accounts. OAuth redirect URI fixed. Drive file links stored and surfaced in the UI.

### VPS Deployment (Jan 11–13)

**`nginx fix` × 5 / `superuser privileges` / `ownership reassign`** *(Jan 11)* — nginx reverse proxy configuration worked through five fix iterations. Systemd service permissions and file ownership were set correctly.

**`decreased scope`** *(Jan 11)* — Google Drive OAuth scope was narrowed early to reduce permissions requested.

**`Terms of service`** *(Jan 12)* — Terms of Use page added to the site. Route handling for `/` was also corrected.

**`wsgi.py` fixes × 6 / `load env` / `deploy.sh`** *(Jan 13)* — WSGI entry point stabilised: environment variables load correctly, `deploy.sh` script automated the server update process.

### Course Polish & Access Control (Jan 15–16)

**`secure courses` / `course url generation v2`** *(Jan 15)* — Course URLs were hardened (token-based generation v2) and course pages were secured behind authentication checks.

**`reviews` / `reviews fix` × 2** *(Jan 15)* — A course review and star-rating system was added and two rounds of bugs were fixed.

**`gallery` / `privacy policy and gallery`** *(Jan 15)* — A photo gallery section was added to the home page. The Privacy Policy page was introduced.

**`google authentication` / `google login fix`** *(Jan 16)* — Google OAuth login flow was fully stabilised; edge cases in callback handling were fixed.

**`fonts` / `font sizes`** *(Jan 16)* — Custom fonts added to the app. Font sizes tuned across pages.

**`resource page image preview`** *(Jan 16)* — Resources in the library can now display an image preview alongside the file.

**`permissions update` / `img extension check` / `file permissions`** *(Jan 16)* — File upload permission checks added; allowed image extensions validated; general file-access permissions tightened.

**`desc for enrolled`** *(Jan 16)* — Course description is now shown inside the enrolled course view.

**`nav bar courses` / `text editing course features` / `\n in feature description`** *(Jan 16)* — Course feature descriptions gained newline support. The navbar inside courses was adjusted. Feature text editing improved.

### Translation Infrastructure (Jan 18–19)

**`translation upgrade` / `lingua button`** *(Jan 18)* — Translation infrastructure upgraded; a language-switcher "lingua" button was added to the UI.

**`improved translations + progress indicator`** *(Jan 19)* — Translation quality improved; a loading/progress indicator was added for async translation jobs.

**`bg task fix` / `langdetect` / `auto_translate move`** *(Jan 19)* — Background translation task stabilised. Language detection (`langdetect`) integrated. Auto-translate code moved to the correct module.

---

## Phase 3 — Course Contents & Backup System (Jan 20 – Feb 9, 2026)

### Course Contents System (Jan 20–22)

**`course contents`** *(Jan 20)* — A full course contents system was implemented: files, folders, and a hierarchy visible to enrolled students. Items can be organised into nested folders by admins.

**`import folder google drive` / `navbar courses`** *(Jan 20)* — Admins can import an entire Google Drive folder structure directly into a course, pulling files through the Drive API. Navbar inside enrolled course pages was added.

**`file preview, no download in course contents`** *(Jan 20)* — Files in course contents can be previewed inline in the browser (PDF, video, images) without exposing a direct download link.

**`select in course contents` / `email fix`** *(Jan 21)* — Bulk-select of course content items implemented. Email handling bug fixed.

**`drag & drop` / `root folders drag and drop` / `delete with contents`** *(Jan 22)* — Course content management gained drag-and-drop reordering for both files and top-level folders. Recursive deletion (folder + all children) implemented.

**`bulk fix`** *(Jan 22)* — Bulk operations on course content items (move, delete) were fixed after the drag-and-drop rework.

**`clear tokens and fix scope` / `request access google drive error fix`** *(Jan 22)* — Google Drive OAuth token storage cleaned up. Error handling for "request access" scenarios improved.

### Course & Gallery Expansion (Jan 23–31)

**`locking folders behind assignments`** *(Jan 23)* — Folder visibility in course contents was gated by assignment completion — a folder stays locked until the student submits its prerequisite assignment.

**`po translations`** *(Jan 23)* — `.po` translation files were updated with new strings from the course contents feature.

**`button in features` / `font`** *(Jan 24–25)* — A call-to-action button was added to the course features section. Font styling adjusted.

**`about company page`** *(Jan 28)* — A dedicated About Company page was added with company information, team section, and initial gallery layout.

**`gallery + db migration`** *(Jan 28)* — Home page gallery received a Alembic migration to persist gallery images in the database. Production images uploaded.

**`lang for features`** *(Jan 29)* — Course feature descriptions were made translatable via the gettext pipeline.

**`logo update`** *(Jan 31)* — Site logo updated.

**`course preview no time slot`** *(Jan 31)* — The course preview card no longer shows an empty time slot field if no time is set.

**`filtering on resources`** *(Jan 31)* — Resource library got a filter/search bar to find resources by name or type.

**`navbar update` / `footer changes`** *(Jan 31)* — Navbar restyled; footer redesigned and unified across all page templates.

**`password hammering`** *(Jan 31)* — Rate-limiting added to the login endpoint to defend against brute-force attacks.

### Backup System & Course Polish (Feb 5–9)

**`postgres_backup` / `backup_db.sh` / `restore_db.sh`** *(Feb 5–6)* — PostgreSQL database backup and restore scripts were written and iteratively improved across a dozen commits. These scripts became the primary data safety mechanism before Docker volumes took over.

**`postgres transfer` / `changes`** *(Feb 6)* — Tooling added for transferring the PostgreSQL database between environments.

**`instance folder fix`** *(Feb 5)* — Flask instance folder path was corrected so config files load from the right location.

**`enrolled course tick alignment`** *(Feb 8)* — The assignment completion tick/checkmark in the enrolled view was misaligned; fixed.

**`tags in courses` / `translation tags in courses`** *(Feb 9)* — Course content items gained tag support. Tag rendering was wired into the translation pipeline.

**`rendering changes` / `fixes width + translation for loading`** *(Feb 9)* — Page rendering pipeline improved; width constraints fixed; a loading placeholder added while translations resolve.

---

## Phase 4 — Visual Overhaul & About Company (Feb 10–26, 2026)

**`renewal of yonca features`** *(Feb 10)* — A broad features-page refresh on the home/about section: updated copy, layout improvements, new visual components.

**`Ignore service account keys` / `Make backup script executable`** *(Feb 10)* — Service account key files added to `.gitignore`. Backup script permissions fixed.

**`bg update` / `overflow x hide` / `logo fix`** *(Feb 12)* — New background image applied. Horizontal overflow causing layout shift was hidden. Logo positioning corrected.

**`color change` / `change style buttons`** *(Feb 12)* — Brand color palette adjusted; button styles updated to match.

**`gallery-popup.css`** *(Feb 12)* — Gallery lightbox/popup was styled: fade-in animation, close button, keyboard navigation.

**`circle`** *(Feb 12)* — Profile images and gallery thumbnails adopted circular framing.

**`fix` × 5 (assignment bugs)** *(Feb 12)* — A series of five fix commits addressed regressions introduced by the visual rework on the assignment submission flow.

**`Navbar in courses`** *(Feb 18)* — The site navbar was added to the in-course enrolled view (it had been absent, making navigation out of a course impossible without the browser back button).

**`fix assignments etc` / `fix2` – `fix11`** *(Feb 18)* — Ten sequential fix commits stabilised the assignment submission, grading, and progress-tracking flows after the navbar addition and layout changes.

**`update logic CourseDesc`** *(Feb 18)* — The logic for displaying the course description page was refactored for correctness; conditional blocks cleaned up.

**`footer added to courseEnabled`** *(Feb 18)* — Site footer was added to the enrolled course view, completing consistent footer coverage across all pages.

**`google drive scope reduced` / `button fix`** *(Feb 21)* — Google Drive OAuth scope was narrowed to the minimum set of permissions actually required. A button style bug introduced in the scope change was fixed.

**`translation update`** *(Feb 21)* — Translation strings updated and `.mo` files recompiled.

**`overflow scrollbar fix` / `footer update`** *(Feb 26)* — Page-level overflow causing a spurious scrollbar was fixed. Footer content and links updated.

**`index update`** *(Feb 26)* — Home page (`index.html`) content and layout updated.

---

## Phase 5 — Page Builder, Infrastructure & Translation Engine (Mar 2026)

### Pre-Builder Polish (Mar 2–8)

**`carousel timer change`** *(Mar 2)* — Home page carousel auto-play interval adjusted.

**`courses + footer + tag + translation upgrade`** *(Mar 2)* — Course listing page, footer, tags, and translation handling all received improvements in a single coordinated commit.

**`language order` / `circular frame gallery changes`** *(Mar 3)* — Language switcher order was fixed. Gallery circular frame styling refined.

**`font update`** *(Mar 3)* — Font choices updated across the site.

**`tags fix gallery`** *(Mar 3)* — Gallery item tags were not rendering correctly; fixed.

**`About company update`** *(Mar 6)* — About Company page content, layout, and services section updated.

**`visual update + refresh fixes`** *(Mar 8)* — General visual refresh; page state was not clearing on navigation in some views; fixed.

### Page Builder (Mar 9–14)

**`Course-desc update (drag & drop builder)`** *(Mar 9)* — A drag-and-drop page builder was introduced for course description pages, allowing admins to compose rich content blocks (hero, text, gallery, video, etc.) without writing HTML.

**`Add page_builder.html` / `Add page_builder_utils.py`** *(Mar 9)* — The admin UI template (`page_builder.html`) and the backend rendering utilities (`page_builder_utils.py`) were committed as separate focused commits.

**`migration fixes` × 10** *(Mar 9)* — A large batch of Alembic migration chain fixes: broken cycles, incorrect `down_revision` pointers, and merge conflicts across multiple migration files were all linearised and repaired.

**`translation and button fix` / `fix qorunmali in translations` / `Update translation_service.py`** *(Mar 12)* — Translation service was updated to handle a problematic edge case (`qorunmali`). Button rendering in translated pages fixed.

**`youtube fix + navbar fix + page builder feature added`** *(Mar 13)* — YouTube embed block type added to the page builder. Navbar bug inside builder view fixed.

**`opacity change courses`** *(Mar 14)* — Course card background opacity adjusted.

**`migrations rewamp`** *(Mar 14)* — Migration directory was restructured: files renamed, chain linearised, ready for clean forward migration.

**`strip .env` × 5** *(Mar 14)* — `.env` files accidentally committed to history were scrubbed across five history-rewrite commits.

**`backup` / `jobman`** *(Mar 14)* — A database backup utility and a background job manager (`jobman`) were added.

**`fix healthcheck`** *(Mar 14)* — Docker health check for the web container was fixed after the migrations rework broke it.

**`fix google url` × 2** *(Mar 14)* — Google OAuth callback URL was broken after the deployment restructure; patched.

### Deployment & Docker Compose (Mar 16–17)

**`google cli`** *(Mar 16)* — Google Cloud CLI tooling added to the Docker build for Drive/OAuth management.

**`shared caddy`** *(Mar 17)* — Caddy reverse proxy configuration was refactored to be shared between staging and production containers, reducing duplication.

**`db fixes` × 3** *(Mar 17)* — Database connection and schema fixes after the Caddy/Docker restructure changed container networking.

**`instructions for Magsud`** *(Mar 17)* — Developer onboarding documentation committed for a collaborator joining the project.

**`just`** *(Mar 17)* — `Justfile` added: `just up`, `just dev`, `just migrate`, and other developer shortcuts codified as runnable recipes.

### Translation & Cleanup (Mar 19–Apr 12)

**`Translations`** *(Mar 19)* — Full translation pipeline run: extract → update → translate → compile. Russian and English `.po`/`.mo` files updated.

**`dockerignore` / `.mo files`** *(Mar 21–22)* — `.dockerignore` updated to exclude compiled translation files from the build context; `.mo` files committed separately.

**`translation tags fix`** *(Mar 22)* — Translation placeholder tags were being double-escaped or stripped in some page builder blocks; fixed.

**`trash removed + translation(content) tag bug fix`** *(Mar 25)* — Leftover debug code removed. Content-translation tag bug in page builder blocks fixed.

**`google permissions and format fix`** *(Mar 25)* — Google Drive permission scope handling corrected after a production incident.

**`html mobile fix` × 3** *(Mar 25)* — Three rounds of HTML/mobile layout fixes for the course description page on small screens.

**`arrow visual update` / `course title visibility`** *(Mar 23)* — Visual polish on the course listing page: navigation arrows redesigned, course title contrast improved.

**`cleanup` × 14** *(Mar 29)* — Large-scale code cleanup sweep: dead code, unused imports, commented-out blocks, and old debug statements removed across the codebase.

**`bg change` / `Incorrect deletion reverted`** *(Apr 9)* — Background colour adjusted. An accidental deletion of a needed file was reverted.

**`wrapper fix for mobile` / `visual update hero` / `height change hero page builder`** *(Apr 2)* — Mobile layout wrapper fixed for the page builder hero block. Hero height and visual appearance tuned.

**`translation fix` × 2 / `fix`** *(Apr 12)* — Translation string fixes; minor route/view bug fixed.

---

## Phase 6 — Language, Mobile & Enrolled UX (Apr 20 – May 15, 2026)

**`language update: AZ removed`** *(Apr 20)* — Azerbaijani was disabled as a supported language. Translation quality via LibreTranslate was insufficient for production use; the locale is preserved in constants for future re-enabling.

**`visual update home + about company` / `translations + constants`** *(Apr 22)* — Home page and About Company page visual updates. Language constants updated; new translatable strings compiled and merged.

**`visual update 1` / `logo spacing`** *(Apr 23)* — Logo spacing corrected (too close to the navbar edge). General visual refresh on home and about pages.

**`Google drive permission and URI fix`** *(Apr 23)* — A Google Drive OAuth redirect URI mismatch and permission scope error were causing auth failures in production; both fixed.

**`translation update + video update`** *(Apr 27)* — Translation strings updated. Video rendering in page builder blocks improved.

**`interface course content enrolled`** *(Apr 28)* — The enrolled student's view of course contents was redesigned for better usability: cleaner layout, clearer item states, improved folder hierarchy display.

**`privacy policy and terms of use Updated`** *(Apr 30)* — Legal pages content revised to reflect current practices.

**`FIX translations az to work in legal pages`** *(Apr 30)* — Although `az` is globally disabled, the legal pages were crashing when the locale was explicitly set to `az` (e.g., via a direct URL). Now falls back gracefully to the default language.

**`login translations fix` / `language switching fix all`** *(May 5)* — Login-page translation strings corrected. Language-switching flow fixed across all pages (previously some pages lost the selected language on navigation).

**`optimization_courses1` / `optimization fix v.1.2` / `optimization fix 1.3`** *(May 5)* — Three rounds of query-level performance optimisations for the course pages: N+1 query patterns eliminated, eager loading added where appropriate.

**`fixed enrolled course page`** *(May 12)* — The enrolled course view was broken after the optimisation changes; repaired.

**`whatsapp icon added`** *(May 15)* — WhatsApp contact icon added to the site.

**`login + language dropdown in course enrolled view fix`** *(May 15)* — Login redirect from inside a course was broken. Language-switcher dropdown inside the enrolled view was not retaining the selected language; fixed.

---

## Phase 7 — Analytics, About Company & Assignment Improvements (May 17–27, 2026)

### Analytics (May 17–19)

**`Fix: analytics button and chart rendering`** *(May 17)* — Analytics chart rendering was broken on first load; the trigger button did not initialise correctly. Fixed before v.1 was merged.

**`analytics v.1`** *(May 18)* — First version of course analytics released: an admin panel view showing enrollment counts per course, activity over time, and progress metrics. Charts rendered via a JS charting library.

**`fix routes` / `migration fix`** *(May 18)* — Route registration conflict caused by the analytics blueprint was fixed. An Alembic migration needed by the analytics tables was repaired.

**`optimizations fix 2.0`** *(May 18)* — Second-pass performance optimisations: analytics queries were slow on large datasets; addressed with pagination and aggregate queries.

**`Course analytics search-bar addition`** *(May 19)* — A search/filter bar was added to the analytics view so admins can quickly find specific courses in a long list.

**`color list for analytics update`** *(May 19)* — The analytics chart color palette was updated for better visual distinction between courses.

**`language fix` / `retranslate` × 3 / `cleanup` × 2**  *(May 19)* — Language-detection bug fixed. Translation pipeline rerun three times to catch strings missed by the analytics feature. Dead code cleaned up.

### About Company & Services (May 24)

**`about company gallery 2`** *(May 24)* — A second gallery section was added to the About Company page, allowing separate galleries for different content areas (e.g., team vs. facilities).

**`services about company fix` / `fix 1 visibility size our services`** *(May 24)* — The "Our Services" section on the About Company page had layout and visibility issues; fixed.

**`buttons gallery 1+2 fix`** *(May 24)* — Navigation arrow buttons for both gallery sections were broken after adding gallery 2; fixed.

**`content translation moxo`** *(May 24)* — The `content_translation` table (used by the page builder) was corrected and extended for new block types.

**`unused feature removed`** *(May 24)* — A half-built feature was removed from the codebase.

### File Access & Course Content Fixes (May 25–26)

**`file viewer limits applied`** *(May 25)* — File viewing is now restricted based on enrollment status and role; unenrolled users cannot access course file previews.

**`footer privacy policy link added`** *(May 25)* — The site footer now includes a direct link to the Privacy Policy page.

**`translation of legal docs to azeri fixed` / `po file fixed`** *(May 25)* — Azerbaijani translations for legal documents were corrected in the `.po` files and recompiled.

**`Fix: Remove broken duplicate gallery_2 migration` / `Rechain gallery_2 migration` / `Repair broken auto-generated migrations`** *(May 25)* — A third round of Alembic migration chain repairs: adding the About Company gallery 2 columns caused a cycle conflict; three commits linearised the chain.

**`course page enrolled assignments fixes`** *(May 25)* — Several bugs in the enrolled view's assignments panel were fixed: submission state display, grade visibility, and deadline rendering.

**`deleting folders in courses fix`** *(May 25)* — Recursive folder deletion in course contents was not cascading correctly; fixed to properly remove all child items.

**`bulk move fix`** *(May 26)* — Bulk-move of course content items was broken after the folder deletion fix; repaired.

**`decline submissions function added`** *(May 26)* — Admins and instructors can now formally decline a student's assignment submission with a reason, not just approve it.

**`newline in course assignments' description implemented`** *(May 26)* — Assignment descriptions now preserve line breaks when displayed (previously `\n` was rendered as a space).

**`fix form_data about company` / `translation fix`** *(May 26)* — About Company form data was not being saved correctly in some fields; fixed. Translation string fix.

**`limitation page — ADMIN page for limiting users' access to pages`** *(May 27)* — A new admin panel section was added allowing admins to restrict which application pages are accessible to specific users or user groups. Pages can be toggled on/off per user.

---

## Phase 8 — UI Polish, Contact & Icons (Jun 9–11, 2026)

### Enrolled View & Translation Fixes (Jun 9)

**`update of course enrolled`** *(Jun 9)* — Comprehensive visual and UX update to the enrolled course page: spacing, component layout, and state display all improved.

**`indent fix` / `margin fix` × 3** *(Jun 9)* — Text indentation and vertical margins in the enrolled course view were inconsistent; fixed across four commits.

**`translations fix` × 2** *(Jun 9)* — Translation string rendering fixed for strings that were appearing untranslated in the enrolled view.

### Contact, WhatsApp & Hero (Jun 10)

**`contact us`** *(Jun 10)* — A full Contact Us page was added with a form, company contact details, and a map embed. Also added to the site navigation.

**`contact us language update`** *(Jun 10)* — Contact Us page strings were wrapped in `_()` and made translatable in Russian and English.

**`whatsapp button` / `whatsapp button courses tweak fix`** *(Jun 10)* — A floating WhatsApp contact button was added site-wide and on course detail pages, linking to the company's WhatsApp number.

**`course hero fix`** *(Jun 10)* — The hero banner on course description pages had broken layout at certain viewport widths; fixed.

**`tweaks for tags courses`** *(Jun 10)* — Course tag pills on the course listing and description pages were restyled.

**`carousel rework`** *(Jun 10)* — The home page image carousel was significantly reworked: new transition behaviour, correct autoplay timing, arrow controls repositioned, and mobile touch support improved.

**`height carousel tweaks`** *(Jun 10)* — Carousel height made consistent across breakpoints.

### Visual Polish (Jun 10)

**`button size + hero bg fix`** *(Jun 10)* — Button sizing was inconsistent across the site; standardised. Hero section background colour fixed.

**`visual update` / `opacity bg tweak`** *(Jun 10)* — General visual polish pass. Background overlay opacity adjusted for better text readability over images.

**`remove content translation from description of courses`** *(Jun 10)* — Course descriptions were removed from the `content_translation` live-translation system; they are authored directly in the language of their audience and don't need runtime translation.

**`zoom reduced page builder`** *(Jun 10)* — The page builder admin canvas zoom level was reduced so the full block layout is visible on normal screens without scrolling.

**`mobile fix` / `mobile builder fix`** *(Jun 10)* — Mobile layout fixes on general pages (overflow and stacking issues). Page builder block editor also fixed on mobile.

### Icons (Jun 10–11)

**`icons added` / `last ui icons` / `file type icons` / `removed system icons`** *(Jun 10)* — A comprehensive icon pass across the entire application: file-type icons (PDF, video, image, etc.) introduced in course content views; system left/right navigation arrows replaced with custom icons.

**`whatsapp icon change`** *(Jun 10)* — WhatsApp button icon colour scheme adjusted.

**`useless icon removed + icons added`** *(Jun 11)* — Further icon cleanup: a redundant icon removed, new icons added where actions lacked visual indicators.

**`rework of enrolled icon`** *(Jun 11)* — The enrolled-status indicator icon on course cards was redesigned to be clearer.

### Course & Site Improvements (Jun 11)

**`courses length of items logic reworked`** *(Jun 11)* — The logic for counting and displaying item totals (files, folders) in course listings was reworked for accuracy; previously showed incorrect counts in nested structures.

**`fonts (montserrat)`** *(Jun 11)* — Montserrat was adopted as the primary body font across the site (noted as subject to future change).

**`visual fixes`** *(Jun 11)* — General visual cleanup pass addressing leftover spacing and alignment inconsistencies.

**`wheel gallery 1 about us fix`** *(Jun 11)* — The circular/wheel-style gallery component on the About Us section was broken after the icon changes; fixed.

**`limits added + po translation fix`** *(Jun 11)* — File-access and enrollment limits applied to additional pages. `.po` translation file corrected for strings that had incorrect entries.

**`visual updates` (production deployment series)** *(Jun 11)* — Several production deployments pushed to stabilise the site after the Jun 10–11 changes.

---

## Phase 9 — Rebranding, Certificates & Admin Permissions (Jun 12–25, 2026)

### Rebranding (Jun 12–15)

**`rebranding` × 6 commits / `rebranding for oauth`** *(Jun 12)* — Full visual rebranding pass: logo upload flow revised, OAuth consent screen updated to match new branding, multiple rounds of fixes (`rebranding fix 2`, `fix 3`, `5`, `5.1`, `6`).

**`oauth verification template switch`** *(Jun 14)* — OAuth verification template was switched to the new branded design.

**`visual update` / `visual changes + navbar at the bottom visibility`** *(Jun 14–15)* — General visual updates; navbar bottom-of-page visibility improved.

**`improved loading of bg` / `visual change to bg Item`** *(Jun 15–16)* — Background image loading optimised; About page item background restyled.

### Course Content Improvements (Jun 14–19)

**`imported material delete in drive fixed`** *(Jun 14)* — Deleting Google Drive-imported course material from within the app now correctly removes it.

**`icon type fix` × 2** *(Jun 15)* — File-type icons in course content were broken for certain MIME types; fixed in two passes.

**`mobile implementation for course content`** *(Jun 15)* — Course content panel now has a proper mobile layout.

**`recursive folder inside folder fix`** *(Jun 19)* — Nested folder structures inside course content were not rendering correctly; fixed.

**`google drive item id hidden`** *(Jun 19)* — Google Drive internal item IDs are no longer exposed in the UI.

**`bulk actions in course enrolled teacher/admin`** *(Jun 19)* — Teachers and admins can now bulk-select and act on course content items from the enrolled view.

**`description removed from course-enrolled`** *(Jun 17)* — Course description was removed from the enrolled view to reduce visual clutter.

**`announcements`** *(Jun 17)* — Course announcements feature added: teachers can post announcements to enrolled students.

**`edit resource item`** *(Jun 16)* — Resource items in the resource library can now be edited after creation.

**`item 2nd image for gallery in about company`** *(Jun 16)* — A second image slot was added to About Company gallery items.

### User & Auth (Jun 19)

**`password change by user capability`** *(Jun 19)* — Users can now change their own password from the profile page.

**`translation quality improved via reducing queries for already translated content`** *(Jun 19)* — Translation lookups were optimised to skip re-querying content that has already been translated.

### Admin Permission Tiers (Jun 21–23)

**`permissions for admins added`** *(Jun 23)* — A three-tier permission system was introduced: **full admin** (unrestricted), **sub-admin** (restricted to specific permission keys), and **regular user**. Each admin panel view is gated by a permission key via `user.has_perm('key')`. Only full admins can assign or revoke sub-admin permissions at `/admin/user_permissions/`.

**`course analytics fix`** *(Jun 23)* — Analytics view broke after the permission gating was applied; fixed to respect the new access model.

**`course bug fix`** *(Jun 23)* — A bug introduced in the permission refactor caused a crash on course pages; patched.

### Certificate System (Jun 19–25)

**`certificate registry - demo`** *(Jun 19)* — Initial certificate registry UI: a verifiable certificate index page per course was scaffolded.

**`tuning.json reworked + translations + cache certificates`** *(Jun 21)* — Certificate generation tuning (positioning, font sizes, colors) moved to a per-course JSON config (`tuning.json`). Generated certificates are now cached as PNG/PDF on first download.

**`certificate template volume mount + persistent tuning.json`** *(Jun 21)* — Certificate template images and tuning config are stored in a Docker volume-mounted directory so they persist across deployments.

**`serve certificate template thumbnails from volume mount`** *(Jun 21)* — Template preview thumbnails in the admin are served from the volume-mounted directory.

**`simplify certificate storage — templates in static/, data/ per-environment`** *(Jun 21)* — Font files live in `static/certificates/fonts/`; templates and generated files live in the volume-mounted `data/` directory, separate per environment.

**`keep certificate templates out of public git repo`** *(Jun 21)* — Template PNG files are excluded from git; they are uploaded to each server manually via SCP.

**`docs: certificate template upload instructions`** / **`docs: clarify certificate template SCP uses SSH_HOST secret`** *(Jun 21)* — Deployment documentation updated with SCP upload steps.

**`certificates visuals and certificate board reworked`** *(Jun 24)* — Certificate card design, the admin certificate management board, and the per-course certificate tuning panel were all reworked. Configurable issue date (current date or custom date picker) added when issuing certificates.

**`updated translations`** *(Jun 25)* — Translation strings updated and compiled after the certificate and city features added new UI text.

### City Autocomplete & User Filters (Jun 24–25)

**World cities autocomplete** *(Jun 24)* — A 32,000-city dataset (English + Russian names, sourced from GeoNames) was added as `static/cities.json`. A lazy-loading `CityAutocomplete` JS module provides typeahead suggestions on city inputs across the profile page and admin user create/edit forms.

**Admin user filters** *(Jun 24)* — The admin user list gained filter controls: filter by city (text match) and filter by registration date (before / after). The `city` and `created_at` columns were added to the `user` table via Alembic migrations.

**Certificate wall page builder block** *(Jun 24)* — A new "Certificate Wall" block type was added to the course page builder. It renders a responsive grid of graduate cards (name, city, issue date) pulled live from issued certificates. Cards initially show 3 entries; a "Show more" button reveals 5 additional cards per click.

**Certificate fonts** *(Jun 25)* — Certificate typography updated: student name in **Great Vibes** (unchanged), course name in **Cormorant Garamond SemiBold** (fallback: Cinzel), date and certificate ID in **Libre Baskerville** (fallback: Cormorant Garamond Regular).

**Russian translations for city UI** *(Jun 25)* — `City` → `Город`, `Start typing your city…` → `Начните вводить город…` added to the Russian `.po` file and compiled.

---

## Ongoing / Cross-Cutting

- **Translation pipeline** — LibreTranslate-backed gettext translations (`az` disabled, `ru`/`en` active) are continuously maintained. The two-table system (`translation` for gettext strings, `content_translation` for page builder content) evolved across many commits. Bad LibreTranslate auto-translations in English were mass-cleared (Jun 21).
- **Migration fixes** — Alembic migration chains broke repeatedly as features were developed in parallel; dedicated fix sessions occurred in Jan, Mar, May, and Jun 2026. Most recently: `city` and `created_at` columns added to `user` table (Jun 2026).
- **Cleanup sweeps** — Rapid feature development followed by cleanup/debug-removal commits is a recurring pattern throughout the project history.
- **Google Drive** — The Drive integration evolved: basic service-account → full OAuth2 → import folders → scope reduction → URI fixes → imported-item deletion fix (Jun 2026).
- **Deployment** — Stack: simple VPS systemd → nginx → Caddy → Docker Compose. CI/CD: GitHub Actions builds Docker image → pushes to GHCR → SSH-deploys to staging (`staging` branch) and production (`main` branch). Certificates and templates live in volume-mounted directories not committed to git.
- **Admin permission model** — As of Jun 2026: three tiers (full admin / sub-admin / user). All admin views gated via `user.has_perm('key')`. Sub-admin permission assignment restricted to full admins only.
