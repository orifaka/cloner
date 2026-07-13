from __future__ import annotations

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from builder.billing import BillingService
from builder.config import Settings
from builder.deploy import DeploymentEngine
from builder.keyboards import (
    admin_bot_actions_kb,
    admin_bots_kb,
    admin_kb,
    confirm_kb,
    main_menu,
)
from builder.texts import t_admin_bot, t_admin_dash, t_denied
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
                await event.answer("🚫 Ruxsat yo'q", show_alert=True)
            except Exception:  # noqa: BLE001
                if event.message:
                    await event.message.answer(t_denied())
        else:
            await event.answer(t_denied())
        return False
    return True


def _menu(settings: Settings) -> object:
    return main_menu(is_admin=True)


@router.message(Command("admin"))
@router.message(F.text == "🛠 Admin")
async def admin_entry(
    message: Message,
    state: FSMContext,
    settings: Settings,
    billing: BillingService,
) -> None:
    await safe_delete_message(message)
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        await show(message.bot, message.chat.id, state, t_denied(), main_menu())
        return
    await state.clear()
    data = await billing.admin_overview()
    await show(
        message.bot,
        message.chat.id,
        state,
        t_admin_dash(data) + "\nKerakli bo'limni tanlang:",
        admin_kb(),
    )
    logger.info("admin open user=%s", message.from_user.id)


@router.callback_query(F.data == "adm:menu")
@router.callback_query(F.data == "adm:dash")
async def adm_dash(callback: CallbackQuery, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    await safe_cb(callback)
    if not await _guard(callback, settings) or not callback.message:
        return
    data = await billing.admin_overview()
    try:
        await callback.message.edit_text(t_admin_dash(data), reply_markup=admin_kb())
    except Exception:  # noqa: BLE001
        await show(callback.bot, callback.message.chat.id, state, t_admin_dash(data), admin_kb())


@router.callback_query(F.data.startswith("adm:bots"))
async def adm_bots(callback: CallbackQuery, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    await safe_cb(callback)
    if not await _guard(callback, settings) or not callback.message:
        return
    page = 0
    parts = (callback.data or "").split(":")
    if len(parts) == 3 and parts[2].isdigit():
        page = int(parts[2])
    data = await billing.admin_overview()
    deps = data["deps"]
    text = f"🤖 <b>Botlar</b> · jami {len(deps)}\nSahifa: {page + 1}"
    kb = admin_bots_kb(deps, page=page)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        await show(callback.bot, callback.message.chat.id, state, text, kb)


@router.callback_query(F.data.startswith("adm:bot:"))
async def adm_bot_detail(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    billing: BillingService,
) -> None:
    await safe_cb(callback)
    if not await _guard(callback, settings) or not callback.message:
        return
    dep_id = int((callback.data or "").split(":")[-1])
    dep = await billing.get_deployment(dep_id)
    if not dep:
        await callback.message.answer("Topilmadi")
        return
    text = t_admin_bot(dep)
    try:
        await callback.message.edit_text(text, reply_markup=admin_bot_actions_kb(dep_id))
    except Exception:  # noqa: BLE001
        await show(callback.bot, callback.message.chat.id, state, text, admin_bot_actions_kb(dep_id))


@router.callback_query(F.data.startswith("adm:act:"))
async def adm_bot_action(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    await safe_cb(callback)
    if not await _guard(callback, settings) or not callback.message:
        return
    # adm:act:restart:12
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        return
    action, dep_id_s = parts[2], parts[3]
    dep_id = int(dep_id_s)
    dep = await billing.get_deployment(dep_id)
    if not dep:
        await callback.message.answer("Topilmadi")
        return

    if action == "del":
        await callback.message.edit_text(
            f"🗑 #{dep_id} o'chirilsinmi?\n@{dep.bot_username or '—'}",
            reply_markup=confirm_kb(f"adm:act:delok:{dep_id}", "adm:bots"),
        )
        return

    try:
        if action == "start":
            await deploy.start(dep_id)
            msg = "✅ Start"
        elif action == "stop":
            await deploy.stop(dep_id)
            msg = "✅ Stop"
        elif action == "restart":
            await deploy.restart(dep_id)
            msg = "✅ Restart"
        elif action == "logs":
            text = await deploy.read_logs(dep_id, 35)
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            await callback.message.answer(f"<pre>{safe[-3500:]}</pre>" if safe else "Bo'sh")
            return
        elif action == "delok":
            await deploy.stop(dep_id)
            # soft delete via status
            from builder.db import get_session_factory
            from builder.models import Deployment
            from sqlalchemy import select

            sf = get_session_factory()
            async with sf() as s:
                d = await s.get(Deployment, dep_id)
                if d:
                    d.status = "deleted"
                    d.bot_token_encrypted = None
                    await s.commit()
            msg = "🗑 O'chirildi"
            await callback.message.edit_text(msg, reply_markup=admin_kb())
            logger.info("admin delete dep=%s by=%s", dep_id, callback.from_user.id if callback.from_user else 0)
            return
        else:
            msg = "?"
        dep2 = await billing.get_deployment(dep_id)
        await callback.message.edit_text(
            f"{msg}\n\n{t_admin_bot(dep2) if dep2 else ''}",
            reply_markup=admin_bot_actions_kb(dep_id),
        )
        logger.info("admin %s dep=%s", action, dep_id)
    except Exception as e:  # noqa: BLE001
        await callback.message.answer(f"❌ {e}")


@router.callback_query(F.data == "adm:users")
async def adm_users(callback: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(callback)
    if not await _guard(callback, settings) or not callback.message:
        return
    users = await billing.list_users(25)
    lines = ["👥 <b>Users</b> (oxirgi 25)\n"]
    for u in users:
        lines.append(
            f"• <code>{u.telegram_id}</code> @{u.username or '—'} · {u.full_name[:20]} · {u.role}"
        )
    text = "\n".join(lines) if users else "Users yo'q"
    try:
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except Exception:  # noqa: BLE001
        await callback.message.answer(text, reply_markup=admin_kb())


@router.callback_query(F.data == "adm:pays")
async def adm_pays(callback: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(callback)
    if not await _guard(callback, settings) or not callback.message:
        return
    data = await billing.admin_overview()
    text = (
        "💰 <b>Payments</b>\n\n"
        f"Success: <b>{data['payments']}</b>\n"
        f"Stars: <b>{data['stars']}</b>\n"
        f"Active subs: <b>{data['active_subs']}</b>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except Exception:  # noqa: BLE001
        await callback.message.answer(text, reply_markup=admin_kb())


@router.callback_query(F.data == "adm:bc")
async def adm_bc_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await safe_cb(callback)
    if not await _guard(callback, settings) or not callback.message:
        return
    await state.set_state(AdminStates.broadcast)
    await callback.message.answer(
        "📢 <b>Broadcast</b>\n\nBarcha userlarga yuboriladigan matnni yozing.\n/cancel"
    )


@router.message(AdminStates.broadcast, F.text)
async def adm_bc_send(
    message: Message,
    state: FSMContext,
    settings: Settings,
    billing: BillingService,
) -> None:
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("Bekor", reply_markup=_menu(settings))
        return
    users = await billing.list_users(500)
    ok = fail = 0
    for u in users:
        try:
            await message.bot.send_message(u.telegram_id, f"📢 <b>Xabar</b>\n\n{text}")
            ok += 1
        except Exception:  # noqa: BLE001
            fail += 1
    await state.clear()
    await message.answer(f"✅ Yuborildi: {ok}\n❌ Xato: {fail}", reply_markup=_menu(settings))
    logger.info("broadcast ok=%s fail=%s by=%s", ok, fail, message.from_user.id)
