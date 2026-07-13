from __future__ import annotations

from typing import Any, Optional

from builder.config import Settings


def t_home(s: Settings, *, is_admin: bool = False) -> str:
    mode = (
        "🧪 <b>Test rejim</b> · to'lov o'chiq"
        if not s.payments_enabled
        else f"⭐ <b>{s.subscription_price_stars} Stars</b> / {s.subscription_days} kun"
    )
    admin_line = "\n🛠 Sizda <b>Admin panel</b> bor" if is_admin else ""
    return (
        f"✨ <b>{s.brand_name}</b>\n"
        f"{mode}{admin_line}\n\n"
        "O'z Mafia botingizni bir zumda ishga tushiring.\n\n"
        "👤 <b>Siz:</b> token berasiz\n"
        "⚙️ <b>Biz:</b> hosting · deploy · restart\n"
        "👑 Yaratuvchi avtomatik <b>ADMIN</b> bo'ladi"
    )


def t_help(s: Settings) -> str:
    return (
        "ℹ️ <b>Yordam</b>\n\n"
        "1. <b>🚀 Ochish</b> — bot yaratish\n"
        "2. @BotFather token yuboring\n"
        "3. Deploy avtomatik\n"
        "4. Botingizni guruhga qo'shing → /game\n\n"
        "🎛 <b>Boshqaruv</b> — start/stop/restart/log\n"
        "🔑 Token yangilash — yangi token yuboring\n\n"
        f"Support: {s.support_url}\n"
        "Buyruqlar: /start /open /status /admin /cancel"
    )


def t_ask_token() -> str:
    return (
        "🔑 <b>BotFather token</b>\n\n"
        "1. @BotFather oching\n"
        "2. API token nusxalang\n"
        "3. Shu yerga yuboring\n\n"
        "⚠️ Token xabar o'chiriladi\n"
        "Siz botning <b>admini</b> bo'lasiz\n"
        "<i>/cancel</i>"
    )


def t_checking() -> str:
    return "⏳ Token tekshirilmoqda…"


def t_invalid(err: str) -> str:
    return f"❌ <b>Token xato</b>\n\n{err}\n\nQayta yuboring yoki /cancel"


def t_deploying(username: str | None) -> str:
    return f"🚀 <b>Deploy</b> · @{username or 'bot'}\n\n⏳ Tayyorlanmoqda…"


def t_progress(username: str | None, step: str) -> str:
    return f"🚀 <b>Deploy</b> · @{username or 'bot'}\n\n{step}"


def t_ready(username: str | None, days: int, owner_id: int | None = None) -> str:
    admin = f"\n👑 ADMIN_IDS: <code>{owner_id}</code>" if owner_id else ""
    return (
        f"✅ <b>Tayyor!</b> · @{username or 'bot'}\n"
        f"⏱ {days} kun · <b>RUNNING</b>{admin}\n\n"
        "Guruhga admin qilib qo'shing → <code>/game</code>\n"
        "Boshqaruv: 🎛 tugma"
    )


def t_failed(err: str) -> str:
    return f"❌ <b>Deploy xato</b>\n\n<code>{(err or '?')[:400]}</code>\n\n/start"


def t_status(
    username: str | None,
    status: str,
    days: int | None,
    sub: str | None,
    err: str | None = None,
    owner_id: int | None = None,
) -> str:
    icon = {
        "running": "🟢",
        "stopped": "⏸",
        "suspended": "🔴",
        "failed": "❌",
        "provisioning": "🟡",
    }.get(status, "⚪")
    t = (
        f"{icon} <b>@{username or '—'}</b>\n"
        f"Status: <b>{status.upper()}</b>\n"
        f"Obuna: <b>{sub or '—'}</b> · kun: <b>{days if days is not None else '—'}</b>"
    )
    if owner_id:
        t += f"\n👑 Admin: <code>{owner_id}</code>"
    if err:
        t += f"\n\n⚠️ <code>{err[:200]}</code>"
    return t


def t_no_bot() -> str:
    return "🤖 Bot hali yo'q.\n\n<b>🚀 Ochish</b> ni bosing."


def t_busy() -> str:
    return "⏳ Deploy allaqachon ketmoqda…"


def t_need_sub() -> str:
    return "Avval <b>🚀 Ochish</b> ni bosing."


def t_cancelled() -> str:
    return "Bekor qilindi."


def t_denied() -> str:
    return "🚫 Ruxsat yo'q."


def t_admin_dash(data: dict[str, Any]) -> str:
    return (
        "🛠 <b>Admin Dashboard</b>\n\n"
        f"👥 Users: <b>{data['users']}</b>\n"
        f"🤖 Deployments: <b>{data['deployments']}</b>\n"
        f"🟢 Running: <b>{data['running']}</b>\n"
        f"⏸ Stopped: <b>{data['stopped']}</b>\n"
        f"🔴 Suspended: <b>{data['suspended']}</b>\n"
        f"❌ Failed: <b>{data['failed']}</b>\n"
        f"📅 Active subs: <b>{data['active_subs']}</b>\n"
        f"⭐ Stars: <b>{data['stars']}</b> ({data['payments']} to'lov)\n"
    )


def t_admin_bot(dep, owner_tg: Optional[int] = None) -> str:
    icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "❌"}.get(dep.status, "⚪")
    uname = f"@{dep.bot_username}" if dep.bot_username else "—"
    owner = ""
    if dep.user:
        owner = f"\n👤 Owner: <code>{dep.user.telegram_id}</code> @{dep.user.username or '—'}"
    elif owner_tg:
        owner = f"\n👤 Owner: <code>{owner_tg}</code>"
    err = f"\n⚠️ <code>{dep.last_error[:180]}</code>" if dep.last_error else ""
    return (
        f"{icon} <b>{uname}</b>  #{dep.id}\n"
        f"Status: <b>{dep.status}</b>\n"
        f"Slug: <code>{dep.slug}</code>\n"
        f"PID: <code>{dep.process_pid or '—'}</code>{owner}{err}"
    )
