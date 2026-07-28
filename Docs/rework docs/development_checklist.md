# LMS Rework — Development Checklist

Tracks implementation progress phase by phase, per the approved local-first roadmap. I'll
keep this checked off as work lands — treat it as the source of truth for "what's actually
done" alongside `git log`. See `setup_checklist.md` for the accounts/keys you need to
provide alongside this.

---

## Phase 0 — Security hardening

- [x] Global CSRF protection (`CSRFProtect`), all forms + `fetch()` calls covered
- [x] Upload limits (`MAX_CONTENT_LENGTH`) + real content/MIME sniffing (not just extension)
- [ ] Rate limiting moved from in-memory to Redis (depends on Phase 3's Redis service —
  tracked here, executed there)
- [x] Structured logging — replaced all 164 `print()` calls with leveled, JSON-formatted
  rotating file logging (`lms/logging_config.py`) + console output
- [x] Password hashing confirmed strong (Werkzeug's default `scrypt`, no change needed) +
  strength rules (`lms/password_policy.py`) applied to change-password and admin user creation
- [x] Self-service `/signup` route (didn't exist before) + email verification
  (`lms/email_service.py`, dev-mode logs the link) gating login until verified; Google
  OAuth and admin-created accounts are auto-verified since those are already trusted
- [x] GDPR basics — cookie consent banner (`components/cookie_consent.html`, all public
  pages) + self-service data export (`/profile/export`, JSON download) and account
  deletion (`/profile/delete`, password-confirmed). Deletion anonymizes rather than hard-
  deletes the row, since several tables have NOT NULL foreign keys to the user (forum
  messages, submissions, certificates, etc.) — this avoids orphaning that content.
- [ ] Show/hide password toggle (eye icon) on password input fields (login, signup, change
  password, admin user creation, etc.) — filed here from backlog, adjacent to the existing
  password-policy/strength-rules work above

**Phase 0 is complete** except the show/hide toggle just filed above. Rate limiting → Redis migration is the only other item still pending,
and it's blocked on Phase 3's Redis service by design.

## Interim — Drive writer stopgap (pulled forward from Phase 4)

- [x] `get_drive_writer_user`/`set_drive_writer`/`clear_drive_writer` in
  `google_drive_service.py`, wired into `authenticate()`'s default (no-explicit-user) path
- [x] Full-admin-only **Admin → Drive Writer** view/route (`lms/admin/__init__.py`,
  `templates/admin/drive_writer.html`) to designate/clear the writer

Built ahead of schedule to avoid needing a dummy "worker" Google account (ToS concern) while
testing centralized-ownership Drive writes locally. This is explicitly **not** the real
Phase 4 worker account — no new token storage, it just points uploads at an admin's existing
linked account via `AppSetting`. Real Phase 4 work (dedicated account, Workspace migration)
is unaffected and still pending.

## Phase 1 — Course: content/UX, access & enrollment model, quizzes

- [x] Fix navbar/footer missing in enrolled course view — investigated thoroughly (route,
  template inheritance, sandboxed render, live curl), couldn't reproduce against current
  code. Dropped per user — will revisit with specific repro steps if it recurs.
- [x] Fix broken login redirects from inside a course — app never captured/honored a `next`
  param at all (client-side attempt existed but didn't run on the course page due to a
  missing `{{ super() }}` in its `scripts` block, also fixed). Replaced with a proper
  server-side `next` param, open-redirect-guarded (`lms/routes/auth.py`, `lms/__init__.py`).
  Verified live incl. malicious external `next` correctly falling back to home.
- [x] Fix language selection not persisting across pages — two causes: a duplicate `/api/user`
  route silently shadowed the one that returned `preferred_language` (merged, dead code
  removed); and `docker-compose.yml`'s `app-dev` hardcoded `FLASK_ENV: production`
  (`SESSION_COOKIE_SECURE=True`) while also exposing port 8000 directly over plain HTTP,
  silently dropping the session cookie entirely. Fixed by removing the direct port mapping
  (Caddy's HTTPS route is unaffected, uses the internal Docker network).
- [ ] Certificates restyle (design-system pass, no functional change) — deferred, no design
  direction available yet; not blocking anything else in this phase.
- [x] `Enrollment` model replacing plain `user_courses` M2M table (`lms/models/__init__.py`) —
  `joined_via`/`enrolled_at`/`paid` stub columns, `association_proxy` keeps `user.courses`/
  `course.users` working as read-only convenience accessors for all 13 existing call sites.
  Migration backfills existing `user_courses` rows as `direct_add`. Found and worked around a
  real `association_proxy` bulk-replace bug (reassigning an overlapping list tries to
  re-insert before deleting, hits the unique constraint) — Flask-Admin's `UserView` now
  manages `Enrollment` rows explicitly via `course_ids` instead of relying on it.
- [x] `PromoCode` model + redemption route (`lms/models/__init__.py`, `lms/routes/__init__.py`)
  — `max_uses`/`expires_at`/`uses_count`, `is_valid` property.
- [x] Open-source/public flag on `Course` (`is_public`) and `ForumChannel` (`is_public`);
  `Resource`/`PDFDocument`/`CourseContent`'s existing `allow_others_to_view` reused as-is,
  no duplicate flag added.
- [x] Join paths — all 4 built and verified live end-to-end: promo code (typed, `/join`),
  direct link (`/join/<code>`, confirmation page on GET so link-prefetch/scanners can't
  auto-join someone), direct-add by teacher/admin (new "Access" tab on
  `CourseManagementView`: add/remove students, generate/revoke promo codes, public toggle),
  instant-join on public courses (button on the course page when `course.is_public`).
  `max_uses` enforcement verified (3rd redemption of a `max_uses=1` code correctly rejected).
- [x] Quiz models (`Quiz`, `QuizQuestion`, `QuizAttempt`/`QuizAnswer`) — MCQ, true/false, short-answer.
  Admin creation is a plain Flask-Admin form with inline questions (JSON textareas for
  options/correct_answer) — a proper authoring UI is Phase 9 scope per the plan, not rebuilt here.
- [x] Quiz attempt limits, timers, auto-grading — `max_attempts` enforced at attempt-start;
  client-side countdown auto-submits at the deadline (server doesn't reject slightly-late
  submissions, to avoid punishing normal network latency); `QuizAttempt.grade()` auto-grades
  all three question types and sets `passed` against `passing_score`.
- [x] `CourseContentFolder.locked_until_quiz_id` so quizzes share the existing assignment-gating
  mechanism — `course_page_enrolled`'s `is_locked` check now covers both assignment- and
  quiz-gated folders.

All verified live end-to-end via `just dev`: admin-created quiz with an MCQ + true/false
question, enrolled student taking it (correct-answer scoring, pass/fail, folder unlock for a
passer vs. still-locked for a non-passer).

- [ ] Merge the "Quizzes" tab on the course page into the "Assignments" tab instead of a
  separate tab (`lms/templates/course_page_enrolled.html`) — filed here from backlog
- [ ] Short-answer quiz questions: replace the current case-insensitive exact-string
  auto-grading (`_check_quiz_answer` in `lms/models/__init__.py`) with **manual teacher
  review**, so answers that are correct but not a literal string match aren't marked wrong —
  filed here from backlog. Note: the backlog item also suggested AI-assisted grading as an
  alternative, but this plan's own "Out of scope for this pass" section explicitly excludes
  AI grading — scoping this to manual review only unless you want to revisit that exclusion.

**Phase 1 is otherwise complete**, pending the two items just filed above.

## Phase 2 — Home, Resources, Forum

- [x] Home page (replaces standalone `index.html` for `/`) — "My Courses", promo-code join
  entry (posts straight to `main.join_with_code`), recent activity (`ContentView`-driven,
  last 5 distinct course-content items viewed), and a "Discover Courses" section of public
  courses not yet joined. Verified live for both authenticated and anonymous views.
- [x] Resources page — redesigned around the plan's actual data (the standalone `Resource`
  model was **deprecated and removed entirely** per an explicit decision this phase, since it
  was never course-scoped and duplicated what `CourseContent` already does). Two sections:
  content from the user's enrolled courses ranked by cross-user view-count popularity
  (`ContentView` aggregation), and locked "teaser" cards (title + course name, no access) for
  content in public courses not yet joined. Verified live with real popularity ranking.
- [x] Forum page — kept `ForumChannel`/`ForumMessage` global (not course-scoped) per an
  explicit decision this phase; `is_public` now gates which channels guests can discover in
  the channel list (layered on top of the existing `requires_login`/`admin_only` content
  gating, which is unchanged). New `forum.html` + JS adapted from the old SPA's forum
  section, fixing a stored-XSS bug found in the original (`innerHTML` string interpolation of
  user-supplied message/username text) by switching to `textContent`-based rendering —
  verified live with an XSS payload that renders as literal text instead of executing.
- [x] Removed `/about` route and the empty `static/gallery/` dir. `/courses` and `/site`
  (legacy SPA aliases) now redirect to Home instead of rendering the old SPA. `index.html`
  itself is **not yet deleted** — `/moxo-test` still renders it, and MoxoTest's full removal
  is already Phase 9 scope; ripping out the now-dead home/courses/forum/resources/about
  `<section>`s early risked breaking the shared JS/CSS the moxo-test page still depends on
  for limited benefit. `components/navbar.html` and `base.html`'s active-nav-highlighting JS
  were both updated from hash-based SPA routing to real pathname-based routing/highlighting.

**Phase 2 is complete**, with two scope decisions made along the way (documented above):
the standalone Resource model is gone (not migrated to be course-scoped), and Forum stayed
global rather than becoming course-scoped like Resources did.

## Phase 3 — Shared background job queue

- [x] Added `redis-dev` to `docker-compose.yml` (dev profile), port configurable via
  `REDIS_PORT` (defaulted to `6380` locally — `6379` was already taken by an unrelated
  project's Redis on this machine; `.env.example` keeps the standard `6379`).
- [x] Replaced `lms/job_manager.py`'s in-process thread-poll worker with RQ backed by Redis
  (`lms/queue.py`). Job status/progress is still tracked in the existing `BackgroundJob` DB
  table, so the admin panel's polling API and `to_dict()` contract are unchanged — only how
  a job gets *picked up* changed. New `lms/worker.py` is the actual worker entrypoint: it
  creates the Flask app and pushes its context **once** for the worker process's whole
  lifetime (not per job), then runs `rq worker` programmatically — needed because job
  functions touch the DB and app config. Runs via `just worker` (local) or the new
  `worker-dev` Docker Compose service.
- [x] Migrated the existing `translate_content` job onto the new queue — same handler logic,
  now dispatched through `job_queue.enqueue(...)` instead of a DB-polling loop.
- [x] Rate limiter's `storage_uri` now reads `REDIS_URL` (`lms/extensions.py`), falling back
  to `memory://` if unset, so one-off local scripts without Redis don't break.

Verified live end-to-end: queued a real translation job from the Flask app process, watched
a **separate** `just worker` process pick it up off Redis and complete it, confirmed via the
admin panel's job-status polling endpoint. Separately confirmed the rate limiter is genuinely
Redis-backed (not just configured) — a `LIMITS:LIMITER/...` key appeared in Redis after
hitting a limited endpoint, and the 6th request within a "5 per 30 seconds" window correctly
got a `429` instead of reaching the view.

**Phase 3 is complete.**

## Phase 4 — Google Drive worker migration

- [x] Single worker-account credential mechanism built: `WorkerCredentials` in
  `google_drive_service.py` duck-types the same three attributes `authenticate()`/
  `refresh_credentials()` already read and write (`google_access_token`/
  `google_refresh_token`/`google_token_expiry`), but persists them to `AppSetting` instead
  of a `User` row — so both functions work against it completely unmodified.
- [x] Worker refresh token stored server-side via `AppSetting` (not on `User`) — done, see
  above. Keys: `worker_google_access_token`/`worker_google_refresh_token`/
  `worker_google_token_expiry`.
- [x] `authenticate()`'s default resolution order is now: **worker account** (this phase) →
  Drive Writer stopgap (Phase 1) → `current_user`. All existing `drive_file_id`/
  `drive_view_link` write paths (`CourseContent`, `CourseAssignmentSubmission` — the
  standalone `Resource`/`PDFDocument` write paths no longer apply since `Resource` was
  removed in Phase 2) already call `authenticate()` with no explicit user, so they
  automatically start using the worker once one is connected — no call-site changes needed.
- [x] New admin surface at `Admin → Drive Worker` (`/admin/drive_worker/`, full admins only):
  shows connection status (including a live account-info check against Google, not just
  "a token is stored"), a "Connect Worker Account" button (OAuth flow reusing the existing
  Google client, just storing the result differently), and disconnect.
- [x] Along the way, fixed a real bug in `get_linked_google_account()`: its 401/expired-token
  cleanup path assumed a real `User` row (`db.session.query(User).filter_by(id=user.id)...`),
  which crashed (`AttributeError`) against the new duck-typed `WorkerCredentials`. Switched
  to direct attribute assignment (matching the pattern `authenticate()` already used) — also
  a minor correctness improvement for the `User` path, since it keeps the in-memory object
  in sync instead of a bulk `UPDATE` that bypassed it.
- [x] Fixed two OAuth scope bugs found during real-world worker setup: (1) `connect_worker()`
  initially requested only `drive`, omitting `openid email profile` — `get_linked_google_account()`
  calls Google's userinfo endpoint to show which account is connected, which 401s without
  those scopes; the self-healing logic then (correctly, per its own logic) treated the 401 as
  an invalid token and auto-cleared it, surfacing as "Worker credentials are stored but
  invalid." (2) Both `connect()` and `connect_worker()` requested the full
  `https://www.googleapis.com/auth/drive` scope, broader than what `SCOPES` in
  `google_drive_service.py` actually declares/uses (`drive.file`) — tightened both to
  `drive.file` for consistency and least-privilege.

Verified live end-to-end with a **real** worker Google account (not a fake token): connected
via `Admin → Drive Worker`, confirmed valid account info displayed (no self-healing
disconnect), priority resolution over the Drive Writer stopgap holds.

**Phase 4 is complete**, including the manual account setup.

## Phase 5 — Translation pipeline rework

- [x] Swapped `core_translator.py`'s engine from LibreTranslate to DeepL — same
  `translate_text`/`translate_batch` signatures (now `deepl_api_key=` instead of
  `libretranslate_url=`), same `{LMS}`/`{MOXO}` protect/restore-terms mechanism, source
  language still left to the engine's auto-detection. DeepL requires a regional variant for
  English as a *target* (plain `EN` is rejected) — defaulted to `EN-US`. Implemented via
  plain `requests` calls (no new `deepl` SDK dependency) since the API surface used is small.
  `translation_service.py` and `scripts/translations/auto_translate_po.py` updated to match;
  `Translation.translation_service` now records `'deepl'`.
- [x] Removed LibreTranslate entirely — `docker-compose.yml`'s `libretranslate` service (was
  shared across all 3 profiles), the `just libre`/`libre-ready` recipes, `LIBRETRANSLATE_URL`
  everywhere, and the `./data/libretranslate` volume dir. Replaced with `DEEPL_API_KEY` in
  `.env`/`.env.example`. `just translate-all`/`translate-reset`/`translate-fix-placeholders`
  no longer need a `libre-ready` dependency since DeepL is a cloud API, not self-hosted.
- [x] Found and fixed a real gap while removing LibreTranslate: Phase 3 only ever added
  Redis + a worker service (`worker-dev`) for the **dev** Docker Compose profile —
  `production`/`staging` had no Redis, no worker, at all. This was latent as long as
  translation ran synchronously inline, but the next item below moves it onto the job
  queue, which would have silently stopped working in deployed environments. Added
  `redis-production`/`redis-staging` and `worker-production`/`worker-staging` mirroring the
  dev pattern, wired `REDIS_URL` into `app-production`/`app-staging`.
- [x] Moved the translation trigger off "admin-click only" onto the Phase 3 RQ queue, as
  both an interval and a threshold trigger:
  - **Threshold**: `CourseView.create_view`/`edit_view` (admin panel) and the self-service
    `/course/create` route now queue a new `translate_course` job (`{'course_id': ...}`)
    instead of calling `auto_translate_course()` synchronously inline and blocking the
    HTTP request on an external API call. Fixes a real gap along the way — self-service
    course creation (`lms/routes/__init__.py`) never triggered translation at all before.
  - **Interval**: added `run_scheduled_translation_sweep()` — a full-catalog
    `translate_content` job that re-enqueues itself every 24h via RQ's built-in scheduler
    (`Queue.enqueue_in(..., job_id=...)`), bootstrapped once per worker-process lifetime by
    `ensure_translation_sweep_scheduled()` (idempotent — checks `ScheduledJobRegistry`
    before enqueuing, so restarting the worker in dev doesn't spawn duplicate chains).
    `lms/worker.py` now runs `Worker.work(with_scheduler=True)` — no separate
    `rq-scheduler` package or process needed, RQ 2.10 has this built in.
  - The admin panel's manual "Translate" button (`TranslateContentView`) is unchanged and
    still queues an on-demand `translate_content` job — kept for on-demand bulk runs.
  - Added `BackgroundJob.data` (JSON) column + migration — `JobManager.queue_job()`'s
    `job_data` parameter existed before but was silently discarded (never persisted or
    passed through); needed it to carry `course_id` into the new per-course job type.
- [x] Lightweight spot-check pass — `content_translator.spot_check_translations()` samples a
  random subset of `ContentTranslation` rows after each `translate_content` run and flags
  (log + job result) any that are empty or still contain a leaked `{LMS}`/`{MOXO}`
  placeholder. Not a quality judge (no reference text to compare against) — just catches the
  failure modes an API error or a term-protection bug actually produce. Merged into the job's
  `result` dict, visible via the existing job-status polling endpoint.
- [x] Found and fixed two incidental bugs while in this code:
  - `content_translator.py`'s `TARGET_LANGUAGES` was hardcoded to `['az', 'ru']`, ignoring
    `constants.SUPPORTED_LANGUAGES` (`['en', 'ru']`, `az` deliberately disabled) — every course
    translation was silently attempting (and failing) an Azerbaijani translation. Now derived
    from `SUPPORTED_LANGUAGES` directly so a disabled language can't come back via this path.
  - `get_translated_string_array()` (`content_translator.py`) was missing its `return`
    statement entirely — always returned `None`, silently nulling out any `tags` array
    translation that went through it.

- [x] Verified fully live end-to-end with a real `DEEPL_API_KEY`: the bootstrapped recurring
  sweep translated a real course title to Russian on worker startup (confirmed via direct DB
  query, and via DeepL's own `/v2/usage` endpoint showing real character consumption); the
  `.po` pipeline (`just translate-all` steps run manually) translated 6 new UI strings,
  placeholders (`%(title)s`) preserved correctly.
- [x] Removed Azerbaijani (`az`) support entirely, not just "disabled" — per explicit
  instruction, since it was already inert (DeepL doesn't support it) and half-removed
  (constants had it commented out but the locale selector, `set_language` route, admin
  translation-cleanup filter, and both legal-page templates still referenced it as a live
  option). Gone from: `constants.py`, `lms/__init__.py`'s `get_locale()`, `routes/__init__.py`'s
  `set_language()` (all three now read `constants.SUPPORTED_LANGUAGES` instead of a
  hardcoded list), `admin/__init__.py`'s `delete_translations`, `lms/translations/az/`
  (deleted), and the full hand-translated Azerbaijani sections of `privacyPolicy.html` /
  `terms.html` (language switcher link, heading, and legal-text block). No leftover `az`
  rows existed in the DB to purge.
- [x] Found and cleaned up incidental cruft while verifying: a stray untracked `lms/venv/`
  directory (Windows-layout venv, gitignored, not the real `uv`-managed `.venv`) was
  polluting `pybabel extract` with strings from `pip`'s own source — deleted. A stale
  `routes/api.py` error message still told users to "Start LibreTranslate with: just libre"
  (both long gone) — now points at checking `DEEPL_API_KEY`. A leftover test-account
  password (`password: TempTest#Pass1`) sitting at the top of `setup_checklist.md` outside
  any section was removed.

**Phase 5 is complete and verified live**, including the manual `DEEPL_API_KEY` setup.

## Phase 6 — AI personal guide + subtitles

- [ ] Enable `pgvector` extension (migration) + embedding-storage model
- [ ] Chunk + embed course documents/transcripts
- [ ] RAG answer pipeline with citations back to source file
- [ ] Auto-transcribe uploaded lecture videos (Gemini audio input) → feeds RAG index too

*(Requires the Gemini API key in `setup_checklist.md` Phase 6 first.)*

## Phase 7 — AI audio overview

- [ ] Single-narrator spoken summary (summarization pipeline + TTS step)
- [ ] Two-host conversational format (only after single-narrator works)

*(Requires the ElevenLabs API key in `setup_checklist.md` Phase 7 first.)*

## Phase 8 — Office file preview

- [ ] Word/Excel → PDF conversion on upload for view-only preview

## Phase 9 — Admin panel rework

- [ ] Remove MoxoTest (view, permission, route, model)
- [ ] Rework course management (promo codes, open-source toggles)
- [ ] Quiz authoring UI
- [ ] Forum/resource moderation rework
- [ ] Translation review UI reflecting DeepL engine
- [ ] Update `ADMIN_PERMISSIONS` (drop `moxo_test_management`, add quiz/promo-code keys)

## Phase 10 — Real email delivery

Currently a placeholder: `lms/email_service.py`'s `send_verification_email()` just logs the
verification link (`[dev-mode email] ...`) instead of sending it — a signup gets told
"check your email" but nothing arrives. Fine for local dev/testing, but blocks real users
from ever completing signup once this is live, and needs a provider decision from
`setup_checklist.md` (SMTP, SendGrid, Mailgun, Postmark, etc.) first.

- [ ] Pick and configure an outbound email provider
- [ ] Swap `send_verification_email()`'s body for the real provider call — call sites
  (`routes/auth.py`) don't need to change, by design
- [ ] Verify a real signup end-to-end: account created → real email received → link works

*(Scheduled after Phases 6-9 per explicit instruction — lowest priority in the roadmap.)*

---

## Backlog — noted for later (not scheduled to a specific phase yet)

*(empty — everything previously here has been filed into Phase 0/1 above or into "Done" below)*

## Done (pulled forward from backlog)

- [x] Self-service course creation — any authenticated user can create their own course via
  `/course/create` and gets full in-page management rights over just that course. Added
  `Course.created_by` (nullable — NULL for existing/admin-created courses). Deliberately
  scoped to `course_page_enrolled` only — the separate Blackboard-style editor at
  `/course/<slug>/edit` stays **admin-only** (it already excluded teachers too, not just
  non-owners), left untouched.
- [x] Removed the global `User.is_teacher` role entirely — it's now **admins + users**, where
  a user gets course-management rights either by creating a course or by being assigned as a
  teacher *for that specific course*. Replaced with `Enrollment.is_teacher` (per-course) and
  `Course.is_managed_by(user)` (`is_admin or created_by == user.id or` a per-course teacher
  `Enrollment`), which now backs all ~29 previously-global `current_user.is_teacher or
  current_user.is_admin` checks inside `course_page_enrolled`, plus the equivalent checks in
  `lms/routes/api.py` (file-serving, Drive picker import, folder-contents API) and the
  certificate download routes. Migration drops `user.is_teacher` with no data backfill — it
  never mapped to a specific course, so there was nothing meaningful to preserve.
  - **Who can assign a teacher / transfer ownership**: admins (via a new toggle on the admin
    panel's Course Management → Access page, alongside a "Make Owner" transfer control) *and*
    the course's own creator (via a new owner-only "Manage" tab on the course page itself,
    `Course.is_owned_by(user)` — `is_admin or created_by == user.id`, deliberately **not**
    including assigned teachers, so being made a teacher doesn't let you assign more).
  - **Ownership is transferable**: transferring sets the new `created_by` and automatically
    grants the outgoing owner a teacher role on that course, so they aren't abruptly locked
    out of a course they built.
  - Verified live end-to-end: a plain user created a course and saw the owner-only Manage
    tab; promoted a second enrolled user to teacher, who then got management rights on that
    course specifically (not on an unrelated course they weren't part of) but did **not** see
    the Manage tab themselves; transferred ownership to a third user, confirmed the new owner
    got the Manage tab, the old owner kept management access as a teacher (not abruptly
    locked out), and the uninvolved second course was untouched throughout.

## Out of scope for this pass

Online meetings (Jitsi), AI grading, AI-generated quizzes, AI course recommendations, paid
enrollment (data model stub only, no payment integration).
