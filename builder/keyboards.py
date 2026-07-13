from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="✨ Bot ochish")],
        [KeyboardButton(text="🤖 Botlarim"), KeyboardButton(text="💎 Obuna")],
        [KeyboardButton(text="📊 Kabinet"), KeyboardButton(text="⚙️ Sozlamalar")],
        [KeyboardButton(text="❓ Yordam")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Admin")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Bo‘limni tanlang…",
    )


def intro_kb(*, payments_on: bool) -> InlineKeyboardMarkup:
    """Primary conversion keyboard on home screen."""
    if payments_on:
        primary = InlineKeyboardButton(
            text="⭐ 300 Stars · Bot ochish",
            callback_data="ux:create",
        )
    else:
        primary = InlineKeyboardButton(
            text="🚀 Bepul sinab ko‘rish",
            callback_data="ux:create",
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [primary],
            [
                InlineKeyboardButton(text="💎 Tariflar", callback_data="ux:sub"),
                InlineKeyboardButton(text="❓ Qanday?", callback_data="ux:support"),
            ],
            [InlineKeyboardButton(text="🤖 Botlarim", callback_data="ux:bots")],
        ]
    )


def bot_actions_kb(dep_id: int, *, status: str = "running") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="▶️ Start", callback_data=f"bot:start:{dep_id}"),
            InlineKeyboardButton(text="⏹ Stop", callback_data=f"bot:stop:{dep_id}"),
            InlineKeyboardButton(text="🔁 Restart", callback_data=f"bot:restart:{dep_id}"),
        ],
        [
            InlineKeyboardButton(text="⭐ Obunani yangilash", callback_data="ux:renew"),
        ],
        [
            InlineKeyboardButton(text="💾 Backup", callback_data=f"bot:backup:{dep_id}"),
            InlineKeyboardButton(text="📋 Loglar", callback_data=f"bot:logs:{dep_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"bot:delask:{dep_id}"),
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data=f"bot:view:{dep_id}"),
            InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home"),
        ],
    ]
    if status == "suspended":
        rows.insert(
            0,
            [InlineKeyboardButton(text="⭐ Hozir tiklash · to‘lov", callback_data="ux:pay")],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bots_list_kb(deps: list, page: int = 0, per: int = 5) -> InlineKeyboardMarkup:
    chunk = deps[page * per : (page + 1) * per]
    rows: list[list[InlineKeyboardButton]] = []
    for d in chunk:
        icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "⚠️"}.get(d.status, "⚪")
        name = f"@{d.bot_username}" if d.bot_username else f"Bot #{d.id}"
        rows.append([InlineKeyboardButton(text=f"{icon}  {name}", callback_data=f"bot:view:{d.id}")])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"ux:bots:{page - 1}"))
    if (page + 1) * per < len(deps):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"ux:bots:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="✨ Yangi bot ochish", callback_data="ux:create")])
    rows.append([InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(yes: str, no: str = "ux:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, tasdiqlayman", callback_data=yes),
                InlineKeyboardButton(text="↩️ Bekor", callback_data=no),
            ]
        ]
    )


def sub_kb(*, payments_on: bool, price: int = 300) -> InlineKeyboardMarkup:
    if payments_on:
        rows = [
            [InlineKeyboardButton(text=f"⭐ To‘lash · {price} Stars", callback_data="ux:pay")],
            [InlineKeyboardButton(text="✨ Bot ochish", callback_data="ux:create")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="🚀 Test rejimda davom etish", callback_data="ux:create")],
        ]
    rows.append([InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_error_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Qayta urinish", callback_data="ux:create")],
            [
                InlineKeyboardButton(text="❓ Yordam", callback_data="ux:support"),
                InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home"),
            ],
        ]
    )


def after_success_kb(dep_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Botni boshqarish", callback_data=f"bot:view:{dep_id}")],
            [InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home")],
        ]
    )


def support_kb(url: str) -> InlineKeyboardMarkup:
    link = url if url.startswith("http") else f"https://t.me/{url.lstrip('@')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Operator bilan bog‘lanish", url=link)],
            [
                InlineKeyboardButton(text="✨ Bot ochish", callback_data="ux:create"),
                InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home"),
            ],
        ]
    )


def empty_bots_kb(*, payments_on: bool) -> InlineKeyboardMarkup:
    label = "⭐ 300 Stars · Ochish" if payments_on else "🚀 Birinchi botimni ochish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data="ux:create")],
            [InlineKeyboardButton(text="💎 Tarif", callback_data="ux:sub")],
            [InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home")],
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
            [InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home")],
        ]
    )


def admin_bots_kb(deps: list, page: int = 0, per: int = 6) -> InlineKeyboardMarkup:
    chunk = deps[page * per : (page + 1) * per]
    rows: list[list[InlineKeyboardButton]] = []
    for d in chunk:
        icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "⚠️"}.get(d.status, "⚪")
        name = f"@{d.bot_username}" if d.bot_username else f"#{d.id}"
        rows.append([InlineKeyboardButton(text=f"{icon}  {name}", callback_data=f"adm:bot:{d.id}")])
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
            [InlineKeyboardButton(text="📋 Logs", callback_data=f"adm:act:logs:{dep_id}")],
            [InlineKeyboardButton(text="◀️", callback_data="adm:bots")],
        ]
    )
