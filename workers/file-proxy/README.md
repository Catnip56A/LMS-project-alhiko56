# file-proxy

Cloudflare Worker that fronts the R2 bucket for signed, short-lived file access. See the
module docstring in `src/index.js` for why this exists instead of plain presigned URLs.

## Deploy

**One-time setup**, requires a Cloudflare account with Workers + the R2 bucket already set up
(same account as `R2_ACCOUNT_ID` in `.env`):

```bash
npx wrangler login                       # one-time browser auth; if OAuth fails (common on
                                          # WSL2 — "No CSRF value available"), use an API token
                                          # instead — see below
```

If OAuth login fails, use an API token instead: [Cloudflare dashboard → My Profile → API
Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token → Custom token, with
**Account > Workers Scripts > Edit** and **Account > Workers R2 Storage > Edit** permissions,
scoped to your account. Put the token and your account ID (shown on the Workers & Pages
overview page) into `.env` as `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` — `just`'s
dotenv-load exports them automatically for every recipe below, no manual `export` needed.

```bash
cd /path/to/repo && just deploy-worker   # deploys the Worker; prints its live URL on first run
npx wrangler secret put SIGNING_SECRET   # one-time: paste output of `openssl rand -hex 32`
```

**Every subsequent redeploy** (e.g. after editing `src/index.js`) is just:

```bash
just deploy-worker
```

`wrangler deploy` prints the live URL, e.g. `https://lms-file-proxy.<account>.workers.dev`.
Put that in the app's `.env` as `R2_WORKER_URL`, and the same secret you just set as
`R2_WORKER_SIGNING_SECRET` — they must match exactly or every request 403s.

If a different environment (staging/prod) uses a different R2 bucket name, edit
`bucket_name` in `wrangler.toml` before deploying for that environment, or add
`[env.staging]` / `[env.production]` blocks with their own `r2_buckets` binding.

## Redeploying

Any change to `src/index.js` needs `just deploy-worker` again — there's no auto-reload.
`SIGNING_SECRET` only needs to be set once (`npx wrangler secret put SIGNING_SECRET` again to
rotate it, but rotating it invalidates every URL signed with the old value within its ~60s
window, which is harmless — they're that short-lived anyway).
