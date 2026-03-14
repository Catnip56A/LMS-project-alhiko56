# Deployment

## Files

| File | Purpose |
|---|---|
| `Caddyfile` | Caddy reverse proxy config — production |
| `Caddyfile.local` | Caddy reverse proxy config — local prod-dev profile |
| `gunicorn_config.py` | Gunicorn WSGI server config |
| `yonca.service` | systemd service unit (legacy, pre-Docker) |
| `deploy.sh` | Bare-metal setup script (legacy, pre-Docker) |
| `dnsmasq/local.conf` | dnsmasq drop-in for developer machines |
| `dnsmasq/prod.conf` | dnsmasq drop-in for the production server |

---

## Docker-based deployment (current)

See `docker-compose.yml` and `Justfile` at the project root.

### Profiles

| Profile | Command | URL |
|---|---|---|
| `dev` | `just up` | `http://localhost:5000` |
| `prod-dev` | `just prod-dev-up` | `https://local.yonca-sdc.com` |
| `prod` | `just prod-up` | `https://yonca-sdc.com` |

---

## dnsmasq setup

### Developer machine — `prod-dev` profile

Resolves `local.yonca-sdc.com` to loopback so the local Caddy container
serves it with a Caddy-issued certificate.

**Linux:**
```bash
sudo cp dnsmasq/local.conf /etc/dnsmasq.d/yonca-local.conf
sudo systemctl restart dnsmasq
```

**macOS (Homebrew):**
```bash
cp dnsmasq/local.conf $(brew --prefix)/etc/dnsmasq.d/yonca-local.conf
brew services restart dnsmasq
```

Verify resolution:
```bash
dig local.yonca-sdc.com +short   # should return 127.0.0.1
```

Then trust Caddy's local CA (once per machine):
```bash
just prod-dev-trust
```

---

### Production server

Resolves all `*.yonca-sdc.com` to loopback so internal requests stay local
instead of going out through public DNS and back (hairpin NAT).

```bash
sudo cp dnsmasq/prod.conf /etc/dnsmasq.d/yonca.conf
sudo systemctl restart dnsmasq
```

Verify:
```bash
dig yonca-sdc.com +short          # should return 127.0.0.1
dig api.yonca-sdc.com +short      # should return 127.0.0.1
```

> **Note:** Ensure dnsmasq is configured as the system resolver
> (`/etc/resolv.conf` or `systemd-resolved` stub). On Ubuntu with
> `systemd-resolved`, add `DNS=127.0.0.1` to `/etc/systemd/resolved.conf`
> and set `DNSStubListener=no`, then restart `systemd-resolved`.

---

## GitHub Actions secrets

Required secrets in `Settings → Secrets → Actions`:

| Secret | Description |
|---|---|
| `SSH_HOST` | Production server IP or hostname |
| `SSH_USER` | SSH user on the production server |
| `SSH_PRIVATE_KEY` | Private key for SSH access |
| `SECRET_KEY` | Flask secret key |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `DOMAIN` | Production domain (`yonca-sdc.com`) |

Optional variable (non-secret, `Settings → Variables → Actions`):

| Variable | Default | Description |
|---|---|---|
| `WEB_CONCURRENCY` | `3` | Gunicorn worker count |
