"""Premium SaaS copy — short, polished, no technical jargon."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from builder.config import Settings


def intro(s: Settings) -> str:
    price = s.subscription_price_stars
    days = s.subscription_days
    return (
        f"<b>{s.brand_name}</b>\n"
        f"<i>Premium Mafia Bot Hosting</i>\n\n"
        "O‘z Telegram Mafia botingizni bir necha daqiqada ishga tushiring.\n"
        "Hosting, xavfsizlik va texnik ishlar — bizda.\n\n"
        "<b>Nima olasiz</b>\n"
        "• Mustaqil bot (sizning token)\n"
        "• Avtomatik deploy & monitoring\n"
        "• Shifrlangan ma’lumotlar\n"
        "• 1-click start / stop / restart\n"
        "• Kunlik backup imkoniyati\n\n"
        "<b>Tarif</b>\n"
        f"⭐ <b>{price} Stars</b> · {days} kun\n\n"
        "<b>Xavfsizlik</b>\n"
        "Token AES shifrlanadi · izolyatsiya · faqat siz boshqarasiz\n\n"
        "Pastdan boshlang 👇"
    )


def help_text(s: Settings) -> str:
    return (
        "<b>Yordam</b>\n\n"
        "1. <b>Create Bot</b> — yangi bot\n"
        "2. BotFather token yuboring\n"
        "3. Deploy tugagach guruhga qo‘shing\n\n"
        "<b>My Bots</b> — boshqaruv\n"
        "<b>Subscription</b> — obuna & to‘lov\n"
        "<b>Dashboard</b> — umumiy holat\n\n"
        f"Support: {s.support_url}"
    )


def subscription_card(s: Settings, *, status: str, days_left: Optional[int], expires: Optional[str]) -> str:
    st = {
        "active": "🟢 Active",
        "grace": "🟡 Grace (suspend)",
        "expired": "🔴 Expired",
        "pending": "⚪ Pending",
        None: "⚪ No plan",
    }.get(status, f"⚪ {status or 'None'}")
    exp = expires or "—"
    left = "—" if days_left is None else f"{days_left} day(s)"
    return (
        "<b>Subscription</b>\n\n"
        f"Plan: <b>{s.subscription_price_stars} Stars / {s.subscription_days} days</b>\n"
        f"Status: {st}\n"
        f"Remaining: <b>{left}</b>\n"
        f"Expires: <code>{exp}</code>\n\n"
        "Grace: to‘lov bo‘lmasa bot <b>darhol suspend</b>.\n"
        "7 kun ichida renew → to‘liq tiklanadi.\n"
        "7 kundan keyin ma’lumotlar <b>o‘chiriladi</b>."
    )


def dashboard(stats: dict[str, Any]) -> str:
    return (
        "<b>Dashboard</b>\n\n"
        f"🤖 Bots: <b>{stats.get('bots', 0)}</b>\n"
        f"🟢 Online: <b>{stats.get('running', 0)}</b>\n"
        f"⏸ Stopped: <b>{stats.get('stopped', 0)}</b>\n"
        f"🔴 Suspended: <b>{stats.get('suspended', 0)}</b>\n"
        f"📅 Plan: <b>{stats.get('sub_status', '—')}</b>\n"
        f"⏳ Days left: <b>{stats.get('days_left', '—')}</b>"
    )


def ask_token() -> str:
    return (
        "<b>Bot token</b>\n\n"
        "1. Open @BotFather\n"
        "2. Copy API token\n"
        "3. Send it here\n\n"
        "Token is encrypted and removed from chat.\n"
        "You become the bot admin automatically.\n\n"
        "<i>/cancel to abort</i>"
    )


def deploy_progress(step: int, label: str) -> str:
    """step 1..6"""
    stages = [
        "Token Validation",
        "Database",
        "Configuration",
        "Deployment",
        "Health Check",
        "Online",
    ]
    lines = ["<b>Creating your bot</b>\n"]
    for i, name in enumerate(stages, start=1):
        if i < step:
            mark = "✅"
        elif i == step:
            mark = "⏳"
        else:
            mark = "○"
        extra = f" — <b>{label}</b>" if i == step and label else ""
        lines.append(f"{mark} {name}{extra}")
    return "\n".join(lines)


def deploy_done(username: Optional[str], days: int, expires: Optional[str] = None) -> str:
    name = f"@{username}" if username else "Your bot"
    exp = f"\nExpires: <code>{expires}</code>" if expires else ""
    return (
        f"<b>Online</b> · {name}\n\n"
        f"Status: 🟢 Running\n"
        f"Plan: {days} days{exp}\n\n"
        "Add the bot to your group as admin, then send /game.\n"
        "Manage anytime in <b>My Bots</b>."
    )


def bot_card(
    *,
    username: Optional[str],
    status: str,
    days_left: Optional[int],
    expires: Optional[str],
    cpu: str,
    ram: str,
    db_size: str,
    last_backup: str,
    error_friendly: Optional[str] = None,
) -> str:
    icon = {
        "running": "🟢 Online",
        "stopped": "⏸ Stopped",
        "suspended": "🔴 Suspended",
        "failed": "⚠️ Needs attention",
        "provisioning": "🟡 Deploying",
        "deleted": "🗑 Deleted",
    }.get(status, f"⚪ {status}")
    name = f"@{username}" if username else "Unnamed bot"
    left = "—" if days_left is None else f"{days_left} day(s)"
    text = (
        f"<b>{name}</b>\n\n"
        f"Status: {icon}\n"
        f"Subscription left: <b>{left}</b>\n"
        f"Expires: <code>{expires or '—'}</code>\n\n"
        f"CPU: <b>{cpu}</b>\n"
        f"RAM: <b>{ram}</b>\n"
        f"Database: <b>{db_size}</b>\n"
        f"Last backup: <b>{last_backup}</b>"
    )
    if error_friendly:
        text += f"\n\nℹ️ {error_friendly}"
    return text


def friendly_error(exc: BaseException | str) -> str:
    raw = str(exc).lower()
    if "token" in raw or "yaroqsiz" in raw or "formati" in raw:
        return (
            "<b>Token issue</b>\n\n"
            "The token looks invalid or expired.\n"
            "Create a new one in @BotFather and try again."
        )
    if "python" in raw or "runtime" in raw or "import" in raw:
        return (
            "<b>Server setup needed</b>\n\n"
            "Hosting environment is not ready yet.\n"
            "Please contact support or try again later."
        )
    if "permission" in raw or "ruxsat" in raw:
        return "<b>Access denied</b>\n\nYou don’t have permission for this action."
    if "not found" in raw or "yo'q" in raw or "topilmadi" in raw:
        return "<b>Not found</b>\n\nThis bot is no longer available. Create a new one."
    return (
        "<b>Something went wrong</b>\n\n"
        "Please try again in a moment.\n"
        "If it continues, open Support."
    )


def remind_7d(s: Settings) -> str:
    return (
        f"<b>Reminder</b> · 7 days left\n\n"
        f"Your plan ends soon. Renew for {s.subscription_price_stars} Stars "
        f"to keep hosting without interruption."
    )


def remind_3d(s: Settings) -> str:
    return (
        f"<b>Reminder</b> · 3 days left\n\n"
        f"Renew now ({s.subscription_price_stars} Stars) to avoid suspension."
    )


def remind_24h(s: Settings) -> str:
    return (
        "<b>Urgent</b> · 24 hours left\n\n"
        "After expiry your bot will be suspended immediately.\n"
        "Open Subscription → Renew."
    )


def remind_expired(s: Settings) -> str:
    return (
        "<b>Subscription expired</b>\n\n"
        "Your bot has been <b>suspended</b>.\n"
        "You have <b>7 days</b> to renew and fully restore it.\n\n"
        "After 7 days without payment, the bot, database and backups "
        "will be <b>permanently deleted</b> to free server resources.\n\n"
        f"Renew: {s.subscription_price_stars} Stars / {s.subscription_days} days"
    )


def remind_grace_daily(days_left: int) -> str:
    return (
        f"<b>Suspended</b> · {days_left} day(s) until permanent deletion\n\n"
        "Renew anytime to restore your bot and data."
    )


def delete_warning(username: Optional[str]) -> str:
    name = f"@{username}" if username else "this bot"
    return (
        f"<b>Delete {name}?</b>\n\n"
        "This will permanently remove:\n"
        "• Bot process\n"
        "• Database\n"
        "• Files & backups\n\n"
        "This cannot be undone."
    )


def settings_text(s: Settings, lang: str) -> str:
    pay = "Enabled" if s.payments_enabled else "Test mode (free deploy)"
    return (
        "<b>Settings</b>\n\n"
        f"Language: <b>{lang}</b>\n"
        f"Payments: <b>{pay}</b>\n"
        f"Support: {s.support_url}\n\n"
        "More options coming soon."
    )


def fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M UTC")
