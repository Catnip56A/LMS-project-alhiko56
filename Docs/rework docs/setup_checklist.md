# LMS Rework — Manual Setup Checklist

Things only you can do (accounts, consoles, keys) for each phase of the rework roadmap
(`Docs/rework docs/Increment_LMS_Rework_Planning_Document.docx` — the platform's planning
doc; no longer affiliated with Yonca, now developed independently as **Increment LMS**, and
the file has been renamed to match; plan tracked in-session). Grouped by the phase that needs
them — nothing here blocks the phase before it in the list.

Drop values into `.env` (see `.env.example` for the existing pattern) using the variable
names below unless noted otherwise.

---

## Phase 0 — Security hardening (in progress now)

- [ ] **Decide on outbound email** for the email-verification step. Nothing to sign up for
  yet — for local dev I'll default to logging verification links to the console/log instead
  of actually sending mail, so this isn't blocking. If you already have a preference for
  later (Gmail SMTP, Mailgun, SendGrid, Postmark, etc.), let me know when we get there;
  otherwise I'll flag it as a decision point when this piece is ready.

No accounts needed for CSRF, rate limiting, upload limits, logging, or GDPR basics — all self-hosted / library-only.

---

## Phase 3 — Shared background job queue

Nothing to do — Redis runs as a new `docker-compose.yml` service (self-hosted), no external account.

---

## Phase 4 — Google Drive worker account

Replaces per-admin OAuth with one dedicated account that owns all course files.

**Interim stopgap already shipped:** creating a throwaway Google account to act as a shared
service identity is legally murky under Google's ToS (personal accounts aren't meant to be
used as bot/service accounts). Until the real worker account exists, any full admin can go
to **Admin → Drive Writer** and designate their own already-linked Google account as the
system-wide writer — all uploads/deletes route through it instead of each user's own
account. Test-only; nothing here is a substitute for steps 1–4 below.

**The real mechanism is now built** (`Admin → Drive Worker`, `/admin/drive_worker/`) — a
dedicated place to store one Google account's OAuth tokens server-side, independent of any
`User` row. Once connected there, it automatically takes priority over the Drive Writer
stopgap above for every upload/delete/permission-change. All that's left is the manual setup
only you can do:

1. [ ] **Create a new Google account** not tied to any team member — e.g.
  `lms.drive.worker@gmail.com` (name it whatever you like). Free personal account is fine
  for Phase 1 of the Drive rollout (15 GB).
2. [x] **Add it as a test user** on the existing Google Cloud OAuth consent screen, if the
  app is still in "Testing" publishing status (Google Cloud Console → APIs & Services →
  OAuth consent screen → Test users). This is a common gotcha — without it, the worker
  account's login will be silently rejected by Google.
3. [x] **In your browser, sign into Google as the worker account** (not your own), then go
  to `Admin → Drive Worker` (full admins only) and click "Connect Worker Account". It'll ask
  for Drive access under whichever Google account is signed in in that browser tab.
4. No new `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` needed — the existing OAuth app/client
  is reused; only the account authorizing it changes.
5. On the OAuth consent screen's **Scopes** section, declare
  `https://www.googleapis.com/auth/drive.file` (not the broader `drive` scope — the app was
  briefly requesting the broad one, but that's been tightened to match what
  `google_drive_service.py` actually uses).

**Phase 4 is done** — worker account connected and verified live.

*(Phase 2 of the Drive rollout — moving to a paid Google Workspace Shared Drive — is
explicitly deferred until we're past the local-only build.)*

---

## Phase 5 — Translation pipeline (DeepL)

1. [x] **Sign up at [deepl.com/pro-api](https://www.deepl.com/pro-api)** for the free API
  plan. Account dashboard shows usage as a lifetime cap (1,000,000 characters total), not a
  monthly-resetting quota — check deepl.com's account page for your plan's exact terms
  rather than relying on this doc.
2. [x] `DEEPL_API_KEY` set in `.env`. Verified live — a real translation landed in
  `content_translation` via the recurring sweep, and 6 UI strings were translated through
  the `.po` pipeline.
3. Azerbaijani support has been removed from the app entirely (not just disabled) — DeepL
  doesn't support it, and it's gone from `constants.py`, the locale selector, the `.po`
  translation files, and the hand-translated legal pages. Re-adding it later would mean
  reintroducing the language end-to-end (a separate translation engine that supports it,
  plus UI/legal-page work), not just flipping a flag back on.

---

## Phase 6 — AI personal guide + subtitles (Gemini)

1. [x] **Get a free Gemini API key** at [Google AI Studio](https://aistudio.google.com/) —
  no card required, ongoing free tier (not a trial). Covers both the RAG chat and audio
  transcription for subtitles from one key. (Hit a Google account age-verification snag
  during signup unrelated to this project — resolved on Google's side.)
2. [x] `GEMINI_API_KEY` set in `.env`. Verified live end-to-end — a real question through
  the course page's "Ask AI" tab returned a correctly-cited answer.
3. [ ] If you expect to later enable billing on this Google Cloud project for anything else
  (e.g. Gemini TTS in Phase 7), use a **separate project/API key** for that — enabling
  billing on a project removes its free tier entirely, and you don't want that to take out
  the free chat/transcription key by accident.
4. [x] **Transcription engine decided: self-hosted Whisper** (`faster-whisper`). No account or
  key needed — it runs locally in the worker container. DeepL was ruled out (its Voice API is
  real-time WebSocket streaming for live meetings: no batch endpoint, no timestamps, paid tier
  only) and Gemini was rejected for this job specifically (no timestamps, and we hit 429s across
  every fallback model during Phase 6 testing). Verified end to end on a real 5:13 lecture:
  113 timestamped segments. No system `ffmpeg` needed after all — PyAV bundles the FFmpeg
  libraries. **Correction to an earlier number here**: the original "~5x realtime" figure was
  measured with 16 cores available *and* VAD trimming the lecture's natural silence/pauses — it
  mixed core-count and content effects and doesn't predict a real deployment. Isolated the two:
  on a genuine 2-CPU cap (`docker update --cpus=2`, same file, same settings), the same lecture
  took 2.1x longer than on 16 cores — ~24 min for a 50-minute lecture on 2 vCPUs, not the ~10
  min this line used to imply. See `development_checklist.md`'s Phase 6 addendum for the full
  comparison and the production RAM/disk sizing.
5. [ ] **On the production server's own `.env`** (not this repo — matches how `DEEPL_API_KEY`
  etc. already work), set `WHISPER_CPU_THREADS=<real vCPU count>` once the VPS is provisioned
  (e.g. `WHISPER_CPU_THREADS=2` for a 2-vCPU box). Left unset, `faster-whisper` auto-detects
  from *visible* core count — fine locally (dev machines see all their own cores), but
  measured to cost real throughput on a constrained cloud VM: `docker update --cpus` throttles
  CPU time without changing what the container reports as its core count, so the thread pool
  over-subscribes and fights over the real budget. Pinning it to the true count removes that.
  Update the number if the plan is ever resized.

No vector DB account needed — used the `pgvector` Postgres extension on the existing
database. One thing this did require: plain `postgres:17-alpine` doesn't ship the
extension, so the DB image is now `pgvector/pgvector:pg17` across dev/staging/production.

---

## Phase 6 addendum — Cloudflare R2 (course content storage)

Course content (video, audio, documents, images — both direct uploads and Google Picker
imports) now lives in Cloudflare R2 instead of Google Drive; see
`development_checklist.md`'s "Phase 6 addendum — Cloudflare R2 migration" for the full design
and reasoning (presigned URLs let the browser stream directly from Cloudflare's CDN, and a
real `<video>` element replaces the old cross-origin Drive iframe, enabling seeking and
click-to-seek citations).

1. [x] **Dev — done, live-verified (2026-08-27).** Cloudflare account created, R2 enabled,
  bucket `increment-lms` created (private, no public access/`r2.dev` domain) with an Object
  Read & Write API token scoped to it, `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/
  `R2_SECRET_ACCESS_KEY`/`R2_BUCKET_NAME` set in dev's `.env`. Confirmed live: real
  upload/serve/delete round trips through the app, and the existing course content (1 video +
  3 documents) backfilled from Drive into this bucket via `just backfill-r2`. Nothing further
  needed for dev.
2. [ ] **TODO when staging is deployed**: create a separate bucket (e.g. `lms-staging`, private,
  same settings as dev's) and its own Object Read & Write API token scoped to just that bucket.
  Set `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_BUCKET_NAME` in staging's
  `.env` (same var names as dev, different values — `R2_ACCOUNT_ID` is the same across all
  environments, it's account-level not bucket-level). Do this **before** the first deploy that
  includes this feature, or uploads on staging will fail with "File storage is not configured."
3. [ ] **TODO when production is deployed**: same as staging — separate bucket (e.g.
  `lms-production`), its own scoped API token, vars set in production's `.env`. Also before the
  first deploy with this feature.
4. [ ] **TODO, once production has real content in its bucket**: create one more R2 API token,
  scoped to **Object Read only** (not write) on the production bucket, and add it to **dev's**
  `.env` only as `R2_UPSTREAM_ACCOUNT_ID`/`R2_UPSTREAM_ACCESS_KEY_ID`/
  `R2_UPSTREAM_SECRET_ACCESS_KEY`/`R2_UPSTREAM_BUCKET_NAME`. Without this, pulling the
  production/staging DB into dev (`just db-pull-staging`) brings in `r2_key` values that only
  exist in the production bucket, and that content 403s locally until re-uploaded — this
  read-only token lets `r2_client`'s upstream fallback serve it instead. Not urgent; only
  matters the first time someone runs a DB pull after production has its own migrated content.
5. [ ] Optional, any environment: `R2_URL_EXPIRY_SECONDS=21600` — how long a media presigned URL
  stays valid (default 6h). Shorter is more secure (a leaked URL stops working sooner) but
  risks interrupting a long viewing session; longer is more convenient but widens the window a
  shared/leaked link stays usable.

Reference — the S3 endpoint is always `https://<account_id>.r2.cloudflarestorage.com` and the
region is always the literal string `auto` (both hardcoded in `lms/r2_client.py`, not
env-configurable).
8. [ ] Once credentials are set, run the one-time backfill for any content already on Drive:
  `just backfill-r2 --dry-run` first, then `just backfill-r2`. Safe to re-run — it only
  processes rows that still have `drive_file_id` set and no `r2_key` yet.

No new Google Drive scopes or credentials needed for this — Picker still uses the existing
Google OAuth setup (Phase 4) purely as the file-selection UI; only the byte storage moved.

---

## Phase 7 — AI audio overview (TTS)

1. [ ] **Sign up at [ElevenLabs](https://elevenlabs.io/)** for the free tier (10,000
  characters/month, non-commercial use — fine for prototyping this feature).
2. [ ] Set:
  ```
  ELEVENLABS_API_KEY=
  ```

---

## Phase 10 — Real email delivery

Signup currently works but email verification is a dev-mode placeholder — the link is
logged, not actually sent (`lms/email_service.py`). Lowest priority, scheduled after
Phases 6-9.

1. [ ] **Pick a provider**: Gmail SMTP (simplest, fine for low volume), SendGrid, Mailgun,
  or Postmark (all have free tiers suitable for this scale).
2. [ ] Set whatever credentials that provider needs in `.env` (e.g. `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, or an API key — exact vars depend on the
  provider chosen above).

---

## Optional / not required for v1

- **Sentry** (error tracking) — free tier (5,000 errors/month) if you want it; not required
  by the plan, purely optional observability.
- **Groq / Anthropic API keys** — only relevant if you want to compare RAG output quality
  against Gemini during testing; not part of the build plan itself.
