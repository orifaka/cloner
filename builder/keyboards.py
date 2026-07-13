from __future__ import annotations

from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="✨ Bot ochish")],
        [KeyboardButton(text="🤖 Botlarim"), KeyboardButton(text="💎 Obuna")],
        [KeyboardButton(text="🎁 Referal"), KeyboardButton(text="🏷 Promokod")],
        [KeyboardButton(text="📋 To‘lovlar"), KeyboardButton(text="📊 Kabinet")],
        [KeyboardButton(text="❓ FAQ"), KeyboardButton(text="💬 Support")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Admin")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Tanlang…",
    )


def intro_kb(*, payments_on: bool, price: int = 300) -> InlineKeyboardMarkup:
    primary = (
        InlineKeyboardButton(text=f"⭐ {price}★ · Hozir ochish", callback_data="ux:create")
        if payments_on
        else InlineKeyboardButton(text="🚀 Bepul sinab ko‘rish", callback_data="ux:create")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [primary],
            [
                InlineKeyboardButton(text="💎 Tarif", callback_data="ux:sub"),
                InlineKeyboardButton(text="❓ FAQ", callback_data="ux:faq"),
            ],
            [
                InlineKeyboardButton(text="🎁 Referal", callback_data="ux:ref"),
                InlineKeyboardButton(text="🤖 Botlarim", callback_data="ux:bots"),
            ],
        ]
    )


def bot_actions_kb(dep_id: int, *, status: str = "running", bot_username: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if bot_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text="➕ Guruhga qo‘shish",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                )
            ]
        )
    if status == "suspended":
        rows.append([InlineKeyboardButton(text="⭐ Hozir tiklash", callback_data="ux:pay")])
    rows.extend(
        [
            [
                InlineKeyboardButton(text="▶️", callback_data=f"bot:start:{dep_id}"),
                InlineKeyboardButton(text="⏹", callback_data=f"bot:stop:{dep_id}"),
                InlineKeyboardButton(text="🔁", callback_data=f"bot:restart:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="⭐ Yangilash", callback_data="ux:renew"),
                InlineKeyboardButton(text="💾 Backup", callback_data=f"bot:backup:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="📋 Log", callback_data=f"bot:logs:{dep_id}"),
                InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"bot:delask:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄", callback_data=f"bot:view:{dep_id}"),
                InlineKeyboardButton(text="🏠", callback_data="ux:home"),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_success_kb(dep_id: int, bot_username: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if bot_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text="➕ Guruhga qo‘shish",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🤖 Boshqaruv paneli", callback_data=f"bot:view:{dep_id}")])
    rows.append([InlineKeyboardButton(text="🏠 Menyuga", callback_data="ux:home")])
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
    rows.append([InlineKeyboardButton(text="✨ Yangi bot", callback_data="ux:create")])
    rows.append([InlineKeyboardButton(text="🏠", callback_data="ux:home")])
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
            [InlineKeyboardButton(text=f"⭐ To‘lash · {price}★", callback_data="ux:pay")],
            [InlineKeyboardButton(text="✨ Bot ochish", callback_data="ux:create")],
            [InlineKeyboardButton(text="🎁 Referal", callback_data="ux:ref")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="🚀 Testda davom", callback_data="ux:create")],
            [InlineKeyboardButton(text="🎁 Referal", callback_data="ux:ref")],
        ]
    rows.append([InlineKeyboardButton(text="🏠", callback_data="ux:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_error_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Qayta", callback_data="ux:create")],
            [
                InlineKeyboardButton(text="❓ FAQ", callback_data="ux:faq"),
                InlineKeyboardButton(text="💬 Support", callback_data="ux:support"),
            ],
            [InlineKeyboardButton(text="🏠", callback_data="ux:home")],
        ]
    )


def empty_bots_kb(*, payments_on: bool) -> InlineKeyboardMarkup:
    label = "⭐ Birinchi botni ochish" if payments_on else "🚀 Birinchi botimni ochish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data="ux:create")],
            [InlineKeyboardButton(text="❓ FAQ", callback_data="ux:faq")],
            [InlineKeyboardButton(text="🏠", callback_data="ux:home")],
        ]
    )


def support_kb(url: str) -> InlineKeyboardMarkup:
    link = url if url.startswith("http") else f"https://t.me/{url.lstrip('@')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Operator", url=link)],
            [
                InlineKeyboardButton(text="❓ FAQ", callback_data="ux:faq"),
                InlineKeyboardButton(text="✨ Ochish", callback_data="ux:create"),
            ],
            [InlineKeyboardButton(text="🏠", callback_data="ux:home")],
        ]
    )


def referral_kb(link: str) -> InlineKeyboardMarkup:
    share = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote('Mafia bot hosting — chegirma bilan och!', safe='')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Ulashish", url=share)],
            [InlineKeyboardButton(text="✨ Bot ochish", callback_data="ux:create")],
            [InlineKeyboardButton(text="🏠", callback_data="ux:home")],
        ]
    )


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Overview", callback_data="adm:dash"),
                InlineKeyboardButton(text="🤖 Bots", callback_data="adm:bots"),
            ],
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users"),
                InlineKeyboardButton(text="📢 BC", callback_data="adm:bc"),
            ],
            [InlineKeyboardButton(text="🏠", callback_data="ux:home")],
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
    rows.append([InlineKeyboardButton(text="🛠", callback_data="adm:dash")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_bot_actions_kb(dep_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️", callback_data=f"adm:act:start:{dep_id}"),
                InlineKeyboardButton(text="⏹", callback_data=f"adm:act:stop:{dep_id}"),
                InlineKeyboardButton(text="🔁", callback_data=f"adm:act:restart:{dep_id}"),
            ],
            [InlineKeyboardButton(text="📋", callback_data=f"adm:act:logs:{dep_id}")],
            [InlineKeyboardButton(text="◀️", callback_data="adm:bots")],
        ]
    )
