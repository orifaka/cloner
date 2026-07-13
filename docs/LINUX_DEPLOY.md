# Linux (Ubuntu) da Mafia Builder SaaS ishga tushirish

> **Muhim:** Oddiy *shared hosting* (faqat cPanel + PHP, root/SSH yo‘q) da Telegram bot **ishlamaydi**.  
> Kerak: **Ubuntu 22.04/24.04 VPS** (SSH, Python 3.11+, doimiy process).  
> Minimal: 1–2 GB RAM, 1 vCPU, 20 GB disk.

---

## 0. Serverga ulanish

```bash
ssh root@YOUR_SERVER_IP
# yoki
ssh ubuntu@YOUR_SERVER_IP
```

---

## 1. Tizim paketlar

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl build-essential python3 python3-venv python3-pip python3-dev \
  sqlite3 ufw fail2ban
```

Python versiya:

```bash
python3 --version   # 3.11+ tavsiya
```

---

## 2. Foydalanuvchi (root da ishlamaslik)

```bash
sudo adduser --disabled-password --gecos "" mafiabot
sudo usermod -aG sudo mafiabot
sudo mkdir -p /opt/mafia-builder
sudo chown mafiabot:mafiabot /opt/mafia-builder
sudo su - mafiabot
```

---

## 3. Kodni olish

```bash
cd /opt/mafia-builder
git clone https://github.com/orifaka/cloner.git .
# agar papka bo'sh bo'lmasa:
# git clone https://github.com/orifaka/cloner.git /opt/mafia-builder
```

---

## 4. Virtualenv + dependencies

```bash
cd /opt/mafia-builder
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

---

## 5. `.env` sozlash

```bash
cp .env.example .env
nano .env
```

Minimal ishlaydigan `.env` (qiymatlarni o‘zingiznikiga almashtiring):

```env
BUILDER_BOT_TOKEN=123456:YOUR_BUILDER_BOT_TOKEN
BUILDER_BOT_USERNAME=YourBuilderBot

PUBLIC_BASE_URL=http://YOUR_SERVER_IP
API_PUBLIC_URL=http://YOUR_SERVER_IP:8080

PLATFORM_DATABASE_URL=sqlite+aiosqlite:///./data/platform.db

REDIS_URL=redis://127.0.0.1:6379/0

# generate:
# python3 -c "import secrets; print(secrets.token_hex(32))"
AES_SECRET_KEY=REPLACE_64_HEX_CHARS
JWT_SECRET_KEY=REPLACE_LONG_RANDOM_STRING_32plus
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

ADMIN_TELEGRAM_IDS=YOUR_TELEGRAM_ID

SUBSCRIPTION_PRICE_STARS=300
SUBSCRIPTION_DAYS=30
GRACE_PERIOD_HOURS=24
DATA_RETENTION_DAYS=30

# test: false | production to'lov: true
PAYMENTS_ENABLED=false

DEPLOY_PROVIDER=process
TEMPLATE_PATH=./template/mafia-bot
DEPLOYMENTS_ROOT=./data/deployments
BACKUPS_ROOT=./data/backups
PYTHON_EXECUTABLE=python3

SUPPORT_URL=https://t.me/your_support
BRAND_NAME=True Mafia Builder
DEFAULT_LANGUAGE=uz
LOG_LEVEL=INFO

API_HOST=127.0.0.1
API_PORT=8080
```

Kalitlarni generatsiya:

```bash
python3 -c "import secrets; print('AES_SECRET_KEY=' + secrets.token_hex(32)); print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
```

Papkalar:

```bash
mkdir -p data/deployments data/backups
chmod 700 data .env
```

---

## 6. Shared runtime (bir marta, deploy tezligi uchun)

```bash
cd /opt/mafia-builder
source .venv/bin/activate
python3 << 'PY'
from pathlib import Path
import sys
ROOT = Path("/opt/mafia-builder")
sys.path[:0] = [
    str(ROOT / "packages" / "core"),
    str(ROOT / "packages" / "deploy"),
]
from platform_core.config import clear_settings_cache, get_settings
from platform_core.database import get_session_factory
from platform_deploy.engine import DeploymentEngine

clear_settings_cache()
s = get_settings()
e = DeploymentEngine(s, get_session_factory(s))
e._ensure_shared_runtime(force=True)
print("OK", e._shared_python())
PY
```

---

## 7. Qo‘lda test (systemd dan oldin)

```bash
cd /opt/mafia-builder
source .venv/bin/activate
python apps/builder-bot/main.py
```

Telegramda botga `/start` yuboring. To‘xtatish: `Ctrl+C`.

---

## 8. systemd — doimiy ishlashi

Root yoki sudo bilan:

```bash
sudo tee /etc/systemd/system/mafia-builder.service > /dev/null << 'EOF'
[Unit]
Description=Mafia Builder SaaS Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mafiabot
Group=mafiabot
WorkingDirectory=/opt/mafia-builder
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/opt/mafia-builder/.env
ExecStart=/opt/mafia-builder/.venv/bin/python -u apps/builder-bot/main.py
Restart=always
RestartSec=5
# Deploy child bots need to spawn
KillMode=mixed
TimeoutStopSec=30
# Optional resource limits
# MemoryMax=1G

StandardOutput=append:/opt/mafia-builder/data/builder.out.log
StandardError=append:/opt/mafia-builder/data/builder.err.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mafia-builder
sudo systemctl start mafia-builder
sudo systemctl status mafia-builder --no-pager
```

Loglar:

```bash
sudo journalctl -u mafia-builder -f
# yoki
tail -f /opt/mafia-builder/data/builder.err.log
```

Boshqaruv:

```bash
sudo systemctl restart mafia-builder
sudo systemctl stop mafia-builder
sudo systemctl start mafia-builder
```

---

## 9. (Ixtiyoriy) Admin API

```bash
sudo tee /etc/systemd/system/mafia-api.service > /dev/null << 'EOF'
[Unit]
Description=Mafia Builder API
After=network-online.target mafia-builder.service

[Service]
Type=simple
User=mafiabot
Group=mafiabot
WorkingDirectory=/opt/mafia-builder
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/opt/mafia-builder/.env
Environment=PYTHONPATH=/opt/mafia-builder/packages/core:/opt/mafia-builder/packages/billing:/opt/mafia-builder/packages/deploy:/opt/mafia-builder/packages/monitoring
ExecStart=/opt/mafia-builder/.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mafia-api
```

---

## 10. Firewall

```bash
sudo ufw allow OpenSSH
# API ni faqat local qoldirsangiz 8080 ochmang
# sudo ufw allow 8080/tcp
sudo ufw enable
sudo ufw status
```

---

## 11. Yangilash (keyingi deploylar)

```bash
sudo systemctl stop mafia-builder
cd /opt/mafia-builder
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl start mafia-builder
```

---

## 12. Foydalanuvchi oqimi

1. Builder botga `/start`
2. `🚀 Ochish` (test rejimda to‘lov o‘chiq bo‘lsa)
3. BotFather token
4. Platforma avtomatik: copy template → `.env` → shared runtime → `python -m app.main`
5. Mijoz boti `data/deployments/<slug>/` da ishlaydi

Tenant bot log:

```bash
ls /opt/mafia-builder/data/deployments/
tail -f /opt/mafia-builder/data/deployments/*/bot.err.log
```

---

## 13. Production checklist

- [ ] `PAYMENTS_ENABLED=true` (Stars yoqilganda)
- [ ] Kuchli `AES_SECRET_KEY` / `JWT_SECRET_KEY`
- [ ] `ADMIN_TELEGRAM_IDS` to‘g‘ri
- [ ] `.env` huquqi `600`
- [ ] `systemctl enable` qilingan
- [ ] Backup: `data/` papkasini kunlik arxivlash
- [ ] Tokenlarni hech qachon git ga qo‘ymang

Backup misol (cron):

```bash
crontab -e
# har kuni 03:00
0 3 * * * tar -czf /home/mafiabot/backups/mafia-$(date +\%F).tar.gz -C /opt/mafia-builder data .env
```

---

## Shared hosting haqida

| Muhit | Ishlaydimi? |
|--------|-------------|
| Ubuntu VPS + SSH | ✅ Ha |
| Docker VPS | ✅ Ha (`DEPLOY_PROVIDER=docker`) |
| cPanel shared (faqat PHP) | ❌ Yo‘q |
| Python passenger (qisqa request) | ❌ Polling bot uchun yaroqsiz |

Agar faqat shared hosting bo‘lsa: **Timeweb / Aeza / Hetzner / DigitalOcean** da arzon Ubuntu VPS oling.

---

## Muammolar

**Bot javob bermaydi**
```bash
sudo systemctl status mafia-builder
tail -100 /opt/mafia-builder/data/builder.err.log
```

**Deploy runtime xato**
```bash
# shared runtime qayta
rm -rf /opt/mafia-builder/data/shared-runtime
# keyin bo'lim 6 ni qayta ishga tushiring
```

**Permission denied**
```bash
sudo chown -R mafiabot:mafiabot /opt/mafia-builder
```

**Conflict: boshqa joyda polling**
- Builder token faqat shu serverda ishlashi kerak (2 joyda polling bo‘lmasin).
