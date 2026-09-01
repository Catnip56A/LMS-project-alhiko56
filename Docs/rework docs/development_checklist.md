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
   - [x] **Delete the dead import paths — done.** Turned out already done: commit `0a5d74a`
     ("whisper transcription + dead code purge") had already deleted the
     `import_drive_file`/`import_drive_folder` action branches in `routes/__init__.py`,
     `_import_from_drive()`, and `/api/import-drive-file` — this checkbox just hadn't been
     ticked retroactively. **Found while re-verifying (2026-08-31): the note below was also
     stale.** `google_drive_service.import_drive_file()`/`import_drive_folder()` were kept on
     the stated belief that `_import_drive_tree()` still called them — checked again and it
     doesn't (it's been using `get_file_metadata`/`collect_folder_structure` directly since the
     R2 migration rewrote it); a repo-wide grep confirmed zero remaining callers of either
     function, or of `extract_file_id_from_url` (which only those two called). Deleted all
     three (124 lines, `lms/google_drive_service.py`) — confirmed via `create_app()` still
     registering all 151 routes with no import errors, live in the running container.

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

   **Import makes files world-readable — two follow-ups. Re-evaluated 2026-08-31, after the R2
   migration — see below for what's actually still true.** `picker_import()` used to call
   `set_file_permissions(make_public=True)` whenever `allow_view` was set, creating a Drive
   `{'type': 'anyone', 'role': 'reader'}` permission on a file in the *teacher's own personal
   Drive*. The RAG pipeline depended on this at the time (`_download_public_drive_file` fetches
   bytes over the public link precisely to sidestep the `drive.file` scope limits).
   - [x] **Honest label — re-checked, no longer needed.** The premise changed: the R2
     migration's Picker-import rewrite (see the "Cloudflare R2 migration" addendum further
     down) already stopped `picker_import()` from calling `set_file_permissions` at all — it
     copies bytes into R2 instead of referencing the Drive file in place, and the same is true
     of the direct-upload path. Checked all three checkboxes this concern was about
     (`fileAllowView` on direct upload, `pickerAllowView` on Picker import, the
     `visibility_{{ item.id }}` toggle) against current behavior: for R2-backed content (the
     normal case now and for everything created going forward) each one only ever sets
     `CourseContent.allow_others_to_view`, an app-level flag enforced by this app's own
     login+enrollment-gated routes — not a Drive public link. "Allow students to view" is an
     accurate description of that. Renaming it to "Make viewable via link (public)" as
     originally proposed would now be **wrong**, not more honest — it would describe a Drive
     side effect that no longer happens for the common path. Left the labels as-is.
   - [x] **Revoke on delete — real bug found and fixed, but narrower than described.** The
     Picker-import fix above also means there's no world-readable Drive permission being
     created for new content at all anymore, so the described leak mostly can't happen going
     forward. But auditing every `set_file_permissions` call site while checking the above
     turned up two real, still-live gaps for the one case the R2 migration didn't touch — a
     `CourseContent` row that's `drive_file_id`-set, `is_imported=True`, and genuinely not yet
     R2-migrated (`r2_key IS NULL`; only possible for content predating this app's current
     ingestion paths, or not yet backfilled):
     1. `toggle_content_visibility` (`routes/__init__.py`) gated its Drive-permission update on
        `content.drive_file_id` alone — but `drive_file_id` is *retained as provenance on every
        R2-migrated row too* (see the R2 addendum), so toggling visibility on an already-
        migrated item was still reaching out to Drive and flipping the permission on the
        now-unused retained copy, for no reason and with no bearing on how the content is
        actually served. Fixed to also require `not content.r2_key`.
     2. `delete_content` deleted the whole Drive file outright when the app had uploaded it
        itself, but for an *imported* Drive-hosted row (referencing a file in the teacher's own
        Drive, never owned by the app) it did neither that nor a permission revoke — exactly
        the described leak, for this one now-narrow case. Added a `set_file_permissions(...,
        make_public=False)` call for that specific branch (`drive_file_id` set, `is_imported`,
        `not r2_key`), best-effort (a Drive-side failure logs a warning but never blocks
        deleting the row itself — the DB record is authoritative regardless of what happens on
        Drive's side).
     **Verified live** (real Flask test client, real admin session, real Drive-authenticated
     service): toggling visibility on a real R2-migrated row (content 20) made zero
     `set_file_permissions` calls (previously would have made one); a synthetic still-Drive-
     hosted imported row correctly triggered the new revoke call on delete
     (`set_file_permissions(service, 'fake_...', make_public=False)`), and — with that call
     forced to fail — the row was still deleted successfully, confirming the delete path isn't
     hostage to Drive API availability.

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

### Phase 6 addendum — Video moment highlighting (2026-08-28, done and live-verified — 10 of 10)

Design worked out in discussion. Extends the existing video transcription so lecture videos
surface specific *moments*, not just whole-file text. Full detail, evidence, and the agreed
step-by-step order are in "Decisions taken before implementation" immediately below this list
— this list is the plan; that section is the log of what's actually landed.

- [x] ~~Audio-only extraction via `ffmpeg`~~ — **moot, not needed.** `faster-whisper` decodes
  via PyAV, which bundles the FFmpeg libraries and reads only the audio stream natively. No
  separate extraction step, no system `ffmpeg` install. **Frame extraction (below) also needs
  no system ffmpeg** — PyAV bundles it there too; an earlier draft of this note incorrectly
  said a Dockerfile `apt-get install ffmpeg` layer would be needed for that step. It isn't.
- [x] **Transcription with word/segment-level timestamps — done.** Engine: self-hosted Whisper
  (`faster-whisper`), not Gemini — see the engine comparison below. Verified end to end on a
  real uploaded lecture: 113 timestamped segments, correct transcript content.
- [x] Chunk by time-window or sentence boundary (~30–60s), storing start/end timestamps as
  metadata alongside the existing `pgvector` chunk embeddings, so Ask AI citations can point
  to the exact moment in a video, not just the file. **Done — see "Step 2 done" below.**
- [x] **Schema — two tables, not one.** `VideoMomentFlag` (append-only signal log: one row
  per auto-detection or student click, `course_content_id`/`timestamp_seconds`/`bucket_index`/
  `source`/`added_by`) and `VideoMoment` (the low-volume, mutable, promoted artifact —
  `status`/`caption`/`frame_phash`/`attempts`). Split deliberately: `VideoMomentFlag` is
  high-volume and never mutated; collapsing them would mean 99% of rows have NULL
  caption/status columns, and a spam-flag delete could risk an already-embedded caption.
  `Enrollment.moment_flags_blocked` (new column, default false) is the per-course
  student-block flag, mirroring `Enrollment.is_teacher`'s existing scope rather than a new
  moderation table. Migration `f6a7b8c9d0e1`, applied and confirmed live via `\dt` +
  `\d enrollment`.
- [x] **Stage 1 (auto)**: keyword/regex pass over the raw per-Whisper-segment transcript
  (English + Russian trigger phrases — this app ships `SUPPORTED_LANGUAGES = ['en','ru']` and
  Whisper auto-detects), run inside `embed_content_item` (`lms/rag_service.py`) rather than
  inside `transcribe_video_segments` — the self-healing legacy-row path
  (`_extract_drive_file_text`) also produces a segment list via a different route, and
  `embed_content_item` is the one place both converge. New `lms/moment_service.py`:
  `detect_auto_moments`/`record_auto_moments`. Unit-verified with a synthetic segment list:
  correctly detected 3 real trigger phrases, correctly collapsed two same-bucket hits to one
  (earliest kept), correctly skipped the Gemini-fallback whole-file placeholder shape
  (`start=end=0.0`).
- [x] **Stage 2 (student)**: "Flag this moment" button, `lms/templates/file_viewer.html`'s
  `.controls-row`, matching the existing `#fullview-btn`/`#zoom-in-btn` button family and the
  reindex-button's disable→text-swap→`setTimeout` feedback convention. `POST
  /api/content/<id>/moment-flag` (`lms/routes/api.py`) — rate-limited **per-user, not the
  app's default per-IP** (a lecture hall/campus NAT shares one IP, and that convergence is
  the intended signal, not abuse), with the real anti-spam primitive being a DB unique
  constraint (`uq_video_moment_flag_bucket_user`), not application logic. **Teacher flag =
  instant promotion**: if the flagging user manages the course, their single flag queues the
  bucket for captioning immediately, bypassing the weight threshold — verified live.
- [x] **Weighting — adaptive, not fixed.** Resolves the "fixed global vs. configurable per
  course" open question: `threshold = clamp(ceil(enrolled_student_count × 0.10), 2, 12)` —
  computed live per course (`moment_service.threshold_for_course`), not a config setting.
  `weight = COUNT(DISTINCT student added_by) + (1 if any auto flag present)`. Bucketed on the
  existing `SEGMENT_CHUNK_WINDOW_SECONDS` (45s) grid with an adjacent-bucket merge pass for
  the boundary artifact (two flags either side of a 45s edge). Computed live at query time,
  not materialized — the decisive reason is retroactive correctness: blocking a student must
  instantly zero out their contribution to every bucket they ever touched, with no backfill,
  which only a live query gives for free. **Verified live**: a real student flag + a real
  auto-detection flag on the same bucket of a real lecture correctly summed to weight 2,
  correctly promoted; a second isolated test confirmed a blocked student's vote is excluded
  from the weight computation with zero backfill.
- [x] **Abuse handling**: per-user rate limits (6/min, 60/day) plus the DB unique constraint
  (the layer that actually matters — a single student account cannot push a bucket's weight
  above 1 no matter how many times they click). Teacher moderation: `POST
  /api/course/<id>/moment-flags/block-user` (blocks a student, retroactive by construction —
  see above) and `POST /api/content/<id>/moments/block` (blocks a specific bucket forever;
  if already captioned, also deletes its `ContentEmbedding` row so it stops being cited
  immediately). No moderation queue, no per-flag approval — promotion stays fully automatic,
  teachers only intervene reactively, per the original design principle. A small manager-only
  collapsible panel in `file_viewer.html` (`GET /api/content/<id>/moments`) lists flagged/
  promoted moments with per-row "Block moment" and per-flagger "Block student" actions. All
  three routes verified live via the real Flask test client with real session cookies.
- [x] **Perceptual-hash frame diffing** (`lms/frame_extraction.py`, new — no Flask/DB
  dependency, mirrors `transcription.py`'s split): samples a backward-weighted window of
  frames via PyAV (both signal sources — the auto trigger firing mid-phrase, a student's
  reaction-click — are systematically late relative to the actual visual), hashes each with
  `imagehash.phash`, and classifies by consecutive Hamming distance: all near-duplicate → one
  caption call on the sharpest frame, timestamped at the window's first frame; one or two
  large jumps → a real transition, captioned as two distinct moments (capped at 2); sustained
  middle-band distances (continuous change — drawing, scrolling) → caption only the last/most
  complete frame. Cross-moment dedup against already-captioned frames on the same video skips
  a redundant API call entirely when the lecturer returns to an earlier slide — the single
  highest-leverage cost saving for slide-heavy lectures. Thresholds (6 near-duplicate / 14
  distinct) are reasoned starting points, not yet tuned against a large real corpus.
- [x] **Vision captioning wired into the RAG pipeline — the core hypothesis, proven live.**
  New `gemini_client.generate_content_with_image` sends the frame inline as base64 (not the
  heavier async File API used for video transcription — one HTTP request instead of
  upload+poll+reference+cleanup), routed through the existing model-fallback chain. A
  captioned `VideoMoment` becomes an ordinary `ContentEmbedding` row
  (`[On-screen visual] <caption>`, `start_seconds` = the moment's refined timestamp) — **zero
  changes to `answer_question()`**. **Live-verified end to end** on the real migrated lecture
  (course 1, content 22): a real Gemini vision call (first model 503'd, the existing fallback
  chain correctly recovered on the next candidate) produced a real caption of an actual video
  frame; a real Ask AI question then cited it as a `2:02` timestamp chip alongside the
  transcript-based citations, with the answer text correctly drawing on the caption's content
  — exactly the "so Ask AI citations can point to the exact moment in a video" goal this whole
  epic was scoped around, now extended to visual (not just spoken) moments.
- [x] **Critical trap found and fixed as part of this work, not after**: `embed_content_item`
  opens with `ContentEmbedding.query...delete()` — any reindex would have silently and
  permanently deleted every caption embedding, since the promotion sweep never re-processes a
  bucket that already has a `VideoMoment` row. Fixed by re-embedding from
  `VideoMoment.caption` (the durable artifact) at the end of every `embed_content_item` run —
  no new vision API call needed. **Verified live**: captioned a real moment, triggered a real
  full reindex (including real Whisper re-transcription) of content 22, confirmed the caption
  embedding was still present and byte-identical afterward.
- [x] Wire moment-promotion jobs into the existing shared background job queue — done exactly
  like the existing embedding sweep: `job_manager.run_scheduled_moment_promotion`/
  `ensure_moment_promotion_scheduled`, registered in `lms/worker.py`, confirmed scheduled live
  in RQ's `ScheduledJobRegistry` (`moment-promotion-recurring`, every 30 minutes, batch size
  5). Deliberately slower/smaller-batched than the embedding sweep since each promotion
  downloads a whole video and spends a real API call, sharing one worker with Whisper
  transcription.

**New dependencies**: `av` (promoted from transitive — was already pulled in by
`faster-whisper` but never imported directly — to a direct `pyproject.toml` dependency, since
relying on a transitive pin for a feature that now imports it directly is fragile) and
`imagehash` (new, pulls in `scipy`/`pywavelets`).

**Explicitly out of scope for v1**: full frame extraction/OCR/vision-captioning of *every*
frame — too expensive. Only moments that cross the weighting threshold (or a teacher's direct
flag) get a vision-captioning call. Also out of scope, a deliberate decision made before
implementation: surfacing captioned moments anywhere besides Ask AI citations (e.g. seek-bar
markers) — that's a materially larger, separate frontend feature.


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

**BLOCKER — no video player to attach interactive features to. RESOLVED (2026-08-27) — see
"Phase 6 addendum — Cloudflare R2 migration" below.** Course videos previously had no HTML5
`<video>` element anywhere in the app (`file_viewer.html:172-177` rendered an iframe →
`api.py:864` → 302-redirect to `drive.google.com/file/d/{id}/preview`, cross-origin with no
postMessage API). The two escape routes floated at the time this was written (Flask range-proxy,
or direct-to-Drive with a proxy fallback) were both superseded once Cloudflare R2 was chosen as
the storage backend — see below for why. `file_viewer.html` now renders a real `<video>` element
for every video/audio item, backed by R2 presigned URLs.

Consequence, now lifted: student "flag this moment" (Stage 2) and click-to-seek citations can
now be built against a real player. Click-to-seek citations are done (see the R2 addendum);
"flag this moment" itself is still not built.

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
     ~63s of CPU for 5:13 of audio on this 16-core dev box. Model downloaded to the volume
     at runtime (464 MB) and RAM was released after the job, both as designed.
   - **Correction — the "~5x realtime" / "~10 min for a 50-min lecture" estimate above was
     wrong, found while sizing an actual hosting plan (Senko DE-EPYC-2: 2 vCPU, 4GB DDR5 ECC,
     Frankfurt).** That figure conflated two effects: 16 cores being available, and VAD
     trimming the lecture's natural pauses before they ever reached the decoder — neither
     transfers to a real deploy target. Isolated the two with a controlled test: same real
     lecture (re-downloaded via its retained `drive_file_id`), same production settings
     (`vad_filter=True`), only core count changed (`docker update --cpus=2` on the actual
     worker container). Result: **150.3s vs 70.8s — 2.1x slower on 2 cores, not the ~8x naive
     scaling would predict.** For a 50-minute lecture: **~24 minutes on 2 vCPUs**, not ~10.
     Caveat: `docker update --cpus` throttles CPU time but not the container's *visible* core
     count (`nproc`/`sched_getaffinity` still reported 16), so CTranslate2's `cpu_threads=0`
     auto-detect likely still sized its thread pool for 16 and fought over the 2-core budget —
     the real DE-EPYC-2 box (genuinely 2 cores visible) is probably somewhat faster than this,
     but this is the only number actually measured, so treat it as a conservative upper bound.
   - **Fix applied**: `WHISPER_CPU_THREADS` env var (`lms/transcription.py`, default `0` =
     auto-detect) — left unset locally (uses every dev-machine core, unaffected), set
     explicitly to the real vCPU count on the production server's own `.env` (documented in
     `setup_checklist.md`, not hardcoded into tracked `docker-compose.yml`, since it's a
     property of whichever box is actually running the worker and needs to survive a plan
     resize without a code change).
   - Functionally this still fits: transcription runs as a background RQ job, not blocking the
     upload, and the job timeout was already set to 3600s for this exact reason. The real
     consequence is queueing — several long lectures uploaded close together process serially
     on one worker, so the last one in a batch can sit well over an hour before it's searchable.
     Not addressed in this pass; a second worker process would be the fix if that matters.
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

   - [x] **Permission-gating test gap — closed.** Two halves, both now verified through the
     real `answer_question()` entry point (not a reconstructed query): private content
     (`allow_others_to_view=False`) was genuinely leaking and is now fixed; quiz/assignment
     folder-locking (`get_locked_content_ids()`) was already correctly wired in and is now
     proven both directions with a live before/after-passing test. Full evidence at the
     bottom of this addendum, dated 2026-08-24.

   - **Known limitation, by design — this is what step 2 fixes:** those 113 timestamped
     segments collapse into 6 chunks with **no timestamps stored**. `chunk_text()` flattens
     whitespace and `ContentEmbedding` has no column to hold start/end seconds, so the timing
     is produced and then discarded. Step 1's goal was only to prove timestamps *can* be
     produced; persisting them needs the migration in step 2.
2. [x] **Step 2 done — migration for chunk start/end seconds; time-aware chunking; video
   chunks stored with timestamps.**
   - Migration `c3d4e5f6a7b8`: `content_embedding.start_seconds`/`end_seconds` (nullable
     `Float`). Additive-only — NULL for existing/future text/PDF/DOCX/PPTX chunks, which have
     no time axis.
   - New `chunk_segments_by_time()` in `rag_service.py`, parallel to `chunk_text()` (not a
     replacement — plain text still has no timestamps to preserve). Groups Whisper's
     timestamped segments into ~45s windows, also closing a window early if it would exceed
     `CHUNK_SIZE` chars, so dense speech can't produce an unbounded chunk.
   - **Bug caught by testing before this ever touched real data**: the initial version only
     checked the size/window limits *before adding a new segment* to the current chunk — so a
     single segment that alone exceeds `max_chars` never got split, since there's no "next
     segment" to trigger the check. This is exactly the shape of the Gemini-fallback path
     (one segment spanning the entire file, no per-segment timestamps) — a fallback
     transcription would have produced one giant, unbounded chunk despite the docstring's
     explicit claim that it "degrades gracefully." Caught with a 7-case test suite (window
     split, char-based split, the oversized-single-segment case, empty/blank input, and a
     realistic randomized 113-segment transcript with an exact word-coverage assertion — no
     text dropped or duplicated). Fixed by sub-splitting an individual oversized segment with
     `chunk_text()`'s own word-boundary logic; all its pieces share that segment's start/end,
     since a single transcript segment has no finer-grained timing to split by.
   - `extract_text_for_content()` now returns either a plain `str` (untimed sources) or a
     `list[dict]` of timestamped segments (video/audio) — `embed_content_item()` dispatches on
     which shape it got and normalizes both into the same `{'text','start','end'}` chunk shape
     before embedding, so the storage loop doesn't care which source produced them.
   - The self-healing branch in `_extract_drive_file_text()` (legacy rows mis-typed as `'file'`
     that actually sniff as video/audio, from the earlier addendum) now preserves the segments
     it already produces instead of flattening them to text first — it gets real timestamps
     for free, no extra work.
   - `_transcribe_video()` (the old flat-text-only wrapper) had exactly one caller, which this
     step rewired to call `transcribe_video_segments()` directly — removed rather than left as
     an orphan, same dead-code discipline as the rest of this session.
   - **Verified against the real database, not a reconstruction**: re-ran indexing on content
     22 (the same real 5:13 lecture from step 1). 113 raw Whisper segments correctly
     time-chunked into **8 stored chunks**, each ~43-45s, all with real non-NULL, chronological
     timestamps (e.g. `[0.0-44.6]`, `[44.6-88.6]`, ... `[307.4-329.2]`), transcript content
     still coherent. **Zero regression on documents**: re-ran indexing on the three existing
     document rows (ids 17/19/20) and got the exact same chunk counts as the original Phase 6
     verification (10/1/13), with `start_seconds`/`end_seconds` correctly `NULL` on all of them.
3. [x] **Step 3 done — citations carry timestamps through `answer_question()` -> API ->
   chat UI, as text (click-to-seek stays blocked on the video-player work).**
   - `_format_timestamp(seconds)` (new, `rag_service.py`): `5:12`, or `1:05:12` past the hour.
   - Prompt context blocks now label a video chunk as `[Source: title, at 5:12]` instead of
     just `[Source: title]` when `start_seconds` is set — nudged the system instruction to
     let the model reference that moment in prose ("you may reference that moment... so the
     student can find it in the video"), rather than only surfacing it in the citation chip.
   - `sources` entries gain `timestamp` (formatted string) and `start_seconds` (raw float)
     when the file's best-matching chunk has one; **unchanged shape for text/PDF/DOCX**
     (`{content_id, title}` only) — no schema change needed since `AiConversationMessage.sources`
     is a JSON column and both the API route and `get_conversation_history` already pass
     `sources` through verbatim.
   - One source per file at the time this step shipped — **since superseded**: multiple
     citation chips per file (one per distinct moment actually cited, not just the
     best-matching chunk) landed as part of "Video moment highlighting" above.
   - Frontend chip (`course_page_enrolled.html`): `🎥 title (5:12)` when a timestamp is
     present, `📄 title` otherwise — same click-through to `/api/file/c/<id>`, informational
     only for now, consistent with the player blocker noted earlier in this addendum.
   - **Verified against the real re-indexed video (content 22), not a reconstruction.** Asked
     `answer_question()` directly "At what point in the video does the lecturer talk about
     Odysseus returning from the land of the dead?" — the model answered *"...around the
     **2:56 mark**... This follows the segment around the **2:12 mark**..."*, both pulled from
     the real stored timestamps, and `sources` carried `{'timestamp': '2:56', 'start_seconds':
     176.24}` matching that exact chunk from step 2's verification. Checked the branch
     directly (not dependent on which content a live query happens to rank first): a
     document chunk (`start_seconds=None`) produces a source with exactly `{content_id,
     title}`; a video chunk (`start_seconds=307.36`) produces `{..., 'timestamp': '5:07',
     'start_seconds': 307.36}` — confirmed both directions.
4. [x] `video_moments` table + Stage 1 auto-detection (keyword/regex pass, no API cost) —
   **done, see the "Video moment highlighting" section above** (as `VideoMomentFlag`/
   `VideoMoment`, split from the single table originally sketched here).
5. [x] Weighting + promotion job on the existing RQ queue — done, same section above.
6. [x] Perceptual-hash frame diffing + vision-captioning of promoted moments only — done, same
   section above. Multiple citation chips per file also landed alongside this (superseding
   the "one source per file" limitation noted just above in step 3's evidence).
7. [x] Student flagging UI, per-student rate limits, teacher block/blocklist controls,
   click-to-seek citations — all done, same section above. No longer blocked: the player was
   replaced (see the R2 migration section below).

### Phase 6 addendum — Subtitles (2026-08-28, done and live-verified)

Reuses the existing Whisper transcription pipeline — no new transcription engine, no new API
cost. The gap this closes: `embed_content_item` already produced a raw per-segment transcript
(`[{'start','end','text'}, ...]`, ~2-8s per segment) every time it transcribed a video/audio
item, but immediately collapsed it into ~45s RAG chunks and discarded the original timing —
too coarse to ever be usable as subtitle cues.

- [x] **`transcription.transcribe_with_timestamps` now also returns the detected language**
  (`(segments, language)` instead of just `segments`) — Whisper already detects this
  per-file (`info.language`), it was just being logged and thrown away. Both call sites
  (`rag_service.py`: `transcribe_video_segments`, `_extract_drive_file_text`'s self-healing
  branch) updated to set `CourseContent.transcript_language` from it.
- [x] **New `TranscriptSegment` model** (`course_content_id`, `segment_index`,
  `start_seconds`, `end_seconds`, `text`) — persists the *original* per-segment transcript,
  kept deliberately separate from `ContentEmbedding`'s coarser RAG chunks rather than trying
  to reconstruct fine timing from them after the fact. New `lms/subtitle_service.py`
  (Flask/DB layer, mirrors `moment_service.py`'s split): `record_transcript_segments`
  (delete-and-reinsert, same idempotency pattern as `ContentEmbedding`/`VideoMomentFlag`),
  `generate_vtt` (builds a WebVTT string on the fly — no caching, it's one indexed query and
  trivial string work), `has_subtitles`. Hooked into `embed_content_item` right next to the
  Stage-1 moment-detection hook, on the same raw segment list, before it gets chunked.
  Migration `a7b8c9d0e1f2`.
- [x] **New route** `GET /api/file/c/<id>/subtitles.vtt` — same permission gate as the
  existing embed route (subtitles reveal the same spoken content the media itself would).
  Wired into `file_viewer.html` as a `<track kind="subtitles" src="..." srclang="..."
  label="..." default>` inside both the `<video>` and `<audio>` elements, only rendered when
  `has_subtitles` is true; `srclang`/`label` come from `CourseContent.transcript_language`
  ('en'/'ru', this app's two supported languages). **Same-language only** — a translated
  second subtitle track via the existing DeepL pipeline was considered and explicitly scoped
  out for this pass.
- [x] **One-time backfill** (`scripts/migration/backfill_transcript_segments.py`,
  `just backfill-subtitles`) for content transcribed before this feature existed, whose raw
  segments were already discarded — same shape as the R2/moment-promotion backfill scripts
  (dry-run, limit, course/content filters). Reuses `embed_content_item` wholesale (a full
  re-transcription via Whisper, same cost as a manual reindex) rather than a bespoke
  transcribe-only path.
- [x] **Live-verified end to end** against the real course-1 lecture (content 22, previously
  transcribed before this feature existed): dry-run correctly identified it as missing
  subtitles; the real backfill re-transcribed it (113 segments, detected language `en` —
  matching the exact segment count from this same lecture's original transcription test
  months earlier, a good consistency check that nothing regressed) and stored both the
  segments and the language; `GET .../subtitles.vtt` returned a genuinely valid, correctly-
  timed WebVTT file (`WEBVTT` header, sequential numbered cues, `HH:MM:SS.mmm --> ...`
  timestamps, real transcript text); the video viewer's rendered HTML included the `<track>`
  tag with `srclang="en"` and `label="English"` exactly as expected. Also confirmed the
  backfill's re-transcription didn't disturb the video's already-captioned visual moment
  (from the "Video moment highlighting" work above) — its `ContentEmbedding` row survived the
  same reindex run intact.
- [x] Anonymous access to the subtitle route confirmed rejected (401, `@login_required`).

### Phase 6 addendum — video player replacement, decided (2026-08-27, not yet implemented)

Full design worked out in discussion for the player-blocked pieces (step 7 above): replacing
the cross-origin Drive `/preview` iframe (`file_viewer.html:172-177`) so click-to-seek citations
and eventually student moment-flagging become possible.

**Every angle against Google's own iframe player was tried and closed, empirically, not
assumed:**
- No `postMessage` API — cross-origin, standard browser isolation, same reason `currentTime`
  can't be read.
- No start-time URL parameter — tested `?t=`, `?start=`, `#t=` against the real `/preview`
  page; a naive diff looked like a signal (10 lines changed) until a same-URL-twice control
  showed the identical 10-line diff with *zero* params involved — pure per-request nonce
  noise (Google's CSP header alone carries a fresh script-nonce every call). The literal
  parameter value never appears anywhere new in the response. Confirmed: not read, not honored.
- No API-level embed mechanism either — `embedLink` existed in Drive API v2 ("a link for
  embedding the file") but is absent from v3 (what this app uses), and even historically it
  almost certainly just returned the same `/preview` URL the UI's "Embed item" button
  generates — not a different backend with different capabilities.
- Extracting bytes from the iframe's own stream is not merely undocumented, it's structurally
  blocked by browser security (the isolation that stops any site reading another origin's
  iframe content) — confirmed via Drive's own response headers
  (`cross-origin-resource-policy: same-site`, `x-frame-options: SAMEORIGIN`).

**Superseded (2026-08-27): the hybrid direct-Drive/Flask-proxy design below, and the eventlet
switch it forced, were WITHDRAWN before implementation.** The empirical findings above (why the
Drive iframe had to go) still stand and are kept for the record. But the delivery mechanism
itself was replaced with Cloudflare R2 before any of the code below was written — see "Phase 6
addendum — Cloudflare R2 migration" further down for the actual implementation. Reason: R2
presigned URLs let the browser stream directly from Cloudflare's CDN, which removes gunicorn
from the video byte-serving path entirely — the exact problem the hybrid design and the eventlet
switch both existed to solve. The design below is kept only as a record of the road not taken
and why; do not implement it.

<details>
<summary>Withdrawn: hybrid direct-Drive/Flask-proxy design + eventlet switch (superseded by R2, see above)</summary>

Decided approach at the time: our own `<video>` element, not an iframe, with two backing
sources — small files direct to Drive's public link, large files proxied through our own
server (confirmed live: Drive's public link gates >~12.8MB behind an HTML interstitial;
the authenticated `alt=media` API serves 150MB cleanly but needs a `Bearer` token no
`<video src>` can attach, and query-param token auth is explicitly rejected by Google).
Load analysis found bandwidth was not the binding constraint (even a pessimistic 4 Mbps
lecture bitrate leaves ~10,000 views/month of headroom on Senko's 15TB cap) but gunicorn
concurrency was: `worker_class = "sync"`, `workers = 3` means 3 simultaneous video viewers
of any size exhausts 100% of the app's serving capacity for every other user. That's what
motivated switching `worker_class` to `eventlet` (chosen over `gevent` specifically because
`psycopg2` needs `eventlet`'s built-in cooperative patcher, not an added `psycogreen`
dependency, in this psycopg2/SQLAlchemy-heavy codebase) — never implemented, since R2 made
the whole proxy branch (and therefore the concurrency problem it created) unnecessary.

</details>

### Async / background-job conversion (2026-08-31, done and live-verified)

**Policy, going forward: converting a request-handler function to a background job is now
mandatory, not a future nice-to-have, whenever that function would otherwise hold one of
gunicorn's sync worker slots for real time.** `worker_class = "sync"`,
`WEB_CONCURRENCY` defaults to 3 (`deploy/gunicorn_config.py`) — a handful of concurrent slow
requests is enough to saturate the entire site for every other user, exactly the failure mode
the withdrawn eventlet design above existed to solve for video. Eventlet itself was never
adopted (superseded by R2, see above) — the actual fix, both times below, was moving the slow
work onto the existing RQ job queue + a polling endpoint, the same pattern already proven by
the translation/embedding/moment-promotion sweeps, not `async def`/an ASGI rewrite (this is a
sync WSGI app end to end).

- [x] **`POST /api/course/<id>/ask`** (`lms/routes/api.py`) — previously called
  `answer_question()` inline (a multi-second Gemini retrieval+generation chain, more under
  'thorough' effort). Now enqueues an `answer_question` job (`lms/job_manager.py`,
  `_execute_answer_question_job`) and returns `202 {job_id}` immediately; new
  `GET /api/course/<id>/ask/status/<job_id>` (ownership-checked against `user_id` in
  `job.data`, since an answer can quote private course content) is the poll side.
  `course_page_enrolled.html`'s Ask AI form now enqueues then polls every 1.5s (up to ~2 min)
  instead of awaiting one response. **Verified live** via the real Flask test client with a
  real session/CSRF: the enqueue call returned in ~2s (previously would have blocked for the
  full answer), the job correctly went `queued` → `running` → `completed` over ~70s in a
  *separate* worker process, and the final poll returned the real answer with correct
  citations (`0:00`/`1:29`/`5:07` marks on content 22, matching the same lecture used in every
  earlier Ask AI verification this session).
- [x] **Picker import** (`lms/routes/api.py`) — both the single-file and folder-tree branches
  of `_copy_drive_file_to_r2`/`_import_drive_tree` previously ran serially inline against
  gunicorn's `timeout = 600`, worst case on a folder with many files. `picker_import` now does
  only the cheap synchronous checks (course access, a token-refresh-only `authenticate()`
  fail-fast check) and enqueues `picker_import_file` or `picker_import_folder`
  (`_execute_picker_import_file_job`/`_execute_picker_import_folder_job` in
  `lms/job_manager.py`) — the Drive API `service` object can't be put in `job.data` (not
  JSON-serializable) or passed across the process boundary, so the job re-authenticates as the
  same user by id instead, the same "re-fetch models by id" convention every other job already
  follows. New `GET /api/picker-import/status/<job_id>` poll side, same ownership-check
  shape as the ask status endpoint. `course_page_enrolled.html`'s `submitPickerImport` now
  polls every 2s (up to ~8 min, since a folder import can legitimately take minutes). **Verified
  live** end to end (real Flask test client, real admin session with a real linked Google
  account): enqueue returned in 0.7s with a `job_id`; a second, non-owning user correctly got
  `404` polling that job's status (ownership check working); the job itself ran in the worker
  and correctly surfaced a real Drive API 404 (expected — the test file predates this admin
  account's `drive.file` grant, the same scope limitation documented in the Phase 4 addendum
  above) as `status: 'failed'` with the real error message intact, and no partial `CourseContent`
  row was left behind.
- [x] **Found and fixed while adding the first job whose DB write can fail mid-transaction**:
  `job_manager._execute_job`'s exception handler didn't roll back the session before calling
  `job.save()` — a failure raised mid-commit (e.g. a `CourseContent` insert hitting a
  constraint) would leave the session aborted, and `job.save()`'s own commit right after would
  then also fail, silently leaving the job stuck at `running` forever instead of recording
  `failed`. Every job type benefits from the fix (`db.session.rollback()` added right before
  `job.status = JobStatus.FAILED`), not just the two new ones — previous job types mostly
  avoided the failure mode by swallowing per-item errors before they reached this handler
  (`_execute_embed_course_job`'s per-item `try/except: continue`), so it hadn't been hit yet.

**RAG downloads in the worker** (the third item originally flagged here) are already
background-job work by construction — `embed_content_item` only ever runs inside the embedding
sweep/reindex jobs, never inline in a request — so there was nothing to convert there; that
bullet in the original note was describing where the slow work already lived, not a gap.

If eventlet is ever revisited for a different reason, the previously-found caveat still
applies: a documented eventlet issue affects its psycopg2 patcher specifically over
TLS-encrypted Postgres connections — likely moot here (DB traffic runs over the private Docker
network, not TLS) but confirm live, don't assume.

**Known, pre-existing gap — deliberately not fixed by the R2 work below**: none of the four
content-serving routes in `lms/routes/api.py` (`serve_file`, `serve_content_by_db_id`,
`serve_content_embed`, `download_content_by_db_id`) call `get_locked_content_ids()`
(`lms/rag_service.py`), so a student can open a folder-locked file directly by URL even though
Ask AI already refuses to cite it (`answer_question` does check it). Not introduced or widened
by the R2 migration — logged here for a future dedicated fix, shape: one shared gate helper
called from all four routes.

**Structured-citation-syntax problem — still open, separate from what R2 solved.** Linking a
model-mentioned timestamp in free prose back to a specific `content_id`/moment inline (so an
individual mid-sentence mention becomes clickable exactly where the model wrote it) is still
unsolved — parsing natural-language phrasing was explicitly ruled out as unreliable, and no
structured syntax has been designed. What *is* solved (see the R2 addendum's multi-moment
citations): the `sources` list itself now surfaces multiple distinct moments per file as
separate chips, which covers the reported bug (several moments mentioned, only one was
clickable) without needing inline prose parsing.

### Phase 6 addendum — Cloudflare R2 migration (2026-08-27, done and live-verified)

Full plan in `/home/alhiko56/.claude/plans/modular-sniffing-wren.md`. Moves course-content
storage off Google Drive onto Cloudflare R2 (S3-compatible, presigned URLs, always-free egress),
replaces the Drive `/preview` iframe with a real `<video>` element, and fixes the multi-moment
citation bug. All code written, `uv run ruff check` clean, and live-verified end to end against
a real R2 bucket (see the verification item below for exact evidence).

**One real bug caught and fixed during live verification**: `serve_content_by_db_id`'s
mime-based file-type classifier originally set `file_type = 'video'` for *any* row with
`content_type == 'video'` regardless of the actual sniffed MIME — since `content_type='video'`
covers both video **and** audio (see `content_type_for_mime`), every R2-backed audio upload
rendered the `<video>` branch instead of the `<audio>` branch. Fixed to branch on
`file_mime_type.startswith('video/'|'audio/')` directly. Caught by an actual end-to-end test
(uploaded a real WAV, rendered the viewer, saw the wrong branch) — not by inspection.

Scope decided: **all** course-content uploads move to R2 (direct uploads and Picker imports,
every content type, not just video) — this retires Drive as course-content storage, not just a
video-only fix. Existing Drive-hosted content is backfilled too. No eventlet switch (see above —
its motivation is gone). Multi-chip citations, not inline prose parsing. Google-native
Docs/Sheets/Slides on Picker import are skipped with a message, not exported. PDF viewer
regression (native browser viewer exposes download/print, unlike Drive's `/preview`) accepted
as-is. Locked-content authorization gap deliberately deferred (see above).

- [x] **Schema**: `CourseContent.r2_key`/`file_mime_type` (nullable, additive), `has_bytes`/
  `storage_backend` properties. Migration `d4e5f6a7b8c9`, applied and confirmed live via `\d
  course_content`. `drive_file_id` is never cleared — kept as provenance/rollback even after a
  row is migrated; R2 wins whenever both are set.
- [x] **`lms/r2_client.py`** (new): boto3 S3-compatible client against R2's endpoint,
  `build_content_key`/`upload_file`/`download_file`/`generate_presigned_url`/`delete_object`/
  `object_exists`/`get_object_size`. Includes an optional read-only "upstream" client
  (`R2_UPSTREAM_*`) so dev can play back media pulled in via `just db-pull-staging`/production
  even when the object only exists in the production bucket.
- [x] **Upload path** (`lms/routes/__init__.py`): direct uploads now go straight to R2, no
  Google Drive credential needed at all (a real simplification — previously required a linked
  Google account just to upload a course file). Staging cleanup consolidated into one
  `try/finally`.
- [x] **Picker import** (`lms/routes/api.py`): both the single-file and recursive-folder
  branches now download the selected Drive file's bytes and copy them into R2
  (`_copy_drive_file_to_r2`) instead of just referencing them in place — stops mutating the
  teacher's Drive sharing settings entirely (no more `set_file_permissions(make_public=True)`),
  a privacy improvement. Google-native Docs/Sheets/Slides are skipped with a clear per-file
  message. `google_drive_service.download_file` gained the same `resource_key` support
  `get_file_metadata` already had, needed for link-shared files.
- [x] **Serving routes** (`lms/routes/api.py`): new `_content_media_url` helper resolves R2
  (presigned URL) or Drive (today's extension-based URL) per item, so unmigrated rows keep
  working unchanged during an incremental backfill. `serve_content_embed` sets
  `Cache-Control: private, no-store` so an expired presigned URL can't be replayed from
  bfcache. `serve_content_by_db_id` now also classifies file type from the sniffed
  `file_mime_type` when available, and parses/validates a new `?t=<seconds>` query param for
  click-to-seek.
- [x] **RAG pipeline** (`lms/rag_service.py`): new `_download_content_bytes` dispatches to R2
  or Drive; `extract_text_for_content`'s gates changed from `drive_file_id` truthiness to
  `content.has_bytes`. No re-embedding needed for migrated content — bytes are identical, so
  existing `ContentEmbedding` rows (including `start_seconds`) stay valid.
- [x] **Multi-moment citations** (`lms/rag_service.py`, `answer_question`): a file can now earn
  several citation chips — one per distinct moment actually cited — instead of collapsing to
  its single best-matching chunk. A new timed chunk becomes its own source only if it's more
  than `SEGMENT_CHUNK_WINDOW_SECONDS` (45s) from every moment already emitted for that file.
  Sources sort so multiple moments in one file read chronologically.
- [x] **Click-to-seek** (`course_page_enrolled.html`, `file_viewer.html`): citation chips link
  to `?t=<start_seconds>`; the video branch is now a real `<video>` element (not an iframe);
  new seek script reads the server-validated `start_seconds`, seeks on `loadedmetadata` (or
  immediately if metadata is already cached, covering a warm-reload race), and shows a
  friendly message if the presigned URL has expired. Audio's hardcoded `type="audio/mpeg"`
  fixed too (was wrong for non-MP3 uploads) by omitting the `type` hint entirely — same
  technique, lets the browser trust R2's actual stored Content-Type.
- [x] **One-time backfill** (`scripts/migration/backfill_drive_to_r2.py`, `just backfill-r2`):
  run for real against the dev DB's entire Drive-hosted corpus (4 rows: 1 video, 3 documents).
  `--dry-run` listed all 4 correctly; the real run migrated all 4 (`Done: 4 migrated, 0 failed`
  across two invocations); re-running afterward reports `0 row(s) to migrate` — confirmed
  idempotent. The 12.8MB lecture video correctly triggered boto3's multipart upload path
  (2 parts, confirmed via `x-amz-mp-parts-count: 2` on the object) with no code changes needed.
  `drive_file_id` retained on every row post-migration, `embedded_at`/`ContentEmbedding` rows
  untouched (self-heal branch correctly did not fire — the row was already `content_type='video'`).
- [x] **Live end-to-end verification** — done against a real Cloudflare R2 bucket. Evidence:
  - R2 client smoke test (upload/exists/presign/delete against a throwaway object) passed.
  - Real upload of a synthetic audio file and a synthetic video file through the actual
    `/course/<id>` POST route (Flask test client, real session, real DB, real R2 — not mocked):
    both created correct `CourseContent` rows (`r2_key`, `file_mime_type`, `drive_file_id=None`),
    left the upload staging directory empty afterward, and were fully cleaned up via
    `delete_content` (confirmed both the DB row and the R2 object were gone after delete).
  - `serve_content_embed` 302s to a presigned URL with `Cache-Control: private, no-store`.
  - **Range/206 confirmed working** on presigned URLs for both a synthetic file and the real
    12.8MB migrated lecture — `curl -r 0-100` returns `206` with a correct `Content-Range`
    header in every case. Note: `curl -I` (HEAD) against a presigned GET URL returns a
    misleading `403` on R2 — SigV4 presigned URLs are signed per-HTTP-method, and R2 enforces
    that strictly (unlike some S3 implementations). Not a bug: real `<video>`/Range requests are
    always GET, never HEAD, so this only affects how you manually test a presigned URL with
    curl — use `curl -D -` (a real GET), not `curl -I`.
  - **Multi-moment citations confirmed with a real live Gemini call**: asked Ask AI a question
    spanning two topics >45s apart in the same real transcribed lecture (content id 22, "Test
    video - transcribing") and got back three distinct source entries for that one file
    (`0:44`, `2:12`, `3:39`) instead of one — the exact bug originally reported, fixed and
    observed live. Re-ran the identical question after migrating that same content to R2 and
    got byte-identical citations, confirming existing embeddings survive a backfill unchanged.
  - Click-to-seek: `/api/file/c/<id>?t=42` renders the `<video>` element with
    `var seekTo = 42.0;` correctly emitted server-side.
  - **Not independently verified**: the actual browser-side scrub-bar/playback experience (all
    of the above was verified via `curl`/Flask test client/direct R2 API calls, not a real
    browser), the full Picker-import flow (needs live Google OAuth + a real Picker session,
    can't be automated from here), and the `R2_UPSTREAM_*` dev/prod-bucket fallback (no
    production bucket exists yet to fall back to).

**Follow-on bug found and fixed after the above (2026-08-27): Office documents (.docx/.pptx/
.xls/.xlsx and legacy .doc/.ppt) were invisible in the viewer.** Not caught by the verification
above because it only checked the document iframe returned HTTP 200, not that the browser could
actually render what came back. Root cause: Google Drive's `/preview` used to convert the file
server-side before returning it; raw R2 bytes have no equivalent, and browsers have no native
renderer for Office formats (unlike PDF/images, which render fine raw). Fix: headless LibreOffice
converts these to PDF at ingestion time and the converted PDF is what gets embedded — the
original file is untouched and still what downloads/RAG extraction use.
- New `lms/office_preview.py` (`OFFICE_MIME_TYPES`, `convert_to_pdf`, `generate_and_upload_preview`
  — the last one shared by all three ingestion paths below).
- New `CourseContent.r2_preview_key` column (migration `e5f6a7b8c9d0`, nullable, additive) —
  NULL means "the original is natively viewable, embed it directly"; set means "embed this PDF
  instead." `_content_media_url` in `lms/routes/api.py` prefers it for embedding only, never
  for downloads.
- Wired into all three places bytes enter R2: the direct upload route, Picker import
  (`_copy_drive_file_to_r2`, return signature grew a third element), and the backfill script.
- New Dockerfile layer: `libreoffice-writer libreoffice-calc libreoffice-impress`
  (`--no-install-recommends`, not the full `libreoffice` metapackage) — needed in every image
  that can receive an upload/import/backfill, i.e. `app`/`worker` for all three environments,
  since they all build from the same Dockerfile.
- **Live-verified**: converted a real migrated `.docx` (the "CV Magsud Abbaszade.docx" from the
  earlier backfill) via the actual LibreOffice binary in the container — produced a genuine,
  valid PDF (`file` confirms `PDF document, version 1.7`), uploaded it, and confirmed
  `serve_content_embed` now redirects to the `.preview.pdf` object (`Content-Type:
  application/pdf`) instead of the raw `.docx`. Ran a full upload through the real route with a
  LibreOffice-generated test `.docx` and confirmed the preview auto-generates.
- **One test-only wrinkle, not a real-user bug**: a `.docx` generated directly via the
  `python-docx` library (used for a quick synthetic test upload) sniffed as `application/zip`
  via `filetype.guess()`, not as the Word MIME type — `python-docx`'s minimal zip-entry
  ordering doesn't match what `filetype`'s OOXML heuristic expects. Confirmed this is specific
  to that library, not a general problem: both a real-world Word-produced `.docx` and a
  LibreOffice-produced `.docx` sniff correctly. Falls back gracefully anyway (classified
  `file_type='unsupported'`, shows "Preview Not Available" rather than a blank/broken iframe).
  Not fixed — real user uploads (from Word, LibreOffice, Google Docs export, etc.) are
  unaffected.
- **Not yet backfilled**: existing migrated content from before this fix doesn't get a preview
  retroactively unless the backfill script is re-run — but the backfill's selection query only
  picks up rows with `r2_key IS NULL`, so already-migrated rows are skipped. Manually generated
  previews for the two currently-migrated `.docx` rows (ids 19, 20) as a one-off using the same
  `generate_and_upload_preview` function the real ingestion paths call, and confirmed both now
  embed correctly. A proper reusable "regenerate previews for rows missing one" script doesn't
  exist yet — worth adding if more content accumulates from before this fix.

**New known gaps, worth recording while fresh**: presigned URLs are shareable by anyone holding
one for its remaining lifetime (`R2_URL_EXPIRY_SECONDS`, default 6h, is the only control);
replaced/orphaned R2 objects (a re-uploaded file's old object) have no reaper script yet; Drive
copies are intentionally retained post-backfill, purging them is a separate deliberate future
step. **`CourseAssignmentSubmission`/`PDFDocument` uploads were "intentionally still on Drive,
out of this migration's scope" at the time this was written — no longer true, see the
2026-08-31 addendum immediately below.** `import_drive_folder`/`import_drive_file` in
`google_drive_service.py` were noted here as pre-existing dead/legacy code, not touched since
removing them wasn't part of this plan — since deleted, see the Phase 4 leftover-cleanup
addendum further down (2026-08-31), which found they'd become *fully* dead (not just unused
outside each other) once `_import_drive_tree` stopped calling them.

### Phase 6 addendum — R2 migration extended to submissions and PDFDocument (2026-08-31, done and live-verified)

**Superseded in part — see "PDFDocument removed entirely" further below.** Everything in this
section about `PDFDocument` (migrating it to R2, the new `/api/file/p/<id>` route, its half of
the backfill script) describes real work that landed and was live-verified, then was itself
removed a short time later the same day once the user, after hearing the "zero reachable UI"
finding explained in full, decided the feature should just be deleted rather than kept around
unreachable. Left as-is below for the historical record rather than rewritten — the
`CourseAssignmentSubmission` portions of this section are all still current.

Closes the gap the R2 migration addendum above explicitly left open. `CourseContent` was R2
from that earlier pass; `CourseAssignmentSubmission` (assignment uploads) and `PDFDocument`
(the PIN-gated PDF sharing feature) were still 100% Drive-dependent until now. Same schema
shape as `CourseContent`'s migration (`r2_key`/`file_mime_type`, plus `r2_preview_key` for
submissions only — `PDFDocument` is PDF-only by construction, per `upload_pdf`'s
`expected_mimes=PDF_MIME_TYPES`, so it never needs the Office-to-PDF conversion). Migration
`b8c9d0e1f2a3`. `drive_file_id`/`drive_view_link` kept on both, provenance-only once `r2_key`
is set — same convention as `CourseContent`.

- [x] **Real, live security bug found and fixed along the way, not introduced by this
  pass**: `upload_pdf` (`lms/routes/api.py`) staged uploads at
  `os.path.join(current_app.static_folder, 'temp')` — the exact same unauthenticated-exposure
  class already found and fixed for course-content/assignment uploads earlier this session
  (`UPLOAD_STAGING_DIR`, moved outside the static root) — but this one call site was missed by
  that earlier sweep. Any PDF uploaded through this route was briefly served completely
  unauthenticated at `/static/temp/<name>` for as long as the (now-removed) Drive upload took.
  Fixed as a natural side effect of moving this path to R2 (which needed `UPLOAD_STAGING_DIR`
  anyway) — confirmed live: `static/temp/` has zero files after a real PDF upload through the
  actual route.
- [x] **Real finding: `PDFDocument` has zero reachable UI anywhere in the app right now.**
  Its only frontend is markup inside `index.html`, and `index.html` is rendered by zero
  routes — confirmed by grepping every route handler for `render_template('index.html'`
  (no hits) after the earlier MoxoTest cleanup removed the `/moxo-test` route that used to be
  the only thing still rendering it. No admin panel exposure either. **Explicitly discussed with
  the user before proceeding** (not assumed): decided to migrate the feature to R2 and keep it
  intact rather than deleting it or leaving it Drive-only, since it's real, working backend
  functionality with just a missing frontend — reviving it with an actual UI is separate,
  unscheduled future work.
- [x] **`upload_pdf`'s Drive-account gate removed** (`if not current_user.google_access_token:
  return ... 403`) — made no sense once the route no longer touches Drive at all; would have
  needlessly blocked an admin with no linked Google account from uploading a PDF.
- [x] New DB-id-keyed serving routes, mirroring `serve_content_by_db_id`'s reason for existing:
  `GET /api/file/s/<int:submission_id>` and `GET /api/file/p/<int:pdf_id>`. Needed because the
  legacy `serve_file(file_id)` route is keyed by `drive_file_id` in the URL — an R2-only row
  (no Drive file at all) has nothing to put there. New shared `_r2_or_drive_media_url()`
  helper factors out the R2-vs-Drive precedence both routes need (same precedence
  `_content_media_url` already uses for `CourseContent`). `course_page_enrolled.html`'s two
  "View Submission"/"View Your Submission" links updated from `/api/file/{{ …drive_file_id }}`
  to `/api/file/s/{{ …id }}`; `serve_file` itself untouched, kept for any still-Drive-only
  legacy row.
  - **Pre-existing permission behavior preserved, not tightened or loosened**: both new routes
    keep the same "any authenticated user can view a `allow_others_to_view=True` file, not just
    enrolled classmates or the PIN holder" behavior `serve_file` already had for these two
    models — flagged in code comments as a pre-existing gap, not fixed here (PDFDocument's
    `access_pin` in particular is not enforced by the serving route at all, and never was).
- [x] **`submit_assignment`, `delete_submission`, `toggle_submission_visibility`
  (`lms/routes/__init__.py`) rewritten for R2** — upload now goes straight to R2 (no Drive
  credential needed at all, matching the simplification the original `CourseContent` upload
  path already got), with the same "clean up the object being superseded" logic on resubmission
  that `delete_content` already used; `toggle_submission_visibility` gained the same
  `not submission.r2_key` guard `toggle_content_visibility` got in the Phase 4 leftover-cleanup
  pass, so it doesn't reach out to Drive for the (now-provenance-only) `drive_file_id` on an
  R2-migrated row.
- [x] **`upload_pdf`, `delete_pdf` (`lms/routes/api.py`, `lms/routes/__init__.py`) rewritten
  the same way** — R2 upload, R2 cleanup on delete, Drive-permission calls now gated to
  genuinely-still-Drive-hosted legacy rows only.
- [x] New backfill script `scripts/migration/backfill_submissions_pdfs_to_r2.py`
  (`just backfill-submissions-pdfs`), same idempotent/resumable shape as
  `backfill_drive_to_r2.py`. Needed two different download strategies, unlike `CourseContent`
  (always public): `CourseAssignmentSubmission` rows were always made Drive-public
  (`set_file_permissions(..., make_public=True)` in the old upload path), so they download the
  same way `CourseContent` does, over the public link; `PDFDocument` rows were **never** made
  public (`create_view_only_link` only ever built a URL string, never touched a permission —
  confirmed by reading it), so they need an authenticated `download_file()` call instead. No
  existing rows in either table in dev to actually exercise this against (both were empty) —
  the script exists for whenever this ships somewhere with real data.
- [x] **Live-verified end to end** (real Flask test client, real sessions, real R2 bucket, no
  mocks): submitted a real assignment as `testuser` → row created with `r2_key` set and
  `drive_file_id` NULL, real R2 object confirmed to exist, correct sniffed
  `file_mime_type='application/pdf'`; viewed it via the new `/api/file/s/<id>` route → real 302
  to a genuine R2 presigned URL; resubmitted → confirmed the old R2 object was deleted and a
  new one created; toggled visibility → no error, no Drive call attempted; deleted the
  submission → both the DB row and the R2 object confirmed gone. Same full cycle repeated for
  `PDFDocument` as `admin`: upload (201, real R2 object, correct mime), view via
  `/api/file/p/<id>` (302 to a real presigned URL), delete (row and object both confirmed
  gone) — and confirmed zero files left behind in `static/temp/`, closing the security finding
  above.

**Document storage was R2-first across all three models at this point** (`CourseContent`,
`CourseAssignmentSubmission`, `PDFDocument`) — see below for `PDFDocument`'s subsequent removal.

### Phase 6 addendum — PDFDocument removed entirely (2026-08-31, done and live-verified)

Follow-up to the "zero reachable UI" finding two sections above. Once the user understood the
finding in full — `PDFDocument`'s only frontend (`index.html`) is rendered by zero routes,
confirmed by grep, not just "hard to find" — they asked for the feature to be removed outright
rather than kept alive with no way to reach it. Reversed the earlier migrate-and-keep decision
from the same day.

- [x] Model deleted (`lms/models/__init__.py`) and its re-export dropped
  (`lms/__init__.py`).
- [x] All routes deleted: `GET /api/pdfs`, `POST /api/pdfs/upload`, `GET /api/file/p/<id>`
  (`lms/routes/api.py`), the `delete_pdf` form action (`lms/routes/__init__.py`). `serve_file`'s
  three-model lookup (`submission or course_content or pdf_doc`) trimmed back to two.
  `_r2_or_drive_media_url()`'s docstring corrected to describe its one remaining caller
  (`CourseAssignmentSubmission`) rather than two.
- [x] `PDF_MIME_TYPES` (`lms/upload_validation.py`) deleted — it had exactly one caller,
  `upload_pdf`, which is now gone.
- [x] GDPR data export (`lms/data_export.py`, `export_user_data`) — dropped the `uploaded_pdfs`
  key and its `PDFDocument` import. Verified live: `export_user_data()` still runs cleanly and
  returns every other section unchanged.
- [x] Migration `c9d0e1f2a3b4` drops the `pdf_document` table outright — the first genuinely
  destructive migration in this chain (every other one so far has been additive/nullable).
  Explicitly documented in the migration's own docstring as unsafe to run against a database
  with real rows in that table without exporting them first; the dev database's table was
  confirmed empty before dropping it, so nothing was actually lost here. `downgrade()` restores
  the empty schema only, not data.
- [x] The backfill script from the section above split back apart:
  `backfill_submissions_pdfs_to_r2.py` deleted, replaced by
  `scripts/migration/backfill_submissions_to_r2.py` (`just backfill-submissions`, renamed from
  `backfill-submissions-pdfs`) — submission-only now, since there's nothing left to backfill
  `PDFDocument` into.
- [x] **Live-verified**: app boots clean post-removal (150 routes, down from 153 — the three
  deleted PDF routes), `uv run ruff check` clean across every touched file, `GET /api/pdfs` and
  `POST /api/pdfs/upload` both confirmed `404` through the real running app, `export_user_data()`
  confirmed still working with the `uploaded_pdfs` key genuinely gone (not just empty), and the
  renamed backfill script's `--dry-run` confirmed running cleanly against the real dev database.

**What was left before Drive could be called fully removed** — the worker-account/Drive-Writer
OAuth machinery and the Picker-import-from-Drive feature — is addressed by the section
immediately below.

### Phase 6 addendum — Picker import removed, replaced with async multi-file upload (2026-08-31, done and live-verified)

Follow-up to the section above's open question. Discussed with the user: keep Picker import
(it only ever ingests, doesn't store, so it didn't conflict with "Drive is no longer used for
storage") vs. remove it too and go Drive-free for course-content ingestion entirely. User chose
removal — Picker import's real value was letting a teacher bulk-import many files without
selecting them one at a time; asked whether folder-structure recreation specifically mattered
enough to rebuild that capability a different way (e.g. directory upload preserving relative
paths, or ZIP upload with server-side extraction) — decided **no**, drop the
folder-structure-recreation feature and keep it simple: multi-file upload, flat, no subfolders
recreated.

- [x] **Picker import backend deleted wholesale**: `GET /api/drive-picker-token`, `POST
  /api/picker-import`, `GET /api/picker-import/status/<job_id>` (`lms/routes/api.py`);
  `_copy_drive_file_to_r2()`/`_import_drive_tree()` helper functions; the `picker_import_file`/
  `picker_import_folder` job types and their execution functions (`lms/job_manager.py`).
  `collect_folder_structure()`/`list_folder_contents()` (`lms/google_drive_service.py`) also
  deleted — confirmed dead once `_import_drive_tree` (their only caller) was gone.
- [x] **Old synchronous single-file `upload_file` form action deleted too**
  (`lms/routes/__init__.py`) — replaced outright by the new async route below rather than kept
  running alongside it, so there's one upload path instead of two.
- [x] **New async multi-file upload**: `POST /api/course/<id>/upload-content` +
  `GET /api/course/<id>/upload-content/status/<job_id>` (`lms/routes/api.py`), new
  `bulk_upload_content` job type (`_execute_bulk_upload_content_job`, `lms/job_manager.py`).
  Files are validated and staged to `UPLOAD_STAGING_DIR` synchronously (cheap — disk writes
  only, no network I/O), then a single job uploads each to R2 (+ LibreOffice preview
  generation where applicable) and creates its `CourseContent` row, so N files each
  potentially needing a slow upload/conversion can't hold a gunicorn worker for real time —
  the same "mandatory for anything that would otherwise block a slot" policy from this
  session's earlier async conversion work. **Deliberately flat**: every file lands directly in
  the chosen target folder; no subfolder structure is recreated (Picker's old folder import
  used to do that). Title handling: a single file uses the shared Title field if one was
  given, otherwise (or for multiple files) each file's own original filename is used —
  matching the convention Picker import itself already used. The whole batch is validated
  before anything is staged, so one bad file 400s the request with nothing uploaded, rather
  than a partial batch.
  - Status-poll ownership check differs deliberately from the Ask AI/Picker-import status
    endpoints: those check the exact requesting `user_id` (an AI answer or an import is
    personal), this one checks `course.is_managed_by(current_user)` — any teacher/admin
    managing the course can check an upload's status, not just whoever clicked upload,
    matching how every other course-content action in this app is gated.
- [x] **Frontend**: the "Import from Drive" button and its modal deleted; the "Upload File"
  modal reworked into "Upload Files" — `multiple` on the file input, Title field now optional
  (used only for a single-file upload), submission converted from a native form POST to a
  `fetch()`-based enqueue-then-poll flow (`course_page_enrolled.html`), mirroring the pattern
  already established for Ask AI and the (now-removed) Picker import. The Google Picker
  `<script>` tag, `gapi`/`google.picker` calls, and the `.picker-dialog`/`.picker-dialog-bg`
  z-index CSS overrides all removed as dead weight alongside it.
- [x] **Now-unused config removed**: `GOOGLE_API_KEY`/`GOOGLE_APP_ID` (`lms/config.py`) —
  Picker-specific, nothing else read them (confirmed by grep before removing).
- [x] **Live-verified end to end** (real Flask test client, real admin session, real R2
  bucket): a real 2-file batch upload (one PDF, one PNG) enqueued in 0.15s, the job correctly
  went `queued` → `running` → `completed`, both `CourseContent` rows were created with real R2
  objects and correctly sniffed MIME types, titled by their own filenames (no shared title
  given); a single-file upload with a shared Title correctly used that title instead of the
  filename; a 2-file batch with one deliberately invalid file correctly rejected the whole
  batch with `400` and created zero rows (confirmed via a before/after count); a non-managing
  user correctly got `404` polling another course's upload job status. App boots clean at 149
  routes (down from 150), zero Picker-related strings anywhere in the codebase (`grep`
  confirmed), `ruff` clean across every touched file.

**Drive dependency status after this**: no active code path in the app requires a working
Drive connection for anything to function — every ingestion path (direct upload, multi-file
upload, assignment submissions) is R2-only now. What remains is dormant, not active: the
`and not r2_key`-guarded legacy-Drive-cleanup branches in `delete_content`/
`toggle_content_visibility`/`delete_submission`/`toggle_submission_visibility` (only fire for
rows that predate this app's R2-only ingestion paths), the worker-account/Drive-Writer OAuth
admin panels (`Admin → Drive Writer`/`Admin → Drive Worker`) and `link_google_account` (still
present, nothing requires them to be connected anymore), and a separately-noticed, likely-dead
"Sign in with Google" account-creation flow (`auth.google_callback`) that has no button linking
to it anywhere in the current templates — unrelated to this task, not investigated further,
worth a look sometime the way `PDFDocument` was. Retiring any of that admin/legacy surface is
optional cleanup, not required for correctness — flagged for whenever it's wanted, not decided
unilaterally here.

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

- [x] **Fixed — reported live by the user, not caught by the earlier test-gap note.**
  `answer_question()` filtered `course_id`, `is_published`, and locked folders, but never
  `allow_others_to_view` — the exact flag the rest of the app already enforces consistently
  (folder-contents endpoint at `api.py:1125`, file-serving gate at `api.py:745`: students see
  only `allow_others_to_view=True`, course managers see everything). Ask AI was the one path
  that skipped it, so a student could ask about — and receive answers quoting — a teacher's
  "🔒 Private" content. Confirmed on the user's exact real-world case: `testuser`, a plain
  student (`is_teacher=False`) enrolled in course 1, which has two private items (`terms of
  use`, the private planning doc). Retrieval scoped to `allow_others_to_view=True` no longer
  returns either, for a query aimed directly at the private one. Fix:
  `if not course.is_managed_by(user): query.filter(CourseContent.allow_others_to_view.is_(True))`
  in `rag_service.answer_question`, matching the same rule the rest of the app already uses.
  The unrelated "can't ask about a course you're not enrolled in" behavior the user separately
  confirmed working is unchanged — that's the existing `course_id` scoping, untouched here.
- [x] **Quiz/assignment folder-locking verified — the other half of the test gap, closed.**
  `get_locked_content_ids()` was already wired into `answer_question()`'s query
  (`~CourseContent.id.in_(locked_ids)`) before this session touched it; it had simply never
  been exercised end-to-end. Live test: a throwaway quiz, a folder with
  `locked_until_quiz_id` set to it, and a planted secret inside. Called the real
  `answer_question()` (not a reconstruction) as a student who had not passed — answer
  correctly said it had no information, nothing from the locked item appeared in `sources`.
  Recorded a `QuizAttempt(passed=True)` for the same student, called it again — the secret
  was correctly surfaced and cited. Both directions confirmed via production code, not
  inspection; probe rows (quiz, folder, content, embedding, attempt) deleted after.

## Phase 7 — AI audio overview

**Resolved 2026-09-01 — already done, as of Phase 6, no new work needed.** The original
wording here ("single-narrator spoken summary + TTS step... requires ElevenLabs") described
generating brand-new spoken audio from text — a NotebookLM-style podcast feature. That's a
literal reading that turned out not to match the actual intent: "audio overview" meant
treating an *uploaded audio file* the same way video is already treated — transcribed and made
searchable/citable through Ask AI — not synthesizing new narration.

That was already built. Verified by re-reading `rag_service.py`: `extract_text_for_content()`
routes any `content_type='video'` item through `transcribe_video_segments()`, and that
function's mime check explicitly accepts `audio/*` alongside `video/*` — same Whisper
transcription, same timestamped chunks, same `ContentEmbedding` rows, same Ask AI citations.
There's even a self-healing branch (`_extract_drive_file_text`) that catches an audio file
mis-typed as `content_type='file'` and transcribes it anyway. Confirmed live for the video
case (a real test video has 10 embedded chunks); no real standalone audio file exists in the
dev DB yet to click through the identical path with, but it's the same code, not a parallel
implementation that could drift.

A short-lived attempt was made to build the literal TTS-podcast reading of this phase
(`CourseAudioOverview` model/migration, `lms/elevenlabs_client.py`,
`lms/audio_overview_service.py`, a `generate_audio_overview` job type, 4 new routes, a new
course-page tab) before this was caught and corrected — fully reverted (migration downgraded
and deleted, all new files removed, all call sites/UI stripped back out), confirmed via `grep`
returning zero remaining references and a clean app boot (165 routes, `200` on `/`) afterward.
Also surfaced along the way, for whoever revisits real TTS narration later: ElevenLabs' free
tier returns `402 Payment Required` ("Free users cannot use library voices via the API") for
any of the premade/shared voices — only a voice already in the account's own "My Voices" works
on the free API tier, which may mean this specific approach needs a paid plan regardless of
which SDK/library wraps it.

## Phase 8 — Office file preview

- [x] **Word/PDF/PowerPoint → LibreOffice conversion to PDF + iframe.** Turned out already
  done, from earlier work (`lms/office_preview.py`, wired into both `job_manager.py`'s bulk
  upload and `routes/__init__.py`'s submission upload) — confirmed live via two real `.docx`
  rows in the dev DB with a genuine generated `r2_preview_key` PDF each.
- [x] **Excel → interactive table (SheetJS), done 2026-09-01.** Univer was evaluated and
  dropped: its own docs say full-fidelity frontend-only import may need Univer's own backend
  service, and two official doc pages gave two different method names for the same
  operation — too unreliable to build against without hands-on access to a working example.
  Went with SheetJS alone instead (stable, MIT-licensed, well-documented): `.xls`/`.xlsx` now
  get a distinct `file_type='spreadsheet'` in `file_viewer.html` — tabs per sheet, each
  rendered as a real scrollable HTML table (`XLSX.utils.sheet_to_html`) — instead of the flat
  PDF snapshot every other Office format gets. Not a full spreadsheet app (no cell
  editing/formulas UI), but shows real cell values, not a flattened image.
  - New `_content_media_url(..., raw=True)` / `/api/file/c/<id>/embed?raw=1` bypasses the
    Office-preview-PDF substitution so the viewer can fetch the actual `.xlsx` bytes
    client-side instead of a converted PDF.
  - **Real bug caught only by browser testing, not curl/test-client**: the viewer's `fetch()`
    call (needed to get an ArrayBuffer for SheetJS) hit a CORS block — the Cloudflare Worker
    file-proxy (see Phase 7-adjacent security work above) never sent
    `Access-Control-Allow-Origin`, which `<img>/<iframe>/<video> src` embeds never need but a
    same-page `fetch()` reading a cross-origin response does. Fixed by adding permissive CORS
    headers to every Worker response (`workers/file-proxy/src/index.js`) — safe here since the
    URL's own HMAC signature + ~60s expiry is the real access control, not the requesting
    origin.
  - Added `just deploy-worker` (reads `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` from
    `.env` via `just`'s existing dotenv-load) so redeploying the Worker after an edit is one
    command instead of a manual `export`+`wrangler deploy` dance — needed repeatedly during
    this same session.
  - **Verified live with a real Playwright browser** (not just HTTP-level checks): logged in
    as a real admin, uploaded a real 2-sheet `.xlsx` (openpyxl-generated, real data), loaded
    the viewer page, confirmed both sheet tabs render, confirmed the active tab's table
    contains the real cell values (`Alice`, `92`, etc.), confirmed switching tabs correctly
    swaps the rendered table, and confirmed via screenshot the page looks correct. Test
    content/R2 object deleted afterward.

### Phase 8 addendum — real Excel upload failure, root-caused (2026-09-01)

User reported a real `.xlsx` upload failing through the actual app UI (not my test scripts).
Root cause was **pre-existing, unrelated to the SheetJS work above** — a latent bug in the
async `bulk_upload_content` job (built earlier, part of the R2/async-conversion work), that
just happened to surface now: `upload_course_content` (`routes/api.py`) staged the file and
recorded its **absolute path** in the job's `data`, which a worker in a different process
reads back later. `just dev` (host process) resolves `UPLOAD_STAGING_DIR` to a real host path;
Docker's `worker-dev` (the only worker actually running, connected to the same shared Redis
queue per this app's documented dual-server setup) resolves it to `/app/data/upload-staging`
— same bind-mounted directory underneath, but a different path *string*, so a path baked in by
one side is meaningless to the other. Whichever side didn't stage the file got
`FileNotFoundError` → `staged file missing`. This wasn't Excel-specific — it would hit **any**
bulk upload through `:5000` while Docker's worker is the one consuming the queue.

Fixed by storing just the filename in job data (not a full path) and having the job resolve
it against its own local `UPLOAD_STAGING_DIR` at read time (`_execute_bulk_upload_content_job`,
`job_manager.py`) — portable regardless of which process staged vs. consumes it. Verified live
end-to-end with a real Playwright browser session against the actual `:5000` `just dev` server
(reproducing the exact failure conditions): real login, real multipart upload, job queued,
Docker's `worker-dev` picked it up and completed it successfully (`created: 1, failed: 0`).
Cleaned up the two stale failed `BackgroundJob` rows and orphaned staged files left over from
the original failed attempts.

### Phase 8 addendum — full Excel visual formatting (2026-09-01)

User asked for visual formatting (colors/bold/alignment) on top of the plain table above.
Two paid dead ends investigated and ruled out first: (1) Univer, already ruled out in the main
Phase 8 entry above; (2) Microsoft/Google's free online document viewers (`view.officeapps.live.com`
et al.) would give perfect native rendering for free, but their own documentation confirms they
**cache document content on the provider's servers for days** regardless of URL — a real privacy
regression for private course material, directly against the point of this session's earlier
signed-URL security work. Ruled out on that basis, not effort.

Landed on a fully client-side, free, zero-server-cost approach instead: SheetJS's `cellStyles:
true` only exposes cell **fill color** (confirmed by inspecting its actual parsed output
directly — its own docs describe a `{fill:{fgColor}}`/`{font:{...}}` shape that turned out not
to match reality; font bold/italic/color and alignment are silently absent even when the file
has them, full style rendering being SheetJS Pro). Recovered the rest by separately unzipping
the same `.xlsx` with JSZip (free, MIT, no server round-trip) and reading `xl/styles.xml` +
each worksheet's raw per-cell style index directly — verified against a real generated file's
actual XML before writing any parsing code, not assumed from docs. Sheet-name-to-XML-file
resolution goes through `workbook.xml` + its `.rels` properly (not assumed sheet1.xml order),
so a manually-reordered-tabs file still resolves correctly.

**Verified live**: uploaded a real openpyxl file with a merged bold white-on-green header, a
gray bold sub-header row, green bold text, and red italic text — every one of those rendered
with the exact correct computed CSS (`getComputedStyle` checked in a real browser, not just
DOM inspection). Test content/R2 objects deleted afterward.

## Phase 9 — Admin panel rework

- [ ] Remove MoxoTest (view, permission, route, model)
- [ ] Rework course management (promo codes, open-source toggles)
- [ ] Quiz authoring UI
- [ ] Resource moderation rework (forum moderation itself superseded by the dedicated
  Phase 11 below — this bullet now covers whatever non-forum resource moderation surface
  remains, e.g. course/content-level flags)
- [ ] Translation review UI reflecting DeepL engine
- [ ] Update `ADMIN_PERMISSIONS` (drop `moxo_test_management`, add quiz/promo-code keys)
- [ ] Adding more control over platform features such as locking some of them
- [ ] Reworking the UI of Admin panel

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

## Phase 11 — Forum rework (course groupchats, groups, DMs, reply UX)

Started 2026-08-31, core done and live-verified (course channel, reply UX, pin/translate/
delete); Groups/DMs/expiry sweep still open — see the evidence below each item. Full plan at
`/home/alhiko56/.claude/plans/modular-sniffing-wren.md`. Supersedes Phase 9's old
"Forum/resource moderation rework" bullet — this is a full rework, not an admin-panel tweak.
Current state going in:
`ForumChannel`/`ForumMessage` (`lms/models/__init__.py`) are **global only**, a deliberate
Phase 2 decision at the time ("Forum stayed global rather than becoming course-scoped like
Resources did") — no `course_id` column exists on either model today. Replies today are a
Reddit-style nested tree (`ForumMessage.parent_id`, self-referential FK) with no group/DM
concept at all.

**Correction (2026-08-31) — "course groupchat" means reworking the existing Announcements tab
into a channel, not adding a new tab.** The course page already has a course-scoped
messaging surface today — the "Announcements" tab, backed by its own separate model pair
(`CourseAnnouncement`: title + message, teacher-authored, `is_published`-gated; and
`CourseAnnouncementReply`: a second, independent Reddit-style nested-reply tree, parallel to
and unrelated to `ForumMessage`'s). The plan is to fold that into the same course-scoped
`ForumChannel`/`ForumMessage` system used for global channels — a real channel, not a
moderator-created Group (Groups stay forum-tab-only, per the bullet below) — shown embedded in
what's currently the Announcements tab *and* in the Forum tab, same channel both places. This
implies migrating (or at minimum retiring in favor of) `CourseAnnouncement`/
`CourseAnnouncementReply` rather than adding a second, separate course-scoped messaging system
alongside them — confirm the exact migration/retirement shape when this is scoped for real,
since existing announcement data would need a home in the new shape.

**Decided architecture (2026-08-31, confirmed with the user before building):** one unified
system, not three separate ones — `ForumChannel` gained `channel_type`
('global'|'course'|'group'|'dm') and `course_id`; every message (global, course, Group, or DM)
is the same `ForumMessage` row. Group membership is configurable per group ('open' or
'invite_only', via a new `ForumChannelMembership` table — also used unconditionally for DMs).
Retention is configurable per channel (`retention_days`, nullable), not one global setting.

- [x] **Course channel** — done and live-verified. `ForumChannel` gained `channel_type`/
  `course_id`/`created_by`/`membership_mode`/`retention_days`; new `ForumChannelMembership`
  table. Two-migration split (`d0e1f2a3b4c5` schema+data, `e1f2a3b4c5d6` destructive drop),
  mirroring the `PDFDocument` removal's precedent — the dev DB had zero real
  `CourseAnnouncement`/`CourseAnnouncementReply` rows to migrate, but the data-migration logic
  (title folded into the message body as a bold-prefixed line, reply parent-chains remapped
  from the old id-space to the new one) ran clean against the real schema. One `ForumChannel`
  auto-created per existing `Course` by the migration; new `Course` creation (both self-service
  and admin) now creates its channel the same way `Enrollment` creation is already mirrored
  across those two call sites. The Announcements tab now embeds the course's channel via the
  shared `components/forum_ui.html` include instead of server-rendering
  `CourseAnnouncement` rows.
  - **Real pre-existing bug fixed along the way**: `ForumMessage.channel` was a bare string
    with no FK to `ForumChannel` at all — fixed to a real `channel_id` FK as part of this
    (the API still accepts a channel *slug* externally, resolved to `channel_id` server-side,
    so no client-facing URL churn).
- [x] **Moderator-created Groups** — the model/schema/permission side is done; the polish
  (dedicated member-add/remove UX beyond a plain admin grid) is still open, see below.
  `ForumChannelView` (admin panel) extended to create/edit `channel_type='group'` channels
  with `membership_mode`, gated by the existing `has_perm('forum_management')` — satisfies
  "created by moderators of the site" using a permission key that already existed but wasn't
  actually enforced by the old forum edit/delete routes (real gap found and fixed, see below).
  New `ForumChannelMembershipView` (admin) is the working-if-plain way to add/remove members
  for `membership_mode='invite_only'` groups today.
- [ ] **Private messages (1:1 DM)** — not yet built. `forum_service.find_or_create_dm()`
  exists (deterministic slug, creates the channel + 2 membership rows) but there's no inbox
  UI or "Message this user" entry point yet, and its exact placement (a dedicated page? a
  profile action?) still needs a quick decision — flagged in the plan, not decided
  unilaterally.
- [x] **Per-message translation** — done and live-verified. `POST
  /api/forum/messages/<id>/translate` calls `translation_service.get_translation()` directly,
  no new persistence (the existing `Translation` cache is content-agnostic, keyed by
  source-text+target-language regardless of origin). Verified live against a real message,
  correctly cached.
- [x] **Pinning messages** — done and live-verified. `POST /api/forum/messages/<id>/pin`,
  moderator-gated via new `forum_service.can_moderate_channel()` (course: `is_managed_by`;
  global/group: `has_perm('forum_management')` or the channel's own `created_by`; DMs:
  no moderator role at all, not offered). Verified live: a non-manager correctly got `403`,
  the course's own manager correctly succeeded.
- [x] **Deletable chat history — both modes done.** Manual: `DELETE
  /api/forum/messages/<id>` reworked from a hard delete to a soft delete (`deleted_at`),
  rendered client-side as a "[message deleted]" placeholder so reply threads don't orphan —
  same anonymize-in-place philosophy this app already uses for user-account deletion. New
  moderator-only "Clear channel history" bulk action (`POST
  /api/forum/channels/<id>/clear`) does a real hard delete, relying on cascade (see below).
  Time-based: not yet built — `retention_days` exists on the schema and
  `forum_service.purge_expired_channel_messages()` is written, but the recurring sweep job
  (`run_scheduled_forum_purge`/`ensure_forum_purge_scheduled`, mirroring
  `run_scheduled_conversation_purge`) isn't wired into `job_manager.py`/`worker.py` yet.
  - **Real pre-existing bug fixed along the way**: `ForumMessage.parent_id` had no
    delete-cascade behavior at all — deleting a message with replies orphaned them. Fixed at
    the DB level (`ON DELETE CASCADE` on the FK) — **and a second, subtler bug found live
    during verification**: SQLAlchemy's ORM by default actively nulls out a loaded child's
    foreign key before issuing the parent's DELETE (satisfying its own unit-of-work
    bookkeeping), which runs *before* the DB-level cascade ever gets a chance to fire —
    silently orphaning replies instead of removing them, even with the FK constraint in place.
    Caught by live testing (a hard-deleted parent left its reply behind with `parent_id`
    NULL), fixed with `passive_deletes=True` on the `replies` relationship
    (`lms/models/__init__.py`), re-verified clean afterward.
- [x] **Reply UX overhaul** — done and live-verified. New shared component
  `lms/templates/components/forum_ui.html`, included by both `forum.html` and the course
  page's Announcements tab (the one JS module the plan called for, not copy-pasted). WhatsApp/
  Telegram-style flat chronological view is the default, each reply showing an inline
  "↩ replying to X: '…'" quote (the API's flat message shape now always includes
  `parent_username`/`parent_snippet`, computed cheaply since the query already has the parent
  object in hand). The existing Reddit-style nested-tree view is a toggle, remembered via
  `localStorage` (matching the Ask AI quick/thorough toggle's precedent) — with a "View
  thread" action once nesting passes a depth threshold, opening a flattened, indented view of
  just that subtree.
- [x] **Message ordering** — resolved as expected: no new ID scheme needed. The API's
  `GET /api/forum/messages` was rewritten from a server-side recursive nested-tree response to
  a flat list ordered by `(timestamp, id)` ascending — simpler on the backend, and lets the
  frontend build *both* the linear and threaded views from the same one response instead of
  needing a second query shape.
- [x] **Real gap found and fixed while wiring moderation**: `ADMIN_PERMISSIONS` already
  defined a `'forum_management'` key, but the pre-existing forum edit/delete routes checked
  `current_user.is_admin` directly, never `has_perm('forum_management')` — a sub-admin with
  that exact permission couldn't moderate the forum despite the permission existing for
  precisely that. Fixed as part of the pin/moderate/clear routes (edit stayed
  author-only — a moderator can pin/delete but shouldn't be able to rewrite someone else's
  words).
- [x] **Triplicated dead forum UI removed**, per explicit confirmation: `lms/templates/
  index.html` (confirmed rendered by zero routes — same situation `PDFDocument` was in before
  its removal, found while investigating this) deleted entirely, not just its `#forum`
  section; `course_forum.html` + `course_messages.html` (a second, previously-unnoticed dead
  template — also broken, calling `.order_by()` on a `lazy='select'` relationship as if it
  were a dynamic query) + the orphaned `main.view_course_messages` route all deleted.
- [x] **Live-verified end to end** (real Flask test client, real sessions, no mocks): posted
  and replied to a message in a real course channel, confirmed the flat response's
  `parent_username`/`parent_snippet` were correct; translated a message and got a real
  Russian translation back; confirmed a non-manager got `403` trying to pin, then confirmed
  the real course manager succeeded; soft-deleted a message and confirmed the row survived
  with the deleted-placeholder shape; hard-cleared a channel as admin and confirmed both the
  top-level message and its (already-cascaded) reply were genuinely gone from the database,
  not just hidden; confirmed a real DB inspection of the passive_deletes fix. `/forum` and a
  real `/course/<id>` page both confirmed rendering `200` end to end (no template errors) after
  the rework. App boots clean, `uv run ruff check` clean across every touched file, zero
  remaining references anywhere to `CourseAnnouncement`/`CourseAnnouncementReply`/
  `course_forum.html`/`course_messages.html`/`index.html`.

- [x] **Time-based expiry sweep** — done and live-verified. `run_scheduled_forum_purge`/
  `ensure_forum_purge_scheduled` (`lms/job_manager.py`) added, mirroring
  `run_scheduled_conversation_purge`'s exact shape (same `BackgroundJob` tracking, same
  re-enqueue-in-`finally` pattern); runs every `FORUM_PURGE_INTERVAL_HOURS` (6h — retention
  is per-channel, not global, so this just needs to not lag noticeably behind a short
  per-channel setting) and registered in `lms/worker.py` alongside the other three sweeps.
  Verified live: set a real DM channel's `retention_days=1`, backdated a real message to 5
  days old, called `purge_expired_channel_messages()` directly, confirmed it reported
  `{'channels_checked': 1, 'messages_deleted': 1}` and the message was genuinely gone
  afterward (not just hidden).
- [x] **Private messages (1:1 DM) — done and live-verified.** New `GET /api/forum/dms` (list
  my conversations), `POST /api/forum/dms/start` (find-or-create by username, reusing
  `forum_service.find_or_create_dm`). New `/messages` page
  (`lms/templates/messages.html`) — tab-per-conversation UI mirroring `forum.html`'s
  channel-tab pattern, embedding the same shared `forum_ui.html` component (DMs get pin/
  translate/soft-delete for free, no extra code — pin is correctly withheld, per
  `can_moderate_channel`'s "no moderator role in a DM" rule). Entry point: a "Message" link
  next to any other user's name in the shared component (hidden on your own messages and
  inside DMs themselves), landing on `/messages?user=<name>` which auto-starts that
  conversation. New "Messages" navbar link, shown only when logged in.
  - **Verified live**: real `find_or_create_dm` between two real users produced a
    deterministic slug; the sender could post and view; a real third user's
    `can_view_channel()` check correctly returned `False` (privacy confirmed — not just "no
    button to find it," genuinely denied at the permission-check level); the recipient
    correctly saw both the conversation in their list and the message content.
- [x] **Moderator-created Groups — schema/permission side confirmed still solid**, member
  management remains the plain `ForumChannelMembershipView` admin grid from the section
  above (functional, not polished) — no further work done here this pass; a lighter in-app
  moderator control stays a possible future upgrade, not required.
- [x] **Final live sweep**: `/messages`, `/forum`, and a real `/course/<id>` page all
  reconfirmed rendering `200` after the DM/expiry additions (163 routes registered, up from
  160). `uv run ruff check` clean across every file touched this phase.

**Phase 11 is now fully complete** — course channels, Groups, DMs, pinning, translation,
soft/hard delete, time-based expiry, and the reply-UX overhaul are all built and live-verified.

## Phase 12 — Sitewide input censoring (mandatory)

Planned 2026-08-31, not yet started. Applies beyond the forum — every user-authored text field
across the site needs to go through this, not just chat/DM/group messages: quiz short-answer
text, course/content titles & descriptions, profile bio, assignment submission text fields,
forum channel/group names. New `lms/content_moderation.py` (no Flask/DB dependency, mirrors
`core_translator.py`'s role), called at each of those input boundaries.

**Decided approach (2026-08-31):** word-list only, no ML/classifier layer. Google's Perspective
API — the obvious off-the-shelf toxicity API — was considered and ruled out: it's genuinely
being retired (Google/Jigsaw's own announcement; new requests stop being accepted after
February 2026, service ends entirely December 31, 2026), so building against it now would mean
migrating off it almost immediately. A self-hosted ML alternative (e.g. a multilingual
Toxic-BERT variant, which does cover Russian) was also considered and explicitly passed on —
this project has twice already deliberately avoided a `torch` dependency (picked
`faster-whisper`'s ctranslate2 backend over `openai-whisper` specifically to dodge torch's
~800MB weight), and a BERT-family model would reintroduce exactly that tradeoff. **Enforcement
posture: hard-block at submit time** (reject with an inline error, nothing gets posted) — with
a word-list match being an unambiguous violation (not a graded/borderline score the way an ML
classifier's output would be), a hard reject is the right default; there's no nuance here to
route to a moderator review queue for. A message a moderator still wants gone after the fact is
covered by Phase 11's manual-delete feature, not by this layer.

- [ ] `lms/content_moderation.py`: `check_text(text) -> {'blocked': bool, 'matched_terms': [...]}`
  (or similar), loading maintained EN + RU word lists (RU profanity/mat has real,
  actively-maintained open lists distinct from EN ones — don't assume one list transliterates
  to the other).
- [ ] Wire into every input boundary listed above — forum/DM/group messages first (Phase 11
  ships alongside this), then retrofit the pre-existing surfaces (quiz answers, course/content
  text fields, profile bio, submissions).
- [ ] Admin-manageable word list (add/remove terms without a code deploy) — likely a simple
  admin panel view, matching this app's existing `SecureModelView` conventions.
- [ ] Revisit if word-list-only proves insufficient in practice (e.g. sustained harassment
  phrased without listed words) — Gemini-based classification (reusing `gemini_client.py`'s
  existing model-fallback chain, zero new dependency) was the runner-up approach and stays the
  natural upgrade path if this is revisited later, now that the ML-model-with-torch option is
  off the table and Perspective is disqualified either way.

## Phase 13 — Analytics improvements

Planned 2026-08-31, not yet started — a brainstormed list of where analytics would add real
value, to be scoped down before implementation. `ContentView` (existing) and `BackgroundJob`
(existing, tracks every job's status/timing) are the two tables most of this can build on
without new instrumentation; the video-moment-highlighting feature's `VideoMomentFlag` data
(Phase 6 addendum) is currently written but only ever consumed by the promotion sweep — it's
real, already-collected per-timestamp engagement signal that no dashboard surfaces yet.

- [ ] **Student-facing**: personal progress (content completed vs. total per course, quiz score
  history), activity/streak tracking.
- [ ] **Teacher-facing, per course**: enrollment/retention over time and a join-but-never-opened
  drop-off funnel; content engagement (view counts already exist via `ContentView` — video
  watch-through/engagement could finally surface `VideoMomentFlag` data as a teacher-only
  engagement heatmap, distinct from the *student-facing* seek-bar markers that were explicitly
  scoped out of the video-moments feature — this is a teacher analytics view, not that); quiz
  analytics (per-question difficulty, score distribution, most-missed questions); assignment
  analytics (submission rate, on-time vs. late, grade distribution); forum/chat engagement once
  Phase 11 exists (messages per channel, most active students, moderation-action counts); Ask
  AI usage per course (question volume, quick vs. thorough split, how often retrieval returns
  "no indexed material" — a proxy for content gaps).
- [ ] **Admin/site-wide**: DAU/WAU/MAU, signup funnel (signup → verified → first course join →
  first content view), retention cohorts; cost/ops (Gemini call volume and estimated cost
  trend, Whisper minutes transcribed, R2 storage growth, background-job failure rate — all
  derivable from existing tables); content health (courses with zero content or zero
  enrollment, translation coverage %, content that's never been viewed); growth (which public
  courses drive the most signups, promo-code redemption effectiveness).
- [ ] **Moderation-specific** (ties directly to Phase 12): censored-message volume over time
  (a spike is a signal worth surfacing on its own) and per-user block counts, to surface repeat
  offenders for admin action.

## Phase 14 — Rubric-based grading

Added to the roadmap 2026-08-31. Builds directly on the existing `CourseAssignment`/
`CourseAssignmentSubmission` grading flow rather than introducing a parallel one — a rubric is
a structured alternative to the current single freeform grade/feedback field, not a new
grading surface.

- [ ] `Rubric`/`RubricCriterion` models — teacher-authored, reusable across assignments in a
  course (or scoped to one assignment, decide when scoped for real); each criterion has a
  configurable set of levels/points (**"configurable options by users"** — the point/level
  scheme itself is teacher-defined per rubric, not a fixed 4-point scale hardcoded by the app).
- [ ] Rubric authoring UI (likely alongside the Phase 9 quiz-authoring UI work, same
  "teacher builds structured grading criteria" shape).
- [ ] Grading UI: replace/augment the current single grade field with a per-criterion
  score picker when an assignment has a rubric attached; auto-sum to a total.
- [ ] Student-facing: show the filled-out rubric breakdown alongside the grade, not just a
  number — the whole point of a rubric is showing *why*.
- [ ] Decide whether rubrics also apply to quiz short-answer manual review (Phase 1's
  `quiz_review` flow) or stay assignment-only for this pass.

## Phase 15 — Specializations / learning paths

Added to the roadmap 2026-08-31. Bundles existing `Course` rows into an ordered track — no
change to how an individual course works, this is a new grouping layer on top.

- [ ] `Specialization`/`SpecializationCourse` models (ordered M2M between a track and its
  member courses) — decide up front whether course order within a track is enforced
  (must finish course N before N+1 unlocks) or purely organizational/display.
- [ ] Enrollment model: joining a specialization enrolls the user in all of its courses (or
  lazily enrolls as they progress, if order is enforced) — reuse the existing `Enrollment`
  machinery rather than a parallel one.
- [ ] Specialization landing page (progress across the whole track, not just one course) and
  a completion certificate distinct from a single-course certificate.
- [ ] Admin/teacher authoring UI to assemble a specialization from existing courses.
- [ ] Discovery: surface specializations on the Home/Resources pages alongside standalone
  public courses.

## Phase 16 — Calendar

Added to the roadmap 2026-08-31. Primarily a read view over deadline data that mostly already
exists (`CourseAssignment.due_date`, quiz windows) rather than a new scheduling engine.

- [ ] `CalendarEvent` model for things with no existing due-date column (course sessions,
  manually added events) — decide if this is teacher-created only or also supports
  personal/student-added events.
- [ ] Calendar view aggregating: assignment due dates, quiz open/close windows, and any new
  `CalendarEvent` rows, scoped to the user's enrolled courses.
- [ ] Per-course calendar (teacher's view of just their course's schedule) and a personal
  cross-course calendar (student's view across everything they're enrolled in).
- [ ] Decide on reminder delivery — ties into Phase 10 (real email) if reminders should email;
  in-app-only notification is a lighter first cut that doesn't block on Phase 10.
- [ ] `.ics` export, if useful for syncing into a user's own calendar app.

## Phase 17 — LTI (Learning Tools Interoperability)

Added to the roadmap 2026-08-31, not yet scoped in depth. Lets external third-party tools
(publisher content, proctoring, plagiarism checkers, etc.) plug into a course without custom
per-tool integration code — this app would act as an **LTI Platform** (the LMS side), external
tools as **LTI Tools**. Significant standards/security surface — expect this to need
`/security-review` before shipping, per this app's own conventions for anything touching auth/
OAuth.

- [ ] Decide LTI version target: LTI 1.3 (current standard, OAuth2/JWT-based, requires a
  registered key pair and a platform/tool registration flow) vs. legacy LTI 1.1 (OAuth 1.0a,
  simpler but deprecated industry-wide) — LTI 1.3 is very likely the right call given anything
  new should target it, but confirm before building against a dying spec.
- [ ] Platform registration flow (tool consumer key/secret or JWT keys, deployment IDs).
- [ ] Launch flow: course page surfaces an LTI tool as a content/tab type, POSTs a signed
  launch request with user/course/role claims, tool redirects the student into its own UI.
- [ ] Grade passback (LTI Advantage's Assignment and Grade Services) so an external tool's
  score can land back on a `CourseAssignment`/grade record here, if in scope for this pass.
- [ ] Decide how an LTI-backed activity fits into the existing folder-locking/gating and
  analytics (Phase 13) machinery, since it's content this app doesn't fully control.

## Phase 18 — Offline download (tentative — flagged "maybe" by design intent)

Added to the roadmap 2026-08-31, priority genuinely uncertain — revisit before committing real
build time. Worth flagging up front: this sits in direct tension with the existing content-
protection posture (`file_viewer.html`'s anti-copy/watermark machinery, the whole point of
routing every file through a permission-rechecking in-app viewer instead of a raw link — see
the Cloudflare Worker file-proxy work). "Download for offline" is close to the opposite goal of
"never let the raw file leave a controlled viewer." Needs an explicit decision on scope before
any code: whole-course offline packages, or per-file download only for content already flagged
`is_downloadable`?

- [ ] Decide scope: extend the existing per-file `is_downloadable` flag (already used by
  `download_content_by_db_id`) to a bulk "download this course for offline" action, vs. a
  genuinely new offline-sync mechanism (service worker cache, a packaged export).
- [ ] If bulk export: background job (Phase 3 queue) to zip a course's downloadable content,
  served once via the same signed-URL pattern the R2 file-proxy already uses rather than a
  raw static link.
- [ ] Explicit call on whether protected (non-downloadable) content is ever included — default
  should almost certainly be no, matching the existing per-file flag's intent.

---

## Backlog — noted for later (not scheduled to a specific phase yet)

- [ ] **Real-time collaborative editing** — added 2026-08-31, explicitly speculative ("maybe in
  the future," not a committed phase). No concrete target surface chosen yet (course content
  authoring? a shared document type? forum drafts?) — needs a scoping decision before it can
  become a real phase, since the infrastructure cost (WebSocket transport, OT/CRDT conflict
  resolution) varies enormously depending on the answer. Revisit once Phases 14-18 land.

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
