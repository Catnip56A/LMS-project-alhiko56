local test user and admin passwords: TestPass123!

# LMS Rework — Development Checklist

Tracks implementation progress phase by phase, per the approved local-first roadmap. I'll
keep this checked off as work lands — treat it as the source of truth for "what's actually
done" alongside `git log`. See `setup_checklist.md` for the accounts/keys you need to
provide alongside this.

---

## Phase 0 — Security hardening

- [x] Global CSRF protection (`CSRFProtect`), all forms + `fetch()` calls covered
- [x] Upload limits (`MAX_CONTENT_LENGTH`) + real content/MIME sniffing (not just extension)
- [x] Rate limiting moved from in-memory to Redis — done as part of Phase 3 (see that
  section's `storage_uri` entry); this checkbox was just never synced back afterward
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
- [x] Show/hide password toggle (eye icon) on password input fields — new reusable
  `components/password_toggle.html` (self-contained inline SVG icons, no Font Awesome
  dependency, since `login.html`/`signup.html` are standalone pages that don't load it),
  included on login, signup, change-password, and the profile page's delete-account password
  confirm. Each field gets its own independent wrapper/button (verified via a jsdom
  simulation — clicking one field's toggle doesn't affect any other field on the same page).
  Admin user creation's password field (Flask-Admin, `lms/admin/__init__.py`) turned out to
  already be a plain `StringField`, not a masked `PasswordField` — it's already fully visible
  as text with nothing to toggle, so left as-is rather than a false "already handled" claim.

**Phase 0 is now fully complete.**

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

- [x] Merged the "Quizzes" tab into the "Assignments" tab (`lms/templates/course_page_enrolled.html`)
  — removed the separate nav-tab link and tab-pane; the quiz list (same cards as before) now
  renders inside the Assignments tab-pane, gated by the same `enrolled` check, right after the
  assignments list/pagination. Verified live: no more `#quizzes` tab or nav link in the
  rendered page, quiz cards appear correctly under Assignments.
- [x] Short-answer quiz questions now go to **manual teacher review** instead of
  case-insensitive exact-string auto-grading. `QuizAttempt.grade()` (`lms/models/__init__.py`)
  auto-grades mcq/true_false immediately as before, but leaves short_answer answers'
  `is_correct=None` (pending) and, if any answer is still pending, leaves the attempt's
  `score`/`passed` as `None` too rather than a premature auto-graded number — a correct
  free-text answer that doesn't literally string-match shouldn't fail someone. New
  `QuizAttempt.needs_manual_review` property and `grade_short_answer(question_id, is_correct)`
  method (recomputes score/passed once every answer is reviewed). No migration needed —
  `score`/`passed` were already nullable columns.
  - New teacher-only route `GET/POST /course/<id>/quiz/<id>/review`
    (`main.quiz_review`, gated by `course.is_managed_by`) — a queue of pending short-answer
    attempts with the student's answer, the question's reference answer, and Correct/Incorrect
    buttons per question, plus an "already graded" list below. Linked from a "Review Answers"
    button on each quiz card in the merged Assignments tab (teacher/admin only).
  - `quiz_result.html` (student-facing) now shows "Pending teacher review" instead of a score
    when `attempt.needs_manual_review`, and marks individual still-pending answers with an
    ellipsis instead of a check/cross.
  - Verified live end-to-end: submitted a short-answer attempt as a student (score/passed
    correctly landed `NULL`, answer's `is_correct` `NULL`) → result page showed "Pending
    teacher review" → teacher's review queue showed the pending answer with the student's
    text and a reference answer → graded it Correct → attempt's score/passed correctly
    finalized to 100%/passed → review queue moved it to "Already graded" → student's result
    page then showed the real 100% score. Note: the AI-grading alternative the backlog item
    floated is still out of scope per this plan's own exclusions — this is manual review only.
  - The original explicit-string auto-grader's short_answer branch in `_check_quiz_answer` was
    removed as dead code (never reached anymore, since `grade()` special-cases short_answer
    before calling it).

- [x] Teacher-facing promo codes & student enrollment — gap found post-hoc: both features
  exist and work, but only inside `CourseManagementView` (`lms/admin/__init__.py`), gated by
  `has_perm('course_management')`. A course-level teacher (`Enrollment.is_teacher=True`,
  `is_admin=False`) had no way to generate a promo code or add a student — hit a permissions
  wall. Fixed by exposing equivalent actions on the course page itself, gated at
  `course.is_managed_by(current_user)` (any assigned teacher, not just the owner — deliberate
  choice, since the alternative would restrict this to `is_owned_by` like assign-teacher/
  transfer-ownership; picked the broader tier since the whole point was making it
  teacher-facing). Implementation reused the existing model/logic rather than rebuilding it:
  - Promo codes: two new `elif action == ...` branches in the existing single-route POST
    dispatcher in `lms/routes/__init__.py` (same pattern as `assign_teacher`/
    `unassign_teacher`) — `create_promo_code` and `delete_promo_code`, reusing the generation
    logic from `create_promo_code` in `lms/admin/__init__.py` (`secrets.token_hex(4)`,
    existing `PromoCode.max_uses`). `delete_promo_code` scopes the lookup to
    `course_id=course.id` so a teacher can't revoke another course's code by guessing an id.
  - Adding students: `add_student` action, reusing the lookup/create logic from
    `add_student` in `lms/admin/__init__.py` but looking the target up by a single
    username-or-email text field (`User.query.filter(or_(User.username == identifier,
    User.email == identifier))`) rather than the admin panel's dropdown of pre-fetched
    candidates, since the course page doesn't have that full user list. Creates an
    `Enrollment` with `joined_via='direct_add'`.
  - UI: new "Access" section inside the existing "Manage" tab on `course_page_enrolled.html`.
    The tab's visibility moved from `is_course_owner` to `is_teacher_or_admin` so any managing
    teacher sees it; the pre-existing "Manage Teachers" block (assign/unassign teacher,
    transfer ownership) stays nested inside its own `is_course_owner` check within that tab, so
    non-owner teachers see Access but not teacher/ownership controls.
  - Verified live end-to-end as a non-owner teacher (`Enrollment.is_teacher=True`,
    `is_admin=False`): Manage tab appears without the owner-only section; generated a promo
    code (correctly attributed to that teacher via `issued_by`); added a student by username
    (created the `Enrollment` row with `joined_via='direct_add'`); re-adding the same student
    correctly no-ops with a flash warning instead of a duplicate row; revoking the promo code
    deletes it scoped to the right course.

**Phase 1 is now fully complete.**

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

### Phase 4 addendum — video transcription file-type bug + Drive import ownership gap

Context: same root-cause pattern as the earlier `_extract_drive_file_text` fix. Two separate
issues surfaced while investigating:

1. **`_transcribe_video` file-type bug** — [x] **fixed**. It guessed mime type from
   `content.title` via `mimetypes.guess_type()`, same flaw as the pre-fix document extractor:
   a freeform title with no extension (or an untrustworthy one) meant the function returned
   `None` before ever downloading the file, silently, with `embedded_at` still getting set (0
   chunks, indistinguishable in the DB from a legitimately empty file). Fixed the same way as
   the document case (`lms/rag_service.py`, `_transcribe_video`): download to a generic temp
   file first, sniff the real type from bytes via `filetype.guess()`, gate on
   `mime.startswith('video/'|'audio/')` instead of trusting the title. Removed the
   now-unused `import mimetypes`. No scope/cost implications — same unauthenticated public-link
   download already used elsewhere.

2. **`import_drive_file` 404s on files the worker didn't itself create — even fully public
   ones.** Verified live: `drive.file` scope does not expand based on a file's own sharing
   settings ("anyone with the link" is a Drive *sharing* concept, unrelated to OAuth `drive.file`
   *API* visibility, which only ever covers files the app created or that were selected through
   Google's Picker widget). Confirmed directly — a real, genuinely-public content row (id 15)
   downloads fine over the unauthenticated public link but 404s via `import_drive_file()` under
   the worker's own credentials, with a misleading "File not found... make sure it's shared or
   public" message.

   **Considered and rejected**: widening the worker's OAuth scope to `drive.readonly` (or full
   `drive`, needed for actual server-side `files.copy()`) to fix this. Verified against Google's
   official docs: both are classified **Restricted**, requiring brand verification, an OAuth
   Verification Center submission, and a **mandatory third-party CASA security assessment**
   (~$500-$1,800, redone **annually**) before the app can leave "Testing" status — and Testing
   status caps refresh tokens at 7 days, incompatible with an unattended background worker.
   "Internal"/Workspace "Trusted app" status would dodge the token-expiry/user-cap issue but
   isn't available (worker is a plain personal Gmail account, no Workspace org) and doesn't
   exempt the CASA requirement regardless. Ruled out on cost grounds.

   **Correction — Google Picker import already exists.** An earlier draft of this entry
   proposed "build a Picker-based import" as net-new work. That was wrong: the live import
   flow is *already* Picker-based (`importDriveModal` → `openGooglePicker()` →
   `/api/drive-picker-token` → `/api/picker-import`, all in `course_page_enrolled.html` +
   `routes/api.py`). The `import_drive_file`/`import_drive_folder` form actions in
   `routes/__init__.py`, plus `/api/import-drive-file` in `routes/api.py`, are **dead code** —
   grep confirms no template references those action names or a `drive_url` field.
   - [ ] Delete the dead import paths (`import_drive_file`/`import_drive_folder` action
     branches in `routes/__init__.py` ×2 call sites each, `/api/import-drive-file`) and the
     `_import_from_drive()` worker→user fallback helper added for them this session. Keep
     `google_drive_service.import_drive_file()` itself — `_import_drive_tree()` still uses it
     for folder imports.

   **Root causes of the Picker 404s** (`files.get` returning "File not found" on a file the
   teacher had just picked and owns), found by live debugging:
   - [x] **`GOOGLE_APP_ID` was unset.** `config.py` reads it, `.setAppId()` consumes it, and
     per Google's Picker docs it's *mandatory* for the per-file `drive.file` grant to register
     — without it the picker still opens and selects fine, but the backend never gets access.
     Value is the GCP project number (numeric prefix of `GOOGLE_CLIENT_ID`). Added to `.env`.
   - [x] **Resource keys were never threaded through.** Since 2021 Drive requires an
     `X-Goog-Drive-Resource-Keys: <fileId>/<resourceKey>` header for link-shared files
     (`type=anyone`/`domain`); without it the API returns a bare 404 indistinguishable from a
     real permissions failure. Picker surfaces it as `doc.resourceKey` but the code dropped it.
     Added an optional `resource_key` param to `get_file_metadata()` and
     `set_file_permissions()`, threaded from the picker callback → `submitPickerImport()` →
     `picker_import()`.
   - **Debugging lesson worth keeping**: several rebuild-and-retest cycles were wasted because
     the browser was hitting `just dev` on `:5000` while the rebuilds targeted the Docker
     `app-dev` container. Two independent servers, same codebase. `just dev` also snapshots
     `.env` at launch, so new env vars need a full restart, not just the `--debug` autoreload.

   **Import makes files world-readable — two follow-ups.** `picker_import()` calls
   `set_file_permissions(make_public=True)` whenever `allow_view` is set, which creates a
   Drive `{'type': 'anyone', 'role': 'reader'}` permission on a file in the *teacher's own
   personal Drive*. The RAG pipeline depends on this (`_download_public_drive_file` fetches
   bytes over the public link precisely to sidestep the `drive.file` scope limits), so the
   behaviour itself is intentional — but its presentation and lifecycle are not:
   - [ ] **Honest label.** The checkbox reads "Allow students to view" and is `checked` by
     default, implying course-scoped access. It actually grants unauthenticated link-based
     access to anyone holding the URL — no login, no enrollment check. Rename to something
     truthful ("Make viewable via link (public)") and reconsider the default-on.
   - [ ] **Revoke on delete.** The `make_public=False` branch only ever fires from the
     content-edit and submission routes (driven by `allow_others_to_view`). Deleting course
     content does not revoke the Drive permission, so files silently stay world-readable after
     the course stops using them. Revoke on content deletion.

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

- [x] Enabled the `pgvector` Postgres extension via migration. Discovered along the way that
  plain `postgres:17-alpine` doesn't ship the extension at all — switched `db-dev`/
  `db-staging`/`db-production` to `pgvector/pgvector:pg17` (same Postgres 17, extension
  pre-installed) across all three Compose profiles.
- [x] `ContentEmbedding` model (`course_content_id`, `chunk_index`, `chunk_text`,
  `embedding` — `vector(768)`) + `CourseContent.embedded_at`. Requested a reduced 768-dim
  embedding from Gemini (native output is 3072-dim) for cheaper storage/search and to stay
  under pgvector's HNSW index size ceiling if one gets added later; re-normalized the
  truncated vector per Google's own documented requirement.
- [x] `lms/gemini_client.py` (no Flask/DB dependency, mirrors `core_translator.py`'s role) —
  plain `requests`-based REST client for `embedContent`/`batchEmbedContents`,
  `generateContent` (text and file-grounded), and the File API upload/poll/delete flow used
  for video transcription. Built against the classic `generateContent` surface rather than
  a newer "Interactions API" mentioned in Google's docs — confirmed live that
  `generateContent` is still fully supported, and it's far better documented. Also
  discovered `gemini-2.5-flash` (the model version most recently documented) is no longer
  available to new API keys — using `gemini-flash-latest` instead, an alias Google
  maintains to always point at the current recommended model.
- [x] `lms/rag_service.py` (runtime layer, DB/Flask-aware, mirrors `translation_service.py`):
  word-boundary-aware chunking, `extract_text_for_content()` (plain text directly; PDF via
  `pypdf`; video/audio via Gemini File API transcription — Office docs are out of scope,
  that's Phase 8), `embed_content_item()`, and `answer_question()` (embeds the question,
  pgvector cosine-similarity retrieval scoped to the course, grounds a `generateContent`
  call in the retrieved chunks with a system instruction to answer only from that context).
- [x] `get_locked_content_ids()` mirrors `course_page_enrolled.html`'s folder-lock check
  (assignment/quiz gates, cascading to subfolders) so the assistant can't answer from
  content a student hasn't unlocked yet.
- [x] Indexing trigger: given how many separate places create `CourseContent` (13+ call
  sites — uploads, Drive folder imports, picker import, manual text entry, etc.), hooking a
  job into each individually was rejected as fragile. Instead: a recurring embedding sweep
  (`run_scheduled_embedding_sweep`, every 10 minutes, batched, RQ's built-in scheduler —
  same pattern as the Phase 5 translation sweep) picks up anything with `embedded_at IS
  NULL` regardless of how it was created, plus a manual "Reindex course content" button
  (owner/admin only) for immediate (re)indexing.
- [x] `POST /api/course/<id>/ask` — enrolled-user-only, rate-limited (10/min), returns an
  answer plus cited source titles linking back to `/api/file/c/<content_id>`.
  `POST /api/course/<id>/reindex` — owner/admin-only, rate-limited (5/hour).
- [x] "Ask AI" tab on the course page — question input, answer thread with source citation
  chips, reindex button for owners.

Verified live end-to-end through the actual running app (real session + CSRF, not a
bypass script): indexed a test text content item, asked a question through the real HTTP
endpoint, got a correct answer citing the right source; separately triggered the manual
reindex endpoint and confirmed the worker picked it up and completed it. The recurring
sweep bootstraps correctly on worker startup (`just up` logs confirm it alongside the
translation sweep).

- [x] Found and fixed a real bug during that verification, on the very first real document
  tried (`Yonca_Rework_Planning_Document.docx`): text extraction was calling the
  OAuth-scoped Drive API (`files.get`/`get_media` via `authenticate()`), which only succeeds
  for files the currently-resolved identity (the worker account) itself created or opened —
  the `drive.file` scope's restriction. Anything created under a different identity (e.g.
  uploaded before the Phase 4 worker account existed) 404s, even though the file is
  perfectly viewable — the existing file-viewer feature works precisely because it relies on
  the file's separately-configured public share link, not the OAuth-scoped API. Fixed by
  downloading via that same public link (bypasses `authenticate()`/OAuth entirely for
  extraction — handles Google's large-file "can't scan for viruses" interstitial too) and
  determining mime type from the file's extension instead of a metadata API call. While in
  there, added real `.docx`/`.pptx` text extraction (`python-docx`/`python-pptx`) — this is
  extracting raw text, unrelated to Phase 8's *visual preview rendering* scope, so pulling it
  forward wasn't scope creep, and it's exactly what the first real test needed.
- [x] Re-confirmed the "always `--build`" lesson from earlier this session applies to the
  worker too, not just the app: after fixing the extraction bug on the host filesystem, the
  still-running (pre-fix) `worker-dev` container processed a reindex request with its old
  baked-in code, silently deleting freshly-created good embeddings and replacing them with
  zero — a confusing "I reindexed and it still doesn't work" symptom that was actually just
  a stale container. `just up` (which now always rebuilds) resolved it immediately.

**Phase 6 is complete and verified live**, including the manual `GEMINI_API_KEY` setup.

### Phase 6 addendum — conversation history + markdown rendering

- [x] Markdown rendering in the Ask AI chat — answers were showing literal `**bold**`/`*
  italic*` characters, since the original renderer used `textContent` (safe against XSS,
  but doesn't render formatting). Added a minimal hand-written markdown renderer (bold,
  italic, bullet lists, paragraphs — the only formatting Gemini's answers actually use) that
  escapes HTML entities first and only ever introduces a fixed whitelist of tags afterward,
  so nothing from the (LLM-generated, ultimately content-derived) source text can smuggle in
  a real tag.
- [x] Smarter retrieval — `answer_question()` now does two-stage retrieval: pull a wider
  candidate pool (30 chunks), rank whole *files* by their single best-matching chunk, keep
  only the top 3 files, then take each file's best few chunks (4) from just those. Keeps
  answers coherent as a course accumulates more material instead of mixing fragments from
  every vaguely-related file into one prompt — no extra Gemini call needed, just a
  restructured query over the existing embedding-similarity results.
- [x] Persistent, consent-gated, multi-turn conversation memory. New `AiConversation` /
  `AiConversationMessage` models (one conversation per user+course) and
  `User.ai_history_consent` (nullable — `NULL` = not asked yet, `True`/`False` = a standing
  per-user choice, prompted via an inline banner the first time they use Ask AI).
  - **Multi-turn memory**: recent turns are fed back as context on every new question, and
    since a bare follow-up ("which of those has auto-grading?") often doesn't embed anywhere
    near the chunks it actually needs, an extra lightweight Gemini call rewrites it into a
    standalone question (using conversation context) before retrieval runs. Verified live: a
    real follow-up question correctly resolved "those" to the quiz types from the previous
    answer.
  - **Compaction**: once a conversation exceeds 6 raw messages, the oldest ones get folded
    into a rolling summary (another Gemini call) and deleted, so a long-running
    conversation's prompt size stays bounded rather than growing forever.
  - **Consent semantics**: the conversation is always tracked server-side while active —
    that's a technical requirement for multi-turn memory to work at all within a session,
    regardless of consent — but it's only ever displayed back to the user on a later visit
    if they've consented. Not-consented (declined or never-answered) conversations are
    hard-deleted 30 days after their last activity by a new recurring job
    (`run_scheduled_conversation_purge`, daily, same RQ-scheduler pattern as the translation/
    embedding sweeps); consented conversations are never auto-purged. Verified the purge
    logic directly (a manufactured 31-day-stale non-consented conversation was deleted, a
    consented one was left untouched).
  - New endpoints: `GET /api/course/<id>/conversation` (history, consent-gated),
    `POST /api/user/ai-history-consent`.
- [x] Thorough explanations + follow-up questions, and an effort-mode toggle. Updated
  `SYSTEM_INSTRUCTION` (`lms/rag_service.py`) to explain answers in depth rather than a bare
  one-liner, and to ask a clarifying follow-up question instead of guessing when a question is
  ambiguous/underspecified — applies at both effort levels. Added `EFFORT_LEVELS`
  ('quick'/'thorough', `DEFAULT_EFFORT='thorough'`): thorough pulls more source material (5
  files × 6 chunks vs. 3×4), gets a larger output budget, and an extra "go deep, use examples"
  instruction; quick stays closer to the original retrieval depth. Exposed as a Quick/Thorough
  button toggle on the Ask AI tab, remembered per-course via `localStorage` (a lasting
  preference, unlike the tab-position/draft state which is session-scoped).
  `POST /api/course/<id>/ask` accepts `effort` in the JSON body, validated against
  `EFFORT_LEVELS` server-side (invalid/missing falls back to the default) so a tampered
  client value can't do anything worse than picking a valid preset.
  - **Real bug caught during live testing**: the model behind `gemini-flash-latest` is a
    "thinking" model — its internal reasoning tokens count against the same
    `maxOutputTokens` budget as the visible answer, silently. A first attempt at
    quick=800/thorough=2048 token budgets caused answers to get cut off mid-sentence (even
    thorough's 2048-token answer ended mid-word) because thinking alone consumed 400+ tokens
    on a trivial question before any visible text was written, confirmed via a raw API probe
    showing `thoughtsTokenCount: 415` for a one-line question. Fixed by adding a
    `thinking_budget` param to `gemini_client.generate_content` (`generationConfig.
    thinkingConfig.thinkingBudget`): quick sets it to `0` (thinking off entirely, so all of
    its 1024-token budget goes to visible text — also makes quick mode cheaper and faster,
    fitting its name), thorough leaves it unset (thinking stays on for better reasoning
    quality) with a 4096-token budget sized to comfortably cover both thinking and a long
    answer.
  - **Also discovered while testing**: Gemini's free tier caps whatever model
    `gemini-flash-latest` currently resolves to at **20 requests/day** — hit it mid-session
    from ordinary manual testing. The 429's error body named the underlying model as
    `gemini-3.6-flash`, confirming the `-latest` alias has already rolled forward past the
    "gemini-2.5-flash" generation this was originally built against — a live consequence of
    deliberately pinning to `-latest` instead of a dated model name (to avoid the alias going
    stale), which also means Google can silently move us onto a new model generation with its
    own separate — and possibly tighter or laxer — free-tier quota bucket, with zero code
    change on our end. Worth checking AI Studio's usage dashboard by the *current* model name
    (not just "Gemini Flash" generically) when diagnosing quota issues going forward, since a
    dashboard panel for an older generation (e.g. "Gemini 2.5 Flash") can look nearly idle
    while the generation actually being called is the one that's exhausted. This makes the
    limits item below more concrete/urgent than originally filed, not just a "nice to have
    eventually."
- [x] Cross-model fallback so hitting one model's quota doesn't stop testing (or real usage)
  dead — `gemini_client.py` now tries `GENERATION_MODEL_FALLBACKS` in order whenever the
  primary model fails for any reason (quota, model unavailable, etc.), stopping at the first
  one that actually returns text. Candidates were verified live one by one rather than
  guessed — several plausible names turned out dead ends: `gemini-2.5-flash` and
  `gemini-2.5-flash-lite` both 404 with "no longer available to new users" (this API key is
  new enough to be locked out of the 2.5 generation entirely, despite both still appearing in
  `ListModels`), and `gemini-2.0-flash-001`/`gemini-2.0-flash-lite-001` were already
  quota-exhausted. Landed on `gemini-3.5-flash`, `gemini-flash-lite-latest`,
  `gemini-3.1-flash-lite`, `gemini-3-flash-preview` — confirmed reachable and on separate
  quota buckets from the primary `gemini-flash-latest` (→ `gemini-3.6-flash`).
  - Fallback attempts strip `thinkingConfig`/`maxOutputTokens` from the request rather than
    reusing the primary payload verbatim: confirmed live that `gemini-flash-lite-latest` 400s
    outright on `thinkingConfig` (no thinking support at all), and blindly reusing a small
    `maxOutputTokens` on a model with unknown thinking behavior would risk reintroducing the
    exact silent-truncation bug just fixed above. A fallback answer without the fine-tuned
    length/thinking budget beats a broken one.
  - Verified live end-to-end through the real `/api/course/<id>/ask` route (not just the raw
    client): with the primary model's daily quota exhausted, both Quick and Thorough effort
    modes correctly fell through to `gemini-3.5-flash` and returned complete, non-truncated,
    properly-terminated answers (1633 and 3839 chars respectively) with correct sources.
- [x] Usage limits now differentiate the two effort levels. Added `daily_cost` to each
  `EFFORT_LEVELS` preset (`lms/rag_service.py`: quick=1, thorough=3) and a second, cost-weighted
  limit on `/api/course/<id>/ask` (`lms/routes/api.py`) — `@limiter.limit("30 per day",
  cost=_ask_effort_cost)`, stacked alongside the existing flat `10 per minute` burst guard
  rather than replacing it. `_ask_effort_cost()` reads `effort` from the request body (falling
  back to the default if missing/invalid, same as the view itself does) so a tampered value
  can't dodge the higher cost. 30/day with thorough at 3x means up to 30 quick questions/day
  *or* ~10 thorough ones *or* any mix — sized a bit above the real 20/day ceiling observed on
  the primary model (to account for the fallback chain's extra real headroom) while still
  rationing thorough meaningfully harder than quick, per your framing. Keyed by IP
  (`get_remote_address`), matching every other rate limit in this app — not per-user.
  Verified live against the real Redis-backed counter (not mocked): one thorough call moved
  the day-bucket to `3`, a following quick call moved it to `4`, confirming the cost-weighting
  actually lands in storage the way the config says it should.
- [x] Site admins exempted from both `/ask` rate limits (`exempt_when=_is_site_admin`,
  checking `current_user.is_admin` specifically — deliberately *not*
  `course.is_managed_by()`, so a course owner or assigned teacher who isn't a site admin still
  gets rate-limited normally, per your explicit ask). Verified live: an admin's request left
  no Redis counter behind at all (exempt requests skip the check *and* the deduction), while
  the same request from `testuser` (a non-admin) created and incremented the usual counter.
- [x] **Real bug found via user report** ("it does not see 2 more files, even after I
  reindexed them"): `_extract_drive_file_text` (`lms/rag_service.py`) determined file type
  from `os.path.splitext(content.title)[1]` — but titles are freeform display names, not
  filenames, and two real course files were titled "Increment Privacy policy" and "terms of
  use" with no extension at all. The check silently returned `None` before even attempting a
  download, so those two files got `embedded_at` set (job "succeeded") but 0 chunks stored,
  forever, no matter how many times they were reindexed — a silent failure with no error
  surfaced anywhere. Fixed by downloading first and sniffing the actual file type from its
  bytes via the already-installed `filetype` library (`_DOCUMENT_MIMES`, keyed by MIME instead
  of extension) rather than trusting the title. Verified live: both files went from 0 chunks
  to 14 and 10 chunks respectively after reindexing with the fix, and a follow-up Ask AI
  question ("how many source documents...") correctly listed and cited all three files by
  name, where it previously only ever saw the one file whose title happened to end in
  `.docx`.
  - **Same root-cause risk not yet checked**: `_transcribe_video` uses the identical
    `os.path.splitext(content.title)` / `mimetypes.guess_type(content.title)` pattern to
    decide if a content item is a video/audio file worth transcribing. Any video/audio
    content titled without its extension would silently fail to transcribe for the exact same
    reason — not fixed here since no report of it happening yet, but worth a look if lecture
    videos ever seem to not be searchable via Ask AI.

### Phase 6 addendum — Video moment highlighting (planned, not started)

Design worked out in discussion, not yet implemented. Extends the existing video transcription
(`_transcribe_video`) so lecture videos surface specific *moments*, not just whole-file text.

- [ ] Audio-only extraction via `ffmpeg` (skip video pixels entirely — audio is the cheap,
  high-value part).
- [ ] Transcription with word/segment-level timestamps — Whisper (self-hosted, free, needs
  local compute) or Gemini (already have `GEMINI_API_KEY`, cloud, same quota caveats as the
  rest of Phase 6). Engine choice still open — see `setup_checklist.md`.
- [ ] Chunk by time-window or sentence boundary (~30–60s), storing start/end timestamps as
  metadata alongside the existing `pgvector` chunk embeddings, so Ask AI citations can point
  to the exact moment in a video, not just the file.
- [ ] New `video_moments` table (`video_id`, `timestamp`, `source`, `added_by`, `created_at`).
- [ ] Stage 1 (auto): keyword/regex pass over the transcript (e.g. "as you can see," "this
  diagram") — no API call needed.
- [ ] Stage 2 (student): a "flag this moment" button on the video player.
- [ ] Weighting instead of manual approval: `weight = COUNT(DISTINCT added_by)` per timestamp
  bucket — auto-detection gets a base weight, each unique student flag adds weight. A
  scheduled job (same RQ/Redis queue as the Drive worker and translation scheduler) promotes
  candidates crossing a threshold to vision-captioning.
  - Open question: fixed global threshold vs. configurable per course.
- [ ] Abuse handling: per-student rate limits + a teacher control to block a student or
  blocklist a specific timestamp — deliberately *not* per-flag manual approval, to avoid a
  bottleneck.
- [ ] Perceptual-hash frame diffing before any vision-captioning call (local, no API cost):
  near-identical frames near a promoted moment collapse to one caption call using the
  sharpest frame; meaningfully different frames (e.g. a slide transition) are captioned as two
  distinct citable moments; continuous change (drawing, scrolling) biases toward captioning
  the latest/most complete frame rather than diffing further.
- [ ] Wire moment-promotion jobs into the existing shared background job queue (Phase 3) — no
  new infrastructure needed.

**Explicitly out of scope for v1**: full frame extraction/OCR/vision-captioning of *every*
frame — too expensive. Only moments that cross the weighting threshold get a vision-captioning
call.


#### Decisions taken before implementation (2026-08-24)

**Transcription engine: self-hosted Whisper.** DeepL was considered and ruled out — its Voice
API (GA Feb 2026) is real-time WebSocket streaming for live meetings, has no batch endpoint for
pre-recorded files, documents no timestamps, and requires a paid subscription (our key is the
`:fx` free tier). DeepL is a translation engine, not a speech-to-text one. Gemini was the other
candidate but was rejected for this specific job: we hit 429s across every fallback model
repeatedly during Phase 6 testing, and LLM-estimated timestamps are less reliable than Whisper's
native word-level output — which is the whole point of the feature.
- Model **not** baked into the Docker image (models are 75MB–3GB and the image ships through
  GHCR on every deploy). Downloaded at runtime into a persistent volume instead. Starting with
  `small` (~500MB); size is configurable.
- Requires a new `apt-get install ffmpeg` layer in the Dockerfile's **final** stage — there is
  no apt layer there today, and the builder stage's packages aren't carried over. The worker
  runs from the same image, so the binary reaches both.

**BLOCKER — no video player to attach interactive features to. Deferred, must come back to.**
Course videos do not use an HTML5 `<video>` element; there isn't one anywhere in the app.
`lms/templates/file_viewer.html:172-177` renders an iframe → `lms/routes/api.py:864` →
302-redirect to `drive.google.com/file/d/{id}/preview`. That player is cross-origin with no
postMessage API, so `currentTime` cannot be read, seeking cannot be driven, and timestamp
deep-links (`#t=`) do not work against the preview wrapper.

Consequence: **student "flag this moment" (Stage 2) and click-to-seek citations cannot be built
until the player is replaced.** Everything else in this addendum is server-side and unblocked —
including auto-detection, weighting, frame extraction, and vision-captioning, since ffmpeg pulls
frames server-side without any player involvement.

Two escape routes when we return to this, neither yet chosen:
- Flask range-proxy the bytes and render a real `<video>` — works at any file size, but lecture
  videos then flow through gunicorn (bandwidth and worker-occupancy cost).
- Direct Drive byte URL into `<video>`, mirroring what audio already does successfully
  (`api.py:862` + `file_viewer.html:161-171`) — least code, but Drive serves large files behind
  a virus-scan HTML interstitial that a browser `<video src>` cannot get past. `_download_public_drive_file`
  handles that server-side with a confirm token; a raw `<video>` tag has no such escape.

Until then, timestamped citations render as text ("at 12:43 …"), which still beats pointing at a
50-minute file, just without one-click seeking.

**Three more prerequisites found during the same survey:**
- The transcription prompt explicitly forbids timestamps (`rag_service.py:257-258`) — must change.
- `chunk_text()` collapses all whitespace (`rag_service.py:97`), destroying any timestamp
  structure. Time-aware chunking needs a parallel function returning `(text, start, end)` rather
  than a change to that one.
- `ContentEmbedding` has no metadata column (`models/__init__.py:365-384`) — a migration is needed
  for start/end seconds. Precedent for JSON columns exists (`AiConversationMessage.sources`).
- Sources returned by `answer_question()` are file-level only —
  `{'content_id', 'title'}` at `rag_service.py:541-543`. The frontend ignores extra keys
  (`course_page_enrolled.html:3703-3717`), so timestamps can be added without breaking it.

**Production resource cost (measured/benchmarked before committing to the engine):**
- **Image growth: ~198 MB** (measured): onnxruntime 61, ctranslate2 60, PyAV 31, numpy 30,
  tokenizers 11, huggingface-hub 3.4, faster-whisper 1.4. No torch/CUDA — that's the reason
  `faster-whisper` was picked over `openai-whisper`, which would have pulled ~800MB+.
- **Model on disk: ~484 MB** for `small`, in the `./data/whisper-models` volume, downloaded
  once at runtime. Kept out of the image deliberately so deploys pull ~198MB, not ~680MB.
- **RAM: ~1.5 GB** while transcribing (`small` + int8; fp32 would be ~2.26 GB).
- Target VPS is **4 GB**. Baseline before Whisper is roughly 1.0-1.3 GB (gunicorn at
  `WEB_CONCURRENCY=3`, Postgres, Redis, Caddy), so a permanently-resident model would leave
  only ~1.2 GB headroom — too thin once Postgres grows and transient spikes hit.
  **Therefore the model is released after each job by default** (`WHISPER_KEEP_MODEL_LOADED=0`).
  Reloading from the local volume costs ~5-15s against a job that runs for minutes, so the
  singleton-warm optimization is a bad trade at this RAM budget. Set the env var to `1` on a
  RAM-rich host to keep it warm.
- Only the **worker** pays this cost — indexing runs through RQ jobs, never in a web request,
  so `app-*` mounts the volume but never loads the model.
- Fallback if RAM gets tight: `WHISPER_MODEL_SIZE=base` (~145 MB disk, ~600-700 MB RAM) or
  `tiny` (~75 MB, ~400 MB). One env change, no code edit.

**Implementation order (agreed: full scope, incrementally):**
1. [x] **Step 1 done — Whisper transcription with timestamps.**
   - `lms/transcription.py` (new): no Flask/DB dependency, mirroring `core_translator.py`'s
     role. Lazy model load behind a lock, `transcribe_with_timestamps()` returns
     `[{'start','end','text'}]`, `unload_model()` frees RAM, VAD filtering drops silence.
   - `lms/rag_service.py`: new `transcribe_video_segments()` is the real entry point (Whisper
     primary, `_transcribe_via_gemini()` retained as fallback). `_transcribe_video()` still
     returns flat text so the existing indexing path is untouched — storing timestamps is
     step 2 and needs the migration.
   - **No Dockerfile `apt` layer needed after all**: PyAV bundles the FFmpeg libraries, so
     transcription needs no system ffmpeg. That only becomes necessary at step 6 for frame
     extraction. (The original plan item "audio-only extraction via ffmpeg" is moot — PyAV
     decodes just the audio stream natively.)
   - Model-cache volume + `WHISPER_CACHE_DIR` wired into all 6 app/worker services across dev,
     staging, production. The prod/staging **workers had no `volumes:` block at all**, which
     is exactly where transcription runs. `just ensure-dirs` creates the directory.
   - `WHISPER_CACHE_DIR` defaults to a repo-relative path so `just dev` (outside Docker) works,
     with compose overriding it to `/app/data/whisper-models` — same pattern as
     `CERT_TEMPLATE_DIR`.
   - **Verified end to end on a real uploaded lecture (content id 22, 5:13 of audio):**
     `Detected language 'en' with probability 1.00` -> `Transcribed: 113 segments` ->
     `Whisper model unloaded` -> `6 chunks stored`, `embedded_at` set. Transcript content is
     coherent and correct (a lecture on Homer's Odyssey), i.e. genuine ASR, not noise.
     **~63s of CPU for 5:13 of audio = ~5x realtime**, so a 50-minute lecture lands around
     10 minutes — consistent with the VPS sizing estimate above. Model downloaded to the
     volume at runtime (464 MB) and RAM was released after the job, both as designed.
   - **Bug found and fixed during this verification**: the `content_type` sniffing call was
     first patched into the wrong `elif action ==` branch (`submit_assignment` rather than
     `upload_file`), leaving `detected_content_type` assigned where unused and *undefined*
     where read — a `NameError` on every file upload. `ruff` did not catch it (both names
     live in the same function scope) and neither did an import-level check; only tracing
     which action branch each line sat in exposed it. Now proven by executing the real
     handler through Flask's test client with a genuine MP4 (title deliberately carrying no
     extension) and asserting the created row is `content_type='video'`.
   - **Also fixed: the Picker import path had the same bug.** `_import_drive_tree`
     (`routes/api.py`) and `picker_import` both hardcoded `content_type='file'`, so *every*
     Drive-imported lecture would have indexed as 0 chunks. Both now derive it from Drive's
     authoritative `mimeType` via a shared `content_type_for_mime()` helper in
     `upload_validation.py`; the client-supplied mime is fallback only.
   - **Confirmed by instrumentation: Ask AI never re-transcribes.** Spies on
     `transcribe_video_segments`, `_transcribe_via_gemini`, `_download_public_drive_file`,
     `extract_text_for_content`, `gemini_client.upload_file` and `generate_content_with_file`
     recorded **zero calls** during a real `answer_question()` run. Corroborated by the answer
     itself, which quoted Whisper's phonetic spellings ("Scilla"/"Cribdis") rather than the
     correct Scylla/Charybdis — i.e. it was reading our stored transcript, not the audio.
     Transcription lives only in `embed_content_item()` (indexing jobs); the query path just
     embeds the question and vector-searches stored chunks.
   - **Both content_type bugs verified fixed by execution, not inspection:** the `upload_file`
     path via Flask test client (row created as `'video'`), and the Picker path via a real
     `POST /api/picker-import` with Drive metadata reporting `video/mp4` (HTTP 200, row created
     as `'video'`).

   - [ ] **Open test gap — permission gating not covered.** The retrieval checks run so far
     query `ContentEmbedding` directly, unscoped. They prove content is indexed and matchable
     but do **not** exercise the filters the real `/api/course/<id>/ask` applies: publication
     status (`is_published`), folder locks (`get_locked_content_ids()`, which resolves
     assignment- and quiz-gated folders), and course enrolment. A student could in principle
     receive AI answers drawn from material they cannot yet open. Needs a test with a
     non-enrolled user, an unpublished item, and a locked-folder item, asserting none of them
     appear in `sources`. Worth folding into `/security-review` at the next phase wrap.

   - **Known limitation, by design — this is what step 2 fixes:** those 113 timestamped
     segments collapse into 6 chunks with **no timestamps stored**. `chunk_text()` flattens
     whitespace and `ContentEmbedding` has no column to hold start/end seconds, so the timing
     is produced and then discarded. Step 1's goal was only to prove timestamps *can* be
     produced; persisting them needs the migration in step 2.
2. [ ] Migration for chunk start/end seconds; time-aware chunking; video chunks stored with
   timestamps.
3. [ ] Citations carry timestamps through `answer_question()` → API → chat UI as text.
4. [ ] `video_moments` table + Stage 1 auto-detection (keyword/regex pass, no API cost).
5. [ ] Weighting + promotion job on the existing RQ queue.
6. [ ] Perceptual-hash frame diffing + vision-captioning of promoted moments only.
7. [ ] *(blocked on player)* student flagging UI, per-student rate limits, teacher block/blocklist
   controls, click-to-seek citations.
### Phase 4/6 addendum — cleanup + review findings (2026-08-24)

**Dead code removed** (~1,400 lines), each confirmed unreachable by a repo-wide reachability
audit before deletion — no template posts the action, no `url_for`, no `fetch`:
- [x] `edit_course_page` route (536 lines) + `lms/templates/course_editor.html` (848 lines).
- [x] All four `import_drive_file`/`import_drive_folder` form-action handlers, plus
  `/api/import-drive-file` and the `_import_from_drive()` helper. **The Drive import feature
  itself is untouched** — the live path is the Picker flow (`/api/drive-picker-token` ->
  `/api/picker-import`), and `google_drive_service.import_drive_file()` is still used by
  `_import_drive_tree` for folder imports. Only unreachable duplicates went.
- [x] MoxoTest removed entirely (model, `MoxoTestView`, `moxo_test_management` permission,
  route, both navbar links, SPA page, nav default) + migration `a1b2c3d4e5f6` dropping the
  (empty) `tavi_test` table and stripping the permission from `user.admin_permissions` and the
  nav entry from `site_settings.navigation_items` — column defaults only affect new rows.
  Verified: `/moxo-test` -> 404, nav entry gone from the live row, 143 routes still register.
  **Correction to an earlier claim in this file:** MoxoTest was described as dead code. It was
  not — it was linked from `components/navbar.html` via hardcoded hrefs (which a `url_for`
  grep misses). Removing it was a product decision, taken explicitly.
- [x] `certificate_generator._find_template()` no longer hardcodes `moxo_template.*`; it falls
  back to the first template in `TEMPLATE_DIR`, so any user-uploaded file works with no config.
  Admin -> Certificate Tuning selection still wins. Verified with two uploaded templates
  (first-alphabetical fallback, explicit selection honoured, bad name falls back, empty dir
  raises). Also fixed its error message, which named `STATIC_CERTS` while the directory is
  env-configurable and actually `/app/data/cert-templates` in Docker.

**`/code-review` findings, all fixed:**
- [x] `serve_content_by_db_id` gated the in-app viewer on `content_type == 'file'`, so the new
  `'video'` rows fell through to a raw Drive redirect — losing `file_viewer.html` and exposing
  the Drive file id the route exists to hide. Now accepts both, and a title-extension guess can
  no longer override a type resolved from sniffed bytes.
- [x] RQ's default job timeout is 180s; Whisper needs ~10 min for a 50-minute lecture. A
  timed-out horse is SIGKILLed, so the sweep's `finally` re-enqueue never runs and the
  recurring embedding sweep would die until worker restart. `lms/queue.py` now sets
  `default_timeout` (env `RQ_JOB_TIMEOUT_SECONDS`, default 3600).
- [x] Legacy rows stored as `content_type='file'` that are really lectures would never be
  transcribed. Fixed *without* a backfill (a migration can't sniff Drive files):
  `_extract_drive_file_text` now transcribes off the copy it already downloaded when the bytes
  sniff as video/audio — self-healing, no second download. Migration `b2c3d4e5f6a7` clears
  `embedded_at` for rows that indexed to zero chunks so the sweep retries them with current
  code (0 rows affected here; matters for existing deployments).

**`/security-review`: no new vulnerabilities.** Explicitly checked and cleared: the permission
model after removing a permission key (every full-admin check uses `admin_permissions is None`,
never truthiness, so a sub-admin left with `[]` narrows rather than escalates), authorization on
the changed viewer path, path traversal in the new temp-file/transcription/template code, and
SSRF in the Drive download (hardcoded host, `file_id` passed as a query param).

- [x] **Real exposure found and fixed (pre-existing, not introduced here).** Uploads were staged
  in `static/temp/`, which sits inside Flask's static root — so course files *and assignment
  submissions* were fetchable unauthenticated at `/static/temp/<timestamp>_<filename>` while
  staged, and before this session's cleanup fix they were left there permanently. **Confirmed
  live**: a probe file written inside the container was served over plain HTTP with no auth.
  Fixed at the root by moving staging to `data/upload-staging/` (outside the static root,
  env-overridable via `UPLOAD_STAGING_DIR`), adding the volume to all 6 app/worker services,
  creating it in `just ensure-dirs`, and excluding it plus `static/temp/` from git and Docker
  build context. Verified: staging dir is outside `app.static_folder`, and a real upload leaves
  no leftover file.
  - Note: an earlier probe of this wrongly returned 404 and nearly led to dismissing it — the
    test wrote to the *host* path, but `app-dev` has no `./static` bind mount, so the container
    never saw the file. Test inside the container when checking container-served paths.

- [x] Temp-file leak on the upload success path (only error branches cleaned up). Fixed —
  **twice**, because the first fix landed in the wrong `elif action ==` branch. This is the
  same failure mode as the `detected_content_type` bug earlier in this session: this file has
  several near-identical upload blocks, so a `str.replace(..., 1)` silently targets the first
  one, which is `submit_assignment`, not `upload_file`. Verified by locating the branch bounds
  explicitly and asserting every `os.remove` sits in the intended branch.

- [ ] **Still open** — the permission-gating test gap logged above (unpublished content and
  locked folders in Ask AI `sources`). Not addressed in this pass.

## Phase 7 — AI audio overview

- [ ] Single-narrator spoken summary (summarization pipeline + TTS step)
- [ ] Two-host conversational format (only after single-narrator works)

*(Requires the ElevenLabs API key in `setup_checklist.md` Phase 7 first.)*

## Phase 8 — Office file preview

- [ ] Excel -> SheetJS (xlsx) + Univer
- [ ] Word/PDF/Powerpoint -> Libreoffice conversion to PDF(if not pdf already) and iframe later

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
