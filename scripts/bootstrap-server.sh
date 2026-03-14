#!/usr/bin/env bash
# Bootstrap a fresh server for Yonca deployment.
# Run from project root: ./scripts/bootstrap-server.sh <ssh-host> <ssh-user>
#
# What it does:
#   1. Installs Docker on the remote (Ubuntu/Debian)
#   2. Adds user to docker group
#   3. Creates deploy directory structure for production and staging
#   4. Copies docker-compose.yml and deploy/Caddyfile
#   5. Installs dnsmasq prod config
#   6. Extracts static files from the Docker image
#   7. Prints next steps

set -euo pipefail

SSH_HOST="${1:?Usage: $0 <ssh-host> <ssh-user>}"
SSH_USER="${2:?Usage: $0 <ssh-host> <ssh-user>}"
SSH="ssh ${SSH_USER}@${SSH_HOST}"
SCP="scp"
GHCR_OWNER="${GHCR_OWNER:-$(grep GHCR_OWNER .env | cut -d= -f2)}"
IMAGE="ghcr.io/${GHCR_OWNER}/yonca:latest"

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
  $SSH "mkdir -p \$HOME/deploy/${ENV}/yonca/{deploy,data/postgres,data/caddy,flask_session,logs,static}"
done

# ── 3. Copy docker-compose.yml and Caddyfile ─────────────────────────────────
echo "▶ Copying compose and Caddyfile..."
for ENV in "${ENVS[@]}"; do
  DEST="${SSH_USER}@${SSH_HOST}:\$HOME/deploy/${ENV}/yonca"
  $SCP docker-compose.yml            "${SSH_USER}@${SSH_HOST}:~/deploy/${ENV}/yonca/docker-compose.yml"
  $SCP deploy/Caddyfile              "${SSH_USER}@${SSH_HOST}:~/deploy/${ENV}/yonca/deploy/Caddyfile"
done

# ── 4. Install dnsmasq config ─────────────────────────────────────────────────
echo "▶ Installing dnsmasq..."
$SSH "command -v dnsmasq" 2>/dev/null || $SSH "sudo apt-get install -y dnsmasq"
$SCP deploy/dnsmasq/prod.conf "${SSH_USER}@${SSH_HOST}:/tmp/yonca-dnsmasq.conf"
$SSH "sudo mv /tmp/yonca-dnsmasq.conf /etc/dnsmasq.d/yonca.conf && sudo systemctl restart dnsmasq"

# ── 5. Extract static files from image ───────────────────────────────────────
echo "▶ Extracting static files from image..."
$SSH "
  docker pull ${IMAGE} 2>/dev/null || true
  for ENV in ${ENVS[*]}; do
    docker run --rm \
      -v \$HOME/deploy/\${ENV}/yonca/static:/extract \
      ${IMAGE} \
      sh -c 'cp -r /app/static/. /extract/'
    echo \"  static → ~/deploy/\${ENV}/yonca/static/\"
  done
"

# ── 7. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "✓ Bootstrap complete. Next steps:"
echo ""
echo "  1. Push to main or staging — GitHub Actions will write .env and deploy."
echo ""
echo "  2. On first deploy, stamp the DB (only if tables already exist):"
echo "     ssh ${SSH_USER}@${SSH_HOST}"
echo "     cd ~/deploy/production/yonca"
echo "     docker compose --profile prod run --rm migrate-prod flask db stamp head"
echo ""
echo "  3. Verify dnsmasq:"
echo "     ssh ${SSH_USER}@${SSH_HOST} 'dig yonca-sdc.com +short'"
