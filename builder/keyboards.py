from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="✨ Create Bot"), KeyboardButton(text="🤖 My Bots")],
        [KeyboardButton(text="💎 Subscription"), KeyboardButton(text="📊 Dashboard")],
        [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="❓ Support")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Admin")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def intro_kb(*, payments_on: bool) -> InlineKeyboardMarkup:
    primary = "⭐ Get Started" if payments_on else "✨ Create Bot"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=primary, callback_data="ux:create")],
            [
                InlineKeyboardButton(text="💎 Pricing", callback_data="ux:sub"),
                InlineKeyboardButton(text="🤖 My Bots", callback_data="ux:bots"),
            ],
            [
                InlineKeyboardButton(text="❓ Support", callback_data="ux:support"),
            ],
        ]
    )


def bot_actions_kb(dep_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Start", callback_data=f"bot:start:{dep_id}"),
                InlineKeyboardButton(text="⏹ Stop", callback_data=f"bot:stop:{dep_id}"),
                InlineKeyboardButton(text="🔁 Restart", callback_data=f"bot:restart:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Renew", callback_data="ux:renew"),
                InlineKeyboardButton(text="💾 Backup", callback_data=f"bot:backup:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="🧾 Logs", callback_data=f"bot:logs:{dep_id}"),
                InlineKeyboardButton(text="🗑 Delete Bot", callback_data=f"bot:delask:{dep_id}"),
            ],
            [InlineKeyboardButton(text="◀️ Back", callback_data="ux:bots")],
        ]
    )


def bots_list_kb(deps: list, page: int = 0, per: int = 5) -> InlineKeyboardMarkup:
    chunk = deps[page * per : (page + 1) * per]
    rows: list[list[InlineKeyboardButton]] = []
    for d in chunk:
        icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "⚠️"}.get(d.status, "⚪")
        name = f"@{d.bot_username}" if d.bot_username else f"Bot #{d.id}"
        rows.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"bot:view:{d.id}")])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"ux:bots:{page - 1}"))
    if (page + 1) * per < len(deps):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"ux:bots:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="✨ Create Bot", callback_data="ux:create")])
    rows.append([InlineKeyboardButton(text="🏠 Home", callback_data="ux:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(yes: str, no: str = "ux:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=yes),
                InlineKeyboardButton(text="❌ Cancel", callback_data=no),
            ]
        ]
    )


def sub_kb(*, payments_on: bool) -> InlineKeyboardMarkup:
    rows = []
    if payments_on:
        rows.append([InlineKeyboardButton(text="⭐ Pay / Renew · 300 Stars", callback_data="ux:pay")])
    else:
        rows.append([InlineKeyboardButton(text="✨ Continue (test mode)", callback_data="ux:create")])
    rows.append([InlineKeyboardButton(text="🏠 Home", callback_data="ux:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_error_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Try again", callback_data="ux:create")],
            [InlineKeyboardButton(text="❓ Support", callback_data="ux:support")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="ux:home")],
        ]
    )


def support_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Contact support", url=url if url.startswith("http") else f"https://t.me/{url.lstrip('@')}")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="ux:home")],
        ]
    )


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Overview", callback_data="adm:dash"),
                InlineKeyboardButton(text="🤖 All bots", callback_data="adm:bots"),
            ],
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users"),
                InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:bc"),
            ],
            [InlineKeyboardButton(text="🏠 Home", callback_data="ux:home")],
        ]
    )


def admin_bots_kb(deps: list, page: int = 0, per: int = 6) -> InlineKeyboardMarkup:
    chunk = deps[page * per : (page + 1) * per]
    rows: list[list[InlineKeyboardButton]] = []
    for d in chunk:
        icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "⚠️"}.get(d.status, "⚪")
        name = f"@{d.bot_username}" if d.bot_username else f"#{d.id}"
        rows.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"adm:bot:{d.id}")])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:bots:{page - 1}"))
    if (page + 1) * per < len(deps):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:bots:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🛠 Admin", callback_data="adm:dash")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_bot_actions_kb(dep_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️", callback_data=f"adm:act:start:{dep_id}"),
                InlineKeyboardButton(text="⏹", callback_data=f"adm:act:stop:{dep_id}"),
                InlineKeyboardButton(text="🔁", callback_data=f"adm:act:restart:{dep_id}"),
            ],
            [InlineKeyboardButton(text="🧾 Logs", callback_data=f"adm:act:logs:{dep_id}")],
            [InlineKeyboardButton(text="◀️ Bots", callback_data="adm:bots")],
        ]
    )
