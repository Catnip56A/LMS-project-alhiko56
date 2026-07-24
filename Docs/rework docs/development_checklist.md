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

**Phase 0 is complete.** Rate limiting → Redis migration is the only item still pending,
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

**Phase 1 is complete.**

## Phase 2 — Home, Resources, Forum

- [ ] Home page (replaces standalone `index.html`): course recommendations, promo-code join entry point, recent-activity overview
- [ ] Resources page: enrolled-course resources + open-source-flagged resources
- [ ] Forum page: enrolled-course threads + open-source-flagged channels
- [ ] Remove `/about` SPA-marker route, empty `static/gallery/` dir

## Phase 3 — Shared background job queue

- [ ] Add Redis service to `docker-compose.yml` (dev profile)
- [ ] Replace `lms/job_manager.py`'s thread-poll worker with RQ backed by Redis
- [ ] Migrate existing `translate_content` job type onto the new queue
- [ ] Point rate limiter's `storage_uri` at Redis (Phase 0 follow-up)

## Phase 4 — Google Drive worker migration

- [ ] Replace per-user OAuth in `google_drive_service.py` with single worker-account credential
- [ ] Store worker refresh token server-side via `AppSetting` (not on `User`)
- [ ] Update all `drive_file_id`/`drive_view_link` write paths (`Resource`, `PDFDocument`, `CourseContent`, `CourseAssignmentSubmission`) to authenticate as the worker

*(Requires the account + OAuth test-user setup in `setup_checklist.md` Phase 4 first.)*

## Phase 5 — Translation pipeline rework

- [ ] Move translation trigger from admin-click onto the Phase 3 RQ queue as an interval/threshold job
- [ ] Swap `core_translator.py` engine from LibreTranslate to DeepL (en/ru), keep `{LMS}` placeholder mechanism
- [ ] Lightweight spot-check pass on a sample of new translations per run

*(Requires the DeepL API key in `setup_checklist.md` Phase 5 first.)*

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

---

## Backlog — noted for later (not scheduled to a specific phase yet)

- [ ] Show/hide password toggle (eye icon) on password input fields (login, signup, change
  password, admin user creation, etc.)
- [ ] Merge the "Quizzes" tab on the course page into the "Assignments" tab instead of a
  separate tab (`lms/templates/course_page_enrolled.html`)
- [ ] Short-answer quiz questions: replace/augment the current case-insensitive exact-string
  auto-grading (`_check_quiz_answer` in `lms/models/__init__.py`) with manual teacher review
  or AI-assisted grading, so answers that are correct but not a literal string match aren't
  marked wrong

## Out of scope for this pass

Online meetings (Jitsi), AI grading, AI-generated quizzes, AI course recommendations, paid
enrollment (data model stub only, no payment integration).
