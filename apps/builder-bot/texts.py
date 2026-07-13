from __future__ import annotations

from platform_core.config import Settings


def t_home(settings: Settings) -> str:
    mode = "🧪 <b>Test</b> · to'lov o'chiq" if not settings.payments_enabled else f"⭐ <b>{settings.subscription_price_stars} Stars</b> / {settings.subscription_days} kun"
    return (
        f"<b>{settings.brand_name}</b>\n"
        f"{mode}\n\n"
        "Mafia botingizni avtomatik hosting qilamiz.\n\n"
        "<b>Siz:</b> token berasiz\n"
        "<b>Biz:</b> deploy · db · restart · monitoring"
    )


def t_ask_token() -> str:
    return (
        "🔑 <b>Bot token</b>\n\n"
        "1. @BotFather → API token\n"
        "2. Shu yerga yuboring\n\n"
        "<i>Token xabar o'chiriladi. /cancel</i>"
    )


def t_checking() -> str:
    return "⏳ Token tekshirilmoqda…"


def t_invalid(err: str) -> str:
    return f"❌ <b>Token xato</b>\n\n{err}\n\nQayta yuboring yoki /cancel"


def t_deploying(username: str | None) -> str:
    name = f"@{username}" if username else "bot"
    return (
        f"🚀 <b>Deploy</b> · {name}\n\n"
        "⏳ Tayyorlanmoqda…\n"
        "<i>1–3 daqiqa. Shu chatdan chiqmang.</i>"
    )


def t_progress(username: str | None, step: str) -> str:
    name = f"@{username}" if username else "bot"
    return f"🚀 <b>Deploy</b> · {name}\n\n{step}"


def t_ready(username: str | None, days: int) -> str:
    name = f"@{username}" if username else "Bot"
    return (
        f"✅ <b>Tayyor</b> · {name}\n"
        f"⏱ {days} kun · status: <b>RUNNING</b>\n\n"
        "Guruhga admin qilib qo'shing → <code>/game</code>"
    )


def t_failed(err: str) -> str:
    short = (err or "Noma'lum xato")[:400]
    return f"❌ <b>Deploy xato</b>\n\n<code>{short}</code>\n\n/start qayta urinib ko'ring"


def t_status(
    username: str | None,
    status: str,
    days_left: int | None,
    sub_status: str | None,
    error: str | None = None,
) -> str:
    name = f"@{username}" if username else "—"
    days = "—" if days_left is None else str(days_left)
    icon = {
        "running": "🟢",
        "stopped": "⏸",
        "suspended": "🔴",
        "failed": "❌",
        "provisioning": "🟡",
        "pending": "⚪",
    }.get(status, "⚪")
    text = (
        f"{icon} <b>{name}</b>\n"
        f"Status: <b>{status.upper()}</b>\n"
        f"Obuna: <b>{sub_status or '—'}</b> · kun: <b>{days}</b>"
    )
    if error:
        text += f"\n\n⚠️ <code>{error[:200]}</code>"
    return text


def t_no_bot() -> str:
    return "Bot yo'q.\nPastdagi <b>🚀 Ochish</b> ni bosing."


def t_busy() -> str:
    return "⏳ Deploy allaqachon ketmoqda. Kuting…"


def t_need_sub() -> str:
    return "Avval <b>🚀 Ochish</b> ni bosing."


def t_cancelled() -> str:
    return "Bekor qilindi."


def t_support(url: str) -> str:
    return f"🆘 {url}"


def t_done_action(action: str) -> str:
    return f"✅ {action}"
