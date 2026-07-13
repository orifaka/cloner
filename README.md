# True Mafia Builder SaaS

**Alohida Builder Bot** — foydalanuvchi faqat:

1. Telegram Stars to‘laydi  
2. BotFather token beradi  
3. O‘z Mafia botini ishlatadi  

**Qolgan hammasi avtomatik** (backend): papka, `.env`, venv, ishga tushirish, obuna, suspend/reactivate.

> ⚠️ **Muhim:** `template/mafia-bot` ichidagi **eski Mafia bot kodiga tegilmaydi**.  
> Deploy vaqtida shablon **nusxa** olinadi va faqat instance `.env` yoziladi.

---

## Arxitektura

```
User ──► Builder Bot (apps/builder-bot)
              │
              ├─ Billing (Telegram Stars)
              ├─ Token validate (getMe)
              └─ DeploymentEngine
                     │
                     ├─ copy template/mafia-bot  →  data/deployments/{slug}/
                     ├─ write .env only
                     ├─ pip install + start process/docker
                     └─ status: RUNNING
```

| Komponent | Yo‘l | Vazifa |
|-----------|------|--------|
| Builder Bot | `apps/builder-bot` | UX, to‘lov, token, panel |
| API | `apps/api` | Admin REST |
| Core | `packages/core` | models, AES, JWT, DB |
| Billing | `packages/billing` | Stars + lifecycle |
| Deploy | `packages/deploy` | avtomatik hosting |
| Template | `template/mafia-bot` | **read-only** sizning bot |

---

## Tezkor ishga tushirish (Windows / local)

```powershell
cd C:\Users\Sanjarbek\mafia-builder-saas
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# .env ichida BUILDER_BOT_TOKEN va AES/JWT kalitlarini to'ldiring
```

`.env` misol (local):

```env
BUILDER_BOT_TOKEN=123:ABC...
AES_SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
JWT_SECRET_KEY=change-me-jwt-super-secret-min-32-chars-long
ADMIN_TELEGRAM_IDS=SIZNING_TELEGRAM_ID
DEPLOY_PROVIDER=process
TEMPLATE_PATH=./template/mafia-bot
PLATFORM_DATABASE_URL=sqlite+aiosqlite:///./data/platform.db
```

Ishga tushirish:

```powershell
python apps\builder-bot\main.py
```

Admin API (ixtiyoriy):

```powershell
# boshqa terminal
set PYTHONPATH=packages\core;packages\billing;packages\deploy;packages\monitoring
uvicorn apps.api.main:app --host 0.0.0.0 --port 8080
```

---

## Foydalanuvchi oqimi

1. `/start` → tarif  
2. `🚀 Bot ochish` / `/buy` → **300 Stars** invoice  
3. To‘lov muvaffaqiyatli  
4. BotFather token yuborish  
5. Preview → **Deploy qil**  
6. Backend avtomatik: copy → `.env` → venv → `python -m app.main`  
7. `/mybot` — status, restart, logs, renew  

---

## Obuna qoidalari

- Narx: `SUBSCRIPTION_PRICE_STARS` (default 300)  
- Muddat: 30 kun  
- Eslatma: 7 kun / 3 kun / 24 soat  
- Grace period: `GRACE_PERIOD_HOURS`  
- Expired → container/process **stop** (suspend)  
- `/renew` → to‘lov → avtomatik **reactivate**  

---

## Deploy provider

| `DEPLOY_PROVIDER` | Qachon |
|-------------------|--------|
| `process` | Windows / oddiy VPS (default) |
| `docker` | Ubuntu + Docker (production) |

Template **o‘zgartirilmaydi**. Har bir mijoz: `data/deployments/{slug}/`.

---

## Xavfsizlik

- Bot tokenlar **AES-256-GCM** bilan shifrlangan  
- Token xabari chatdan o‘chirishga harakat qilinadi  
- Admin API: JWT Bearer  
- Audit / activity loglar  

---

## Production (Ubuntu + Docker Compose)

```bash
cd /opt/mafia-builder-saas
cp .env.example .env
# sozlang: BUILDER_BOT_TOKEN, AES, JWT, ADMIN ids
# DEPLOY_PROVIDER=docker
# PLATFORM_DATABASE_URL=postgresql+asyncpg://mafia:mafia_secret@postgres:5432/platform

docker compose -f infra/docker-compose.yml up -d --build
```

---

## Buyruqlar (Builder bot)

| Buyruq | Ma’no |
|--------|--------|
| `/start` | Menyu |
| `/buy` | To‘lov |
| `/token` | Token kiritish |
| `/mybot` | Status |
| `/restart` `/stopbot` `/startbot` | Boshqaruv |
| `/logs` `/backup` | Diagnostika |
| `/renew` | Obuna yangilash |
| `/admin_stats` | Faqat admin |

---

## Eslatma

- Bu **SaaS builder** — o‘yin mantiqi `template/mafia-bot` da qoladi.  
- Uchinchi tomon botlari clone qilinmaydi.  
- Har yangi bot — **mustaqil instance** + foydalanuvchi o‘z tokeni.  
