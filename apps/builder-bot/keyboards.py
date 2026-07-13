from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Ochish"), KeyboardButton(text="📊 Status")],
            [KeyboardButton(text="🔁 Restart"), KeyboardButton(text="🧾 Log")],
            [KeyboardButton(text="⏹ Stop"), KeyboardButton(text="▶️ Start")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def status_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁", callback_data="ctl:restart"),
                InlineKeyboardButton(text="⏹", callback_data="ctl:stop"),
                InlineKeyboardButton(text="▶️", callback_data="ctl:start"),
            ],
            [
                InlineKeyboardButton(text="🧾 Log", callback_data="ctl:logs"),
                InlineKeyboardButton(text="💾 Backup", callback_data="ctl:backup"),
            ],
        ]
    )
