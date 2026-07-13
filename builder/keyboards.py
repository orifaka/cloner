from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🚀 Ochish"), KeyboardButton(text="📊 Status")],
        [KeyboardButton(text="🎛 Boshqaruv"), KeyboardButton(text="ℹ️ Yordam")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Admin")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def home_inline(*, payments_enabled: bool) -> InlineKeyboardMarkup:
    pay_btn = (
        InlineKeyboardButton(text="⭐ Obuna olish", callback_data="nav:open")
        if payments_enabled
        else InlineKeyboardButton(text="🚀 Bot ochish", callback_data="nav:open")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [pay_btn],
            [
                InlineKeyboardButton(text="📊 Status", callback_data="nav:status"),
                InlineKeyboardButton(text="🎛 Panel", callback_data="nav:panel"),
            ],
            [
                InlineKeyboardButton(text="🔑 Token", callback_data="nav:token"),
                InlineKeyboardButton(text="ℹ️ Yordam", callback_data="nav:help"),
            ],
        ]
    )


def control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Start", callback_data="ctl:start"),
                InlineKeyboardButton(text="⏹ Stop", callback_data="ctl:stop"),
                InlineKeyboardButton(text="🔁 Restart", callback_data="ctl:restart"),
            ],
            [
                InlineKeyboardButton(text="🧾 Log", callback_data="ctl:logs"),
                InlineKeyboardButton(text="💾 Backup", callback_data="ctl:backup"),
            ],
            [
                InlineKeyboardButton(text="🔑 Token yangilash", callback_data="nav:token"),
                InlineKeyboardButton(text="🔄 Yangilash", callback_data="nav:status"),
            ],
            [InlineKeyboardButton(text="🏠 Menyuga", callback_data="nav:home")],
        ]
    )


def status_kb() -> InlineKeyboardMarkup:
    return control_kb()


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Dashboard", callback_data="adm:dash"),
                InlineKeyboardButton(text="🤖 Botlar", callback_data="adm:bots"),
            ],
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users"),
                InlineKeyboardButton(text="💰 Payments", callback_data="adm:pays"),
            ],
            [
                InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:bc"),
                InlineKeyboardButton(text="🔄 Refresh", callback_data="adm:dash"),
            ],
            [InlineKeyboardButton(text="🏠 Menyuga", callback_data="nav:home")],
        ]
    )


def admin_bots_kb(deps: list, page: int = 0, per: int = 6) -> InlineKeyboardMarkup:
    chunk = deps[page * per : (page + 1) * per]
    rows: list[list[InlineKeyboardButton]] = []
    for d in chunk:
        icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "❌"}.get(d.status, "⚪")
        name = f"@{d.bot_username}" if d.bot_username else f"#{d.id}"
        rows.append(
            [InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"adm:bot:{d.id}")]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:bots:{page - 1}"))
    if (page + 1) * per < len(deps):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:bots:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="⬅️ Admin", callback_data="adm:menu"),
            InlineKeyboardButton(text="🏠", callback_data="nav:home"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_bot_actions_kb(dep_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️", callback_data=f"adm:act:start:{dep_id}"),
                InlineKeyboardButton(text="⏹", callback_data=f"adm:act:stop:{dep_id}"),
                InlineKeyboardButton(text="🔁", callback_data=f"adm:act:restart:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="🧾 Log", callback_data=f"adm:act:logs:{dep_id}"),
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"adm:act:del:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Botlar", callback_data="adm:bots"),
                InlineKeyboardButton(text="🛠 Admin", callback_data="adm:menu"),
            ],
        ]
    )


def confirm_kb(yes_data: str, no_data: str = "adm:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=yes_data),
                InlineKeyboardButton(text="❌ Yo'q", callback_data=no_data),
            ]
        ]
    )
