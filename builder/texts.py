from __future__ import annotations

from builder.config import Settings


def t_home(s: Settings) -> str:
    mode = "🧪 Test · to'lov o'chiq" if not s.payments_enabled else f"⭐ {s.subscription_price_stars} Stars / {s.subscription_days} kun"
    return (
        f"<b>{s.brand_name}</b>\n"
        f"{mode}\n\n"
        "Mafia botingizni avtomatik hosting.\n"
        "<b>Siz:</b> token\n"
        "<b>Biz:</b> deploy · db · restart"
    )


def t_ask_token() -> str:
    return "🔑 <b>Bot token</b>\n@BotFather dan oling → yuboring\n<i>/cancel</i>"


def t_checking() -> str:
    return "⏳ Tekshirilmoqda…"


def t_invalid(err: str) -> str:
    return f"❌ <b>Token xato</b>\n{err}"


def t_deploying(username: str | None) -> str:
    return f"🚀 <b>Deploy</b> · @{username or 'bot'}\n⏳ 1–3 daqiqa…"


def t_progress(username: str | None, step: str) -> str:
    return f"🚀 <b>Deploy</b> · @{username or 'bot'}\n\n{step}"


def t_ready(username: str | None, days: int) -> str:
    return f"✅ <b>Tayyor</b> · @{username or 'bot'}\n⏱ {days} kun · RUNNING\nGuruhga qo'shing → /game"


def t_failed(err: str) -> str:
    return f"❌ <b>Deploy xato</b>\n<code>{(err or '?')[:400]}</code>\n/start"


def t_status(username: str | None, status: str, days: int | None, sub: str | None, err: str | None = None) -> str:
    icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "❌"}.get(status, "⚪")
    t = f"{icon} <b>@{username or '—'}</b>\nStatus: <b>{status}</b>\nObuna: <b>{sub or '—'}</b> · kun: <b>{days if days is not None else '—'}</b>"
    if err:
        t += f"\n⚠️ <code>{err[:200]}</code>"
    return t


def t_no_bot() -> str:
    return "Bot yo'q. <b>🚀 Ochish</b>"


def t_busy() -> str:
    return "⏳ Deploy ketmoqda…"


def t_need_sub() -> str:
    return "Avval <b>🚀 Ochish</b>"


def t_cancelled() -> str:
    return "Bekor."
