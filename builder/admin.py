"""
Premium Admin Panel — only ADMIN_TELEGRAM_IDS.
Dashboard · Bots · Users · Payments · Broadcast · System · Actions
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from builder.billing import BillingService, as_utc
from builder.config import Settings
from builder.copy import friendly_error
from builder.deploy import DeploymentEngine
from builder.keyboards import main_menu
from builder.ui import safe_cb, safe_delete_message, show

logger = logging.getLogger("builder.admin")
router = Router(name="admin")

DIV = "━━━━━━━━━━━━━━━━"


class AdminStates(StatesGroup):
    broadcast = State()
    msg_owner = State()
    grant_days = State()


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_telegram_ids


async def _guard(event: Message | CallbackQuery, settings: Settings) -> bool:
    u = event.from_user
    if not u or not _is_admin(u.id, settings):
        if isinstance(event, CallbackQuery):
            await safe_cb(event)
            try:
                await event.answer("🚫 Faqat admin", show_alert=True)
            except Exception:  # noqa: BLE001
                pass
        else:
            await event.answer("🚫 Admin panel faqat egasi uchun.")
        return False
    return True


def admin_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Dashboard", callback_data="adm:dash"),
                InlineKeyboardButton(text="🖥 System", callback_data="adm:sys"),
            ],
            [
                InlineKeyboardButton(text="🤖 Botlar", callback_data="adm:bots:0"),
                InlineKeyboardButton(text="🔴 Suspended", callback_data="adm:botsf:suspended:0"),
            ],
            [
                InlineKeyboardButton(text="🟢 Online", callback_data="adm:botsf:running:0"),
                InlineKeyboardButton(text="⚠️ Failed", callback_data="adm:botsf:failed:0"),
            ],
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users:0"),
                InlineKeyboardButton(text="💰 Payments", callback_data="adm:pays"),
            ],
            [
                InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:bc"),
                InlineKeyboardButton(text="🔄 Refresh", callback_data="adm:dash"),
            ],
            [InlineKeyboardButton(text="🏠 User menyu", callback_data="ux:home")],
        ]
    )


def admin_bots_kb(deps: list, page: int = 0, per: int = 6, filt: str = "all") -> InlineKeyboardMarkup:
    if filt != "all":
        deps = [d for d in deps if d.status == filt]
    chunk = deps[page * per : (page + 1) * per]
    rows: list[list[InlineKeyboardButton]] = []
    for d in chunk:
        icon = {
            "running": "🟢",
            "stopped": "⏸",
            "suspended": "🔴",
            "failed": "⚠️",
            "provisioning": "🟡",
        }.get(d.status, "⚪")
        name = f"@{d.bot_username}" if d.bot_username else f"#{d.id}"
        rows.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"adm:bot:{d.id}")])
    nav: list[InlineKeyboardButton] = []
    prefix = f"adm:botsf:{filt}" if filt != "all" else "adm:bots"
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page - 1}"))
    if (page + 1) * per < len(deps):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="🛠 Admin", callback_data="adm:menu"),
            InlineKeyboardButton(text="🔄", callback_data=f"{prefix}:{page}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_bot_kb(dep_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Start", callback_data=f"adm:act:start:{dep_id}"),
                InlineKeyboardButton(text="⏹ Stop", callback_data=f"adm:act:stop:{dep_id}"),
                InlineKeyboardButton(text="🔁 Restart", callback_data=f"adm:act:restart:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="📋 Log", callback_data=f"adm:act:logs:{dep_id}"),
                InlineKeyboardButton(text="💾 Backup", callback_data=f"adm:act:backup:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="📨 Owner", callback_data=f"adm:msg:{dep_id}"),
                InlineKeyboardButton(text="➕ +7 kun", callback_data=f"adm:act:days7:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="🗑 Purge", callback_data=f"adm:act:delask:{dep_id}"),
            ],
            [
                InlineKeyboardButton(text="◀️ Botlar", callback_data="adm:bots:0"),
                InlineKeyboardButton(text="🛠", callback_data="adm:menu"),
            ],
        ]
    )


def admin_users_kb(page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️", callback_data=f"adm:users:{max(0, page - 1)}"),
                InlineKeyboardButton(text="▶️", callback_data=f"adm:users:{page + 1}"),
            ],
            [InlineKeyboardButton(text="🛠 Admin", callback_data="adm:menu")],
        ]
    )


def confirm_kb(yes: str, no: str = "adm:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=yes),
                InlineKeyboardButton(text="❌ Yo‘q", callback_data=no),
            ]
        ]
    )


def _dash(data: dict, settings: Settings) -> str:
    return (
        f"🛠 <b>Admin Panel</b>\n"
        f"<i>{settings.brand_name}</i>\n"
        f"{DIV}\n\n"
        f"<b>Biznes</b>\n"
        f"👥 Users: <b>{data['users']}</b>\n"
        f"💎 Active sub: <b>{data['active_subs']}</b>\n"
        f"⭐ Stars jami: <b>{data['stars']}</b>\n"
        f"💳 To‘lovlar: <b>{data['payments']}</b>\n\n"
        f"<b>Infratuzilma</b>\n"
        f"🤖 Deployments: <b>{data['deployments']}</b>\n"
        f"🟢 Online: <b>{data['running']}</b>\n"
        f"⏸ Stopped: <b>{data['stopped']}</b>\n"
        f"🔴 Suspended: <b>{data['suspended']}</b>\n"
        f"⚠️ Failed: <b>{data['failed']}</b>\n"
        f"🟡 Provisioning: <b>{data.get('provisioning', 0)}</b>\n\n"
        f"{DIV}\n"
        f"Faqat siz ko‘rasiz · /admin"
    )


def _system() -> str:
    try:
        import psutil
        import shutil

        cpu = psutil.cpu_percent(interval=0.3)
        vm = psutil.virtual_memory()
        disk = shutil.disk_usage(".")
        return (
            f"🖥 <b>System</b>\n{DIV}\n\n"
            f"CPU: <b>{cpu:.0f}%</b>\n"
            f"RAM: <b>{vm.percent:.0f}%</b> "
            f"({vm.used // (1024**2)}/{vm.total // (1024**2)} MB)\n"
            f"Disk: <b>{disk.used / (1024**3):.1f}/{disk.total / (1024**3):.1f} GB</b> "
            f"({disk.used * 100 // disk.total}%)\n"
            f"Time: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>"
        )
    except Exception as e:  # noqa: BLE001
        return f"🖥 System\n\nMa’lumot olinmadi: {e}"


def _bot_detail(dep, metrics: dict | None = None) -> str:
    name = f"@{dep.bot_username}" if dep.bot_username else f"Bot #{dep.id}"
    owner = "—"
    if dep.user:
        owner = f"<code>{dep.user.telegram_id}</code> @{dep.user.username or '—'}"
    m = metrics or {}
    err = f"\n⚠️ <code>{(dep.last_error or '')[:160]}</code>" if dep.last_error else ""
    return (
        f"🤖 <b>{name}</b>  #{dep.id}\n"
        f"{DIV}\n\n"
        f"Status: <b>{dep.status}</b>\n"
        f"Owner: {owner}\n"
        f"Slug: <code>{dep.slug}</code>\n"
        f"PID: <code>{dep.process_pid or '—'}</code>\n"
        f"CPU: <b>{m.get('cpu', '—')}</b> · RAM: <b>{m.get('ram', '—')}</b>\n"
        f"DB: <b>{m.get('db_size', '—')}</b>\n"
        f"Backup: <b>{m.get('last_backup', '—')}</b>{err}"
    )


# ── Entry ──────────────────────────────────────────────

@router.message(Command("admin"))
@router.message(F.text == "🛠 Admin")
async def admin_entry(message: Message, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    await safe_delete_message(message)
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        await message.answer("🚫 Admin panel faqat egasi uchun.\n`.env` → ADMIN_TELEGRAM_IDS")
        return
    await state.clear()
    data = await billing.admin_overview()
    await show(message.bot, message.chat.id, state, _dash(data, settings), admin_home_kb())
    logger.info("admin open tg=%s", message.from_user.id)


@router.callback_query(F.data == "adm:menu")
@router.callback_query(F.data == "adm:dash")
async def adm_dash(cb: CallbackQuery, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    data = await billing.admin_overview()
    text = _dash(data, settings)
    try:
        await cb.message.edit_text(text, reply_markup=admin_home_kb())
    except Exception:  # noqa: BLE001
        await show(cb.bot, cb.message.chat.id, state, text, admin_home_kb())


@router.callback_query(F.data == "adm:sys")
async def adm_sys(cb: CallbackQuery, settings: Settings) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    try:
        await cb.message.edit_text(_system(), reply_markup=admin_home_kb())
    except Exception:  # noqa: BLE001
        await cb.message.answer(_system(), reply_markup=admin_home_kb())


# ── Bots ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:bots"))
async def adm_bots(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    page = 0
    parts = (cb.data or "").split(":")
    # adm:bots:0  or adm:bots
    if len(parts) >= 3 and parts[2].isdigit():
        page = int(parts[2])
    data = await billing.admin_overview()
    deps = [d for d in data["deps"] if d.status != "deleted"]
    text = f"🤖 <b>Barcha botlar</b> · {len(deps)}\nSahifa {page + 1}"
    kb = admin_bots_kb(deps, page=page, filt="all")
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:botsf:"))
async def adm_bots_filter(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    # adm:botsf:running:0
    parts = (cb.data or "").split(":")
    filt = parts[2] if len(parts) > 2 else "running"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    data = await billing.admin_overview()
    deps = [d for d in data["deps"] if d.status != "deleted"]
    filtered = [d for d in deps if d.status == filt]
    text = f"🤖 <b>{filt.upper()}</b> · {len(filtered)}"
    kb = admin_bots_kb(deps, page=page, filt=filt)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:bot:"))
async def adm_bot_detail(
    cb: CallbackQuery,
    settings: Settings,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    dep_id = int((cb.data or "").split(":")[-1])
    dep = await billing.get_deployment(dep_id)
    if not dep:
        await cb.message.answer("Topilmadi.")
        return
    metrics = deploy.metrics(dep.id, dep.project_path, dep.process_pid, dep.slug)
    text = _bot_detail(dep, metrics)
    try:
        await cb.message.edit_text(text, reply_markup=admin_bot_kb(dep_id))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=admin_bot_kb(dep_id))


@router.callback_query(F.data.startswith("adm:act:"))
async def adm_act(
    cb: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    parts = (cb.data or "").split(":")
    if len(parts) < 4:
        return
    action, dep_id = parts[2], int(parts[3])
    dep = await billing.get_deployment(dep_id)

    if action == "delask":
        name = f"@{dep.bot_username}" if dep and dep.bot_username else f"#{dep_id}"
        await cb.message.edit_text(
            f"🗑 <b>{name}</b> to‘liq o‘chirilsinmi?\n\nDB + fayllar + backup yo‘qoladi.",
            reply_markup=confirm_kb(f"adm:act:purge:{dep_id}", f"adm:bot:{dep_id}"),
        )
        return

    try:
        if action == "start":
            await deploy.start(dep_id)
            note = "✅ Start"
        elif action == "stop":
            await deploy.stop(dep_id)
            note = "✅ Stop"
        elif action == "restart":
            await deploy.restart(dep_id)
            note = "✅ Restart"
        elif action == "backup":
            path = await deploy.backup(dep_id)
            note = f"💾 <code>{path.name}</code>"
        elif action == "logs":
            text = await deploy.read_logs(dep_id, 40)
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            await cb.message.answer(f"<pre>{safe[-3500:]}</pre>" if safe else "Log yo‘q.")
            return
        elif action == "days7":
            if dep and dep.user:
                await billing.grant_bonus_days(dep.user.telegram_id, 7)
                note = "➕ +7 kun berildi"
            else:
                note = "Owner topilmadi"
        elif action == "purge":
            await deploy.purge(dep_id)
            await cb.message.edit_text("🗑 Purge qilindi.", reply_markup=admin_home_kb())
            logger.info("admin purge dep=%s by=%s", dep_id, cb.from_user.id if cb.from_user else 0)
            return
        else:
            note = "OK"
        await cb.message.answer(note)
        dep2 = await billing.get_deployment(dep_id)
        if dep2:
            metrics = deploy.metrics(dep2.id, dep2.project_path, dep2.process_pid, dep2.slug)
            await cb.message.answer(_bot_detail(dep2, metrics), reply_markup=admin_bot_kb(dep_id))
        logger.info("admin %s dep=%s", action, dep_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("admin act")
        await cb.message.answer(friendly_error(e))


@router.callback_query(F.data.startswith("adm:msg:"))
async def adm_msg_start(cb: CallbackQuery, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    dep_id = int((cb.data or "").split(":")[-1])
    dep = await billing.get_deployment(dep_id)
    if not dep or not dep.user:
        await cb.message.answer("Owner yo‘q.")
        return
    await state.set_state(AdminStates.msg_owner)
    await state.update_data(msg_owner_tg=dep.user.telegram_id, msg_dep=dep_id)
    await cb.message.answer(
        f"📨 Owner <code>{dep.user.telegram_id}</code> ga xabar yozing.\n/cancel"
    )


@router.message(AdminStates.msg_owner, F.text)
async def adm_msg_send(message: Message, state: FSMContext, settings: Settings) -> None:
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("Bekor.", reply_markup=main_menu(is_admin=True))
        return
    data = await state.get_data()
    tg = data.get("msg_owner_tg")
    await state.clear()
    if not tg:
        await message.answer("Xato.")
        return
    try:
        await message.bot.send_message(
            int(tg),
            f"📩 <b>Admin xabari</b>\n\n{text}",
        )
        await message.answer("✅ Yuborildi.", reply_markup=main_menu(is_admin=True))
    except Exception as e:  # noqa: BLE001
        await message.answer(friendly_error(e), reply_markup=main_menu(is_admin=True))


# ── Users / Payments ───────────────────────────────────

@router.callback_query(F.data.startswith("adm:users"))
async def adm_users(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    page = 0
    parts = (cb.data or "").split(":")
    if len(parts) >= 3 and parts[2].isdigit():
        page = int(parts[2])
    users = await billing.list_users(200)
    per = 15
    chunk = users[page * per : (page + 1) * per]
    lines = [f"👥 <b>Users</b> · jami {len(users)}\n{DIV}\n"]
    for u in chunk:
        lines.append(
            f"• <code>{u.telegram_id}</code> @{u.username or '—'} · "
            f"{(u.full_name or '')[:18]} · {u.role}"
        )
    if not chunk:
        lines.append("Bo‘sh sahifa.")
    text = "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=admin_users_kb(page))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=admin_users_kb(page))


@router.callback_query(F.data == "adm:pays")
async def adm_pays(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    data = await billing.admin_overview()
    # last payments via raw list
    from sqlalchemy import select
    from builder.db import get_session_factory
    from builder.models import Payment, User

    sf = get_session_factory()
    async with sf() as s:
        pays = (
            await s.execute(select(Payment).order_by(Payment.id.desc()).limit(20))
        ).scalars().all()
        lines = [
            f"💰 <b>Payments</b>\n{DIV}\n",
            f"Jami success: <b>{data['payments']}</b>",
            f"Stars: <b>{data['stars']}</b>\n",
        ]
        for p in pays:
            u = await s.get(User, p.user_id)
            uname = f"@{u.username}" if u and u.username else str(u.telegram_id if u else p.user_id)
            st = "✅" if p.status == "success" else "⏳"
            dt = as_utc(p.paid_at) or as_utc(p.created_at)
            ds = dt.strftime("%m-%d %H:%M") if dt else "—"
            lines.append(f"{st} <b>{p.amount_stars}</b>★ · {uname} · {p.purpose} · {ds}")
    text = "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=admin_home_kb())
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=admin_home_kb())


# ── Broadcast ──────────────────────────────────────────

@router.callback_query(F.data == "adm:bc")
async def adm_bc(cb: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    await state.set_state(AdminStates.broadcast)
    await cb.message.answer(
        "📢 <b>Broadcast</b>\n\n"
        "Barcha userlarga yuboriladigan matnni yozing.\n"
        "HTML mumkin.\n\n"
        "/cancel — bekor"
    )


@router.message(AdminStates.broadcast, F.text)
async def adm_bc_send(message: Message, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    if not message.from_user or not _is_admin(message.from_user.id, settings):
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("Bekor.", reply_markup=main_menu(is_admin=True))
        return
    users = await billing.list_users(1000)
    # confirm count first message already body — send directly with progress
    ok = fail = 0
    prog = await message.answer(f"⏳ Yuborilmoqda… 0/{len(users)}")
    for i, u in enumerate(users, 1):
        try:
            await message.bot.send_message(u.telegram_id, f"📢 <b>E’lon</b>\n\n{text}")
            ok += 1
        except Exception:  # noqa: BLE001
            fail += 1
        if i % 25 == 0:
            try:
                await prog.edit_text(f"⏳ {i}/{len(users)}…")
            except Exception:  # noqa: BLE001
                pass
    await state.clear()
    await message.answer(
        f"✅ Broadcast tugadi\nYuborildi: <b>{ok}</b>\nXato: <b>{fail}</b>",
        reply_markup=main_menu(is_admin=True),
    )
    logger.info("broadcast ok=%s fail=%s by=%s", ok, fail, message.from_user.id)
