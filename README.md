# True Mafia Builder (pure Python)

Telegram bot: foydalanuvchi to‘laydi (yoki test rejim) → BotFather token beradi →  
platforma **avtomatik** Mafia bot instance ishga tushiradi.

- **Docker yo‘q**
- **nginx/traefik yo‘q**
- Faqat **Python**
- Ishga tushirish: **`python main.py`**

## Tuzilma

```
main.py                 ← ishga tushirish
builder/                ← platforma kodi
template/mafia-bot/     ← Mafia bot shablon (o'zgartirilmaydi)
data/                   ← db, deployments, logs
bot.log                 ← barcha loglar
.env
requirements.txt
```

## O‘rnatish

```bash
cd cloner
python3 -m venv .venv
# shared host: python3 -m venv --without-pip .venv && curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # BUILDER_BOT_TOKEN, AES_SECRET_KEY

mkdir -p data/deployments data/backups
```

## Ishga tushirish

```bash
python main.py
```

Fon:

```bash
nohup python main.py >> bot.log 2>&1 &
tail -f bot.log
```

## Foydalanish

1. `/start`
2. `🚀 Ochish` (test: `PAYMENTS_ENABLED=false`)
3. BotFather token
4. Deploy avtomatik → mijoz boti `data/deployments/<slug>/` da ishlaydi
5. Yaratuvchi avtomatik `ADMIN_IDS` ga yoziladi (Mafia bot admin)

## Admin panel (faqat siz)

`.env` da:

```env
ADMIN_TELEGRAM_IDS=SIZNING_TELEGRAM_ID
```

- `/admin` yoki **🛠 Admin** tugmasi (faqat shu ID)
- Dashboard, botlar, start/stop/restart, log, users, payments, broadcast

## To‘lov

- Test: `PAYMENTS_ENABLED=false`
- Production Stars: `PAYMENTS_ENABLED=true`
