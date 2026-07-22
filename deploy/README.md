# Deployment

## Files

| File | Purpose |
|---|---|
| `caddy/docker-compose.yml` | Shared Caddy — runs once on the server, routes all domains |
| `caddy/Caddyfile` | Multi-site Caddy config (prod + staging) |
| `gunicorn_config.py` | Gunicorn WSGI server config |
| `backup.sh` | Backup Docker postgres to local dir or GCS |
| `restore.sh` | Restore from `.dump` or `.sql` |
| `dnsmasq/local.conf` | dnsmasq drop-in for developer machines |
| `dnsmasq/prod.conf` | dnsmasq drop-in for the production server |

---

## Docker-based deployment (current)

See `docker-compose.yml` and `Justfile` at the project root.

### Profiles

| Profile | Command | URL |
|---|---|---|
| `dev` | `just up` | `http://localhost:5000` |
| `prod-dev` | `just prod-dev-up` | `https://local.yourdomain.example.com` |
| `prod` | `just prod-up` | `https://yourdomain.example.com` |

### Server layout

```
~/deploy/
  caddy/                  # shared Caddy — started once, never torn down
    docker-compose.yml
    Caddyfile
    data/                 # TLS certs
  production/lms/       # prod app compose project
  staging/lms/          # staging app compose project
```

### Ports

| Environment | DB | App (direct, bypasses Caddy) |
|---|---|---|
| Production | `127.0.0.1:5439` | `127.0.0.1:5002` |
| Staging | `127.0.0.1:5438` | `127.0.0.1:5001` |

---

## dnsmasq setup

### Developer machine — `prod-dev` profile

```bash
# Linux
sudo cp dnsmasq/local.conf /etc/dnsmasq.d/lms-local.conf
sudo systemctl restart dnsmasq

# macOS (Homebrew)
cp dnsmasq/local.conf $(brew --prefix)/etc/dnsmasq.d/lms-local.conf
brew services restart dnsmasq
```

Verify: `dig local.yourdomain.example.com +short`  — should return `127.0.0.1`

Then trust Caddy's local CA (once per machine):
```bash
just prod-dev-trust
```

### Production server

```bash
sudo cp dnsmasq/prod.conf /etc/dnsmasq.d/lms.conf
sudo systemctl restart dnsmasq
```

> **Note:** On Ubuntu with `systemd-resolved`, set `DNS=127.0.0.1` in
> `/etc/systemd/resolved.conf`, set `DNSStubListener=no`, then restart
> `systemd-resolved`.

---

## Backups

```bash
# Manual backup
./backup.sh

# Restore
./restore.sh ~/backups/lms/lms_2026-03-17.dump

# Cron (add on server, runs daily at 3am)
0 3 * * * cd ~/deploy/production/lms && ./backup.sh >> ~/logs/backup.log 2>&1
```

---

## GitHub Actions secrets

Required in `Settings → Secrets → Actions`:

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
| `DOMAIN` | Production domain (`yourdomain.example.com`) |
| `STAGING_DOMAIN` | Staging domain (`staging.yourdomain.example.com`) |

Optional variable (`Settings → Variables → Actions`):

| Variable | Default | Description |
|---|---|---|
| `WEB_CONCURRENCY` | `3` | Gunicorn worker count |

Ports (`POSTGRES_PORT`, `APP_PORT`) and `APP_HOSTNAME` are derived
automatically from the branch — no secrets needed.
