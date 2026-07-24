password: TempTest#Pass1

# LMS Rework — Manual Setup Checklist

Things only you can do (accounts, consoles, keys) for each phase of the rework roadmap
(`Docs/rework docs/Yonca_Rework_Planning_Document.docx`, plan tracked in-session). Grouped
by the phase that needs them — nothing here blocks the phase before it in the list.

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

1. [ ] **Create a new Google account** not tied to any team member — e.g.
  `lms.drive.worker@gmail.com` (name it whatever you like). Free personal account is fine
  for Phase 1 of the Drive rollout (15 GB).
2. [ ] **Add it as a test user** on the existing Google Cloud OAuth consent screen, if the
  app is still in "Testing" publishing status (Google Cloud Console → APIs & Services →
  OAuth consent screen → Test users). This is a common gotcha — without it, the worker
  account's login will be silently rejected by Google.
3. [ ] **Log in as the worker account** and run through the app's existing "Link Google
  Account" admin flow once, so it can grant Drive access. I'll then store the resulting
  refresh token server-side (not on a `User` row) and switch all Drive writes to use it.
4. No new `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` needed — the existing OAuth app/client
  is reused; only the account authorizing it changes.

*(Phase 2 of the Drive rollout — moving to a paid Google Workspace Shared Drive — is
explicitly deferred until we're past the local-only build.)*

---

## Phase 5 — Translation pipeline (DeepL)

1. [ ] **Sign up at [deepl.com/pro-api](https://www.deepl.com/pro-api)** for the free API
  plan (500k characters/month, no cost at this scale).
2. [ ] Grab the API key and set:
  ```
  DEEPL_API_KEY=
  ```
3. Azerbaijani is out of scope for the translation swap (DeepL doesn't support it, and `az`
  stays disabled per `constants.py`) — nothing to set up there unless you decide to revisit
  Azerbaijani later, in which case it'd be a separate Google Cloud Translation or Azure
  Translator key.

---

## Phase 6 — AI personal guide + subtitles (Gemini)

1. [ ] **Get a free Gemini API key** at [Google AI Studio](https://aistudio.google.com/) —
  no card required, ongoing free tier (not a trial). Covers both the RAG chat and audio
  transcription for subtitles from one key.
2. [ ] Set:
  ```
  GEMINI_API_KEY=
  ```
3. [ ] If you expect to later enable billing on this Google Cloud project for anything else
  (e.g. Gemini TTS in Phase 7), use a **separate project/API key** for that — enabling
  billing on a project removes its free tier entirely, and you don't want that to take out
  the free chat/transcription key by accident.

No vector DB account needed — the plan uses the `pgvector` Postgres extension on the
existing database, which I'll enable via a migration.

---

## Phase 7 — AI audio overview (TTS)

1. [ ] **Sign up at [ElevenLabs](https://elevenlabs.io/)** for the free tier (10,000
  characters/month, non-commercial use — fine for prototyping this feature).
2. [ ] Set:
  ```
  ELEVENLABS_API_KEY=
  ```

---

## Optional / not required for v1

- **Sentry** (error tracking) — free tier (5,000 errors/month) if you want it; not required
  by the plan, purely optional observability.
- **Groq / Anthropic API keys** — only relevant if you want to compare RAG output quality
  against Gemini during testing; not part of the build plan itself.
