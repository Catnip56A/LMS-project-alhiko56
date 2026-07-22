#!/usr/bin/env bash
# Bootstrap a fresh server for LMS deployment.
# Run from project root: ./scripts/bootstrap-server.sh <ssh-host> <ssh-user>
#
# What it does:
#   1. Installs Docker on the remote (Ubuntu/Debian)
#   2. Adds user to docker group
#   3. Creates deploy directory structure for production and staging
#   4. Copies docker-compose.yml and deploy files
#   5. Installs dnsmasq prod config
#   6. Starts shared Caddy (creates lms-proxy network automatically)
#   7. Prints next steps

set -euo pipefail

SSH_HOST="${1:?Usage: $0 <ssh-host> <ssh-user>}"
SSH_USER="${2:?Usage: $0 <ssh-host> <ssh-user>}"
SSH="ssh ${SSH_USER}@${SSH_HOST}"
SCP="scp"

ENVS=(production staging)

echo "▶ Bootstrapping ${SSH_USER}@${SSH_HOST}"

# ── 1. Install Docker ────────────────────────────────────────────────────────
echo "▶ Checking Docker..."
$SSH "docker --version" 2>/dev/null || {
  echo "  Installing Docker..."
  $SSH "curl -fsSL https://get.docker.com | sh"
  echo "  Docker installed."
}
echo "▶ Adding ${SSH_USER} to docker group..."
$SSH "sudo usermod -aG docker ${SSH_USER}"
echo "  Done — reconnect for group membership to take effect."

# ── 2. Create directory structure ────────────────────────────────────────────
echo "▶ Creating directory structure..."
for ENV in "${ENVS[@]}"; do
  $SSH "mkdir -p \$HOME/deploy/${ENV}/lms/{deploy,data/postgres,data/libretranslate,data/flask_session,data/logs} && chmod a+w \$HOME/deploy/${ENV}/lms/{deploy,data/postgres,data/libretranslate,data/flask_session,data/logs}"
done
$SSH "mkdir -p \$HOME/deploy/caddy/data"

# ── 3. Copy docker-compose.yml and deploy files ───────────────────────────────
echo "▶ Copying compose files..."
for ENV in "${ENVS[@]}"; do
  $SCP docker-compose.yml  "${SSH_USER}@${SSH_HOST}:~/deploy/${ENV}/lms/docker-compose.yml"
done
$SCP deploy/caddy/docker-compose.yml "${SSH_USER}@${SSH_HOST}:~/deploy/caddy/docker-compose.yml"
$SCP deploy/caddy/Caddyfile          "${SSH_USER}@${SSH_HOST}:~/deploy/caddy/Caddyfile"

# ── 4. Install dnsmasq config ─────────────────────────────────────────────────
echo "▶ Installing dnsmasq..."
$SSH "command -v dnsmasq" 2>/dev/null || $SSH "sudo apt-get install -y dnsmasq"
$SCP deploy/dnsmasq/prod.conf "${SSH_USER}@${SSH_HOST}:/tmp/lms-dnsmasq.conf"
$SSH "sudo mv /tmp/lms-dnsmasq.conf /etc/dnsmasq.d/lms.conf && sudo systemctl restart dnsmasq"

# ── 5. Start shared Caddy (creates lms-proxy network) ──────────────────────
echo "▶ Starting shared Caddy..."
$SSH "cd \$HOME/deploy/caddy && docker compose up -d"
echo "  Caddy started — lms-proxy network created."

# ── 6. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "✓ Bootstrap complete. Next steps:"
echo ""
echo "  1. Push to main or staging — GitHub Actions will write .env and deploy."
echo ""
echo "  2. On first deploy, stamp the DB (only if tables already exist):"
echo "     ssh ${SSH_USER}@${SSH_HOST}"
echo "     cd ~/deploy/production/lms"
echo "     docker compose run --rm migrate-prod flask db stamp head"
echo ""
echo "  3. Verify dnsmasq:"
echo "     ssh ${SSH_USER}@${SSH_HOST} 'dig yourdomain.example.com +short'"
echo ""
echo "  Ports:"
echo "     production DB:  127.0.0.1:5439"
echo "     staging DB:     127.0.0.1:5438"
echo "     production app: 127.0.0.1:5002"
echo "     staging app:    127.0.0.1:5001"
