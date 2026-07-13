#!/usr/bin/env bash
# Ubuntu 22.04/24.04 — Mafia Builder SaaS one-shot installer
# Usage (as root or sudo):
#   curl -fsSL ... | bash
#   OR: bash install-linux.sh
set -euo pipefail

APP_USER="${APP_USER:-mafiabot}"
APP_DIR="${APP_DIR:-/opt/mafia-builder}"
REPO_URL="${REPO_URL:-https://github.com/orifaka/cloner.git}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Root/sudo bilan ishga tushiring: sudo bash $0"
  exit 1
fi

echo "==> Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl build-essential python3 python3-venv python3-pip python3-dev sqlite3 ufw

echo "==> User: ${APP_USER}"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${APP_USER}"
fi

echo "==> App dir: ${APP_DIR}"
mkdir -p "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  sudo -u "${APP_USER}" git clone "${REPO_URL}" "${APP_DIR}"
else
  sudo -u "${APP_USER}" git -C "${APP_DIR}" pull --ff-only || true
fi

echo "==> venv + pip"
sudo -u "${APP_USER}" bash -lc "
  cd '${APP_DIR}'
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip setuptools wheel
  .venv/bin/pip install -r requirements.txt
  mkdir -p data/deployments data/backups
"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  AES=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  JWT=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
  cat > "${APP_DIR}/.env" << EOF
BUILDER_BOT_TOKEN=CHANGE_ME
BUILDER_BOT_USERNAME=
PUBLIC_BASE_URL=http://127.0.0.1
API_PUBLIC_URL=http://127.0.0.1:8080
PLATFORM_DATABASE_URL=sqlite+aiosqlite:///./data/platform.db
REDIS_URL=redis://127.0.0.1:6379/0
AES_SECRET_KEY=${AES}
JWT_SECRET_KEY=${JWT}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
ADMIN_TELEGRAM_IDS=
SUBSCRIPTION_PRICE_STARS=300
SUBSCRIPTION_DAYS=30
GRACE_PERIOD_HOURS=24
DATA_RETENTION_DAYS=30
PAYMENTS_ENABLED=false
DEPLOY_PROVIDER=process
TEMPLATE_PATH=./template/mafia-bot
DEPLOYMENTS_ROOT=./data/deployments
BACKUPS_ROOT=./data/backups
PYTHON_EXECUTABLE=python3
SUPPORT_URL=https://t.me
BRAND_NAME=True Mafia Builder
DEFAULT_LANGUAGE=uz
LOG_LEVEL=INFO
API_HOST=127.0.0.1
API_PORT=8080
EOF
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
  echo "==> .env yaratildi — BUILDER_BOT_TOKEN ni to'ldiring: nano ${APP_DIR}/.env"
fi

echo "==> systemd unit"
cat > /etc/systemd/system/mafia-builder.service << EOF
[Unit]
Description=Mafia Builder SaaS Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python -u apps/builder-bot/main.py
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=30
StandardOutput=append:${APP_DIR}/data/builder.out.log
StandardError=append:${APP_DIR}/data/builder.err.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mafia-builder.service

echo ""
echo "========================================"
echo "O'rnatish tugadi."
echo "1) nano ${APP_DIR}/.env  →  BUILDER_BOT_TOKEN=..."
echo "2) systemctl start mafia-builder"
echo "3) systemctl status mafia-builder"
echo "4) journalctl -u mafia-builder -f"
echo "========================================"
