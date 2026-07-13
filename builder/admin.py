from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from builder.billing import BillingService
from builder.config import Settings
from builder.copy import friendly_error
from builder.deploy import DeploymentEngine
from builder.keyboards import admin_bot_actions_kb, admin_bots_kb, admin_kb, main_menu
from builder.ui import safe_cb, safe_delete_message, show

logger = logging.getLogger("builder.admin")
router = Router(name="admin")


class AdminStates(StatesGroup):
    broadcast = State()


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_telegram_ids


async def _guard(event: Message | CallbackQuery, settings: Settings) -> bool:
    u = event.from_user
    if not u or not _is_admin(u.id, settings):
        if isinstance(event, CallbackQuery):
            await safe_cb(event)
            try:
                await event.answer("Access denied", show_alert=True)
            except Exception:  # noqa: BLE001
                pass
        else:
            await event.answer("Access denied.")
        return False
    return True


def _dash(data: dict) -> str:
    return (
        "<b>Admin</b>\n\n"
        f"Users: <b>{data['users']}</b>\n"
        f"Bots: <b>{data['deployments']}</b>\n"
        f"Online: <b>{data['running']}</b>\n"
        f"Suspended: <b>{data['suspended']}</b>\n"
        f"Failed: <b>{data['failed']}</b>\n"
        f"Stars: <b>{data['stars']}</b>"
    )


@router.message(Command("admin"))
@router.message(F.text == "🛠 Admin")
async def admin_entry(message: Message, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    await safe_delete_message(message)
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        await message.answer("Access denied.")
        return
    await state.clear()
    data = await billing.admin_overview()
    await show(message.bot, message.chat.id, state, _dash(data), admin_kb())


@router.callback_query(F.data == "adm:dash")
async def adm_dash(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    data = await billing.admin_overview()
    try:
        await cb.message.edit_text(_dash(data), reply_markup=admin_kb())
    except Exception:  # noqa: BLE001
        await cb.message.answer(_dash(data), reply_markup=admin_kb())


@router.callback_query(F.data.startswith("adm:bots"))
async def adm_bots(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    page = 0
    parts = (cb.data or "").split(":")
    if len(parts) == 3 and parts[2].isdigit():
        page = int(parts[2])
    data = await billing.admin_overview()
    text = f"<b>All bots</b> · {len(data['deps'])}"
    kb = admin_bots_kb(data["deps"], page=page)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:bot:"))
async def adm_bot(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    dep_id = int((cb.data or "").split(":")[-1])
    dep = await billing.get_deployment(dep_id)
    if not dep:
        await cb.message.answer("Not found.")
        return
    name = f"@{dep.bot_username}" if dep.bot_username else f"#{dep.id}"
    owner = f"<code>{dep.user.telegram_id}</code>" if dep.user else "—"
    text = f"<b>{name}</b>\nStatus: {dep.status}\nOwner: {owner}\nSlug: <code>{dep.slug}</code>"
    try:
        await cb.message.edit_text(text, reply_markup=admin_bot_actions_kb(dep_id))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=admin_bot_actions_kb(dep_id))


@router.callback_query(F.data.startswith("adm:act:"))
async def adm_act(cb: CallbackQuery, settings: Settings, billing: BillingService, deploy: DeploymentEngine) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    parts = (cb.data or "").split(":")
    if len(parts) < 4:
        return
    action, dep_id = parts[2], int(parts[3])
    try:
        if action == "start":
            await deploy.start(dep_id)
            await cb.message.answer("Started.")
        elif action == "stop":
            await deploy.stop(dep_id)
            await cb.message.answer("Stopped.")
        elif action == "restart":
            await deploy.restart(dep_id)
            await cb.message.answer("Restarted.")
        elif action == "logs":
            text = await deploy.read_logs(dep_id, 30)
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            await cb.message.answer(f"<pre>{safe[-3000:]}</pre>" if safe else "No logs.")
    except Exception as e:  # noqa: BLE001
        await cb.message.answer(friendly_error(e))


@router.callback_query(F.data == "adm:users")
async def adm_users(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    users = await billing.list_users(20)
    lines = ["<b>Users</b>\n"] + [f"• <code>{u.telegram_id}</code> @{u.username or '—'}" for u in users]
    try:
        await cb.message.edit_text("\n".join(lines), reply_markup=admin_kb())
    except Exception:  # noqa: BLE001
        await cb.message.answer("\n".join(lines), reply_markup=admin_kb())


@router.callback_query(F.data == "adm:bc")
async def adm_bc(cb: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings):
        return
    await state.set_state(AdminStates.broadcast)
    if cb.message:
        await cb.message.answer("Send broadcast text.\n/cancel")


@router.message(AdminStates.broadcast, F.text)
async def adm_bc_send(message: Message, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=main_menu(is_admin=True))
        return
    users = await billing.list_users(500)
    ok = fail = 0
    for u in users:
        try:
            await message.bot.send_message(u.telegram_id, f"<b>Announcement</b>\n\n{text}")
            ok += 1
        except Exception:  # noqa: BLE001
            fail += 1
    await state.clear()
    await message.answer(f"Sent: {ok} · Failed: {fail}", reply_markup=main_menu(is_admin=True))
