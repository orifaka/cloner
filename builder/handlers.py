from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from builder.admin import router as admin_router
from builder.billing import BillingService, as_utc
from builder.config import Settings
from builder.copy import (
    ask_token,
    bot_card,
    dashboard,
    delete_warning,
    deploy_done,
    deploy_progress,
    empty_bots,
    fmt_dt,
    friendly_error,
    help_text,
    intro,
    payment_ok,
    payment_sent,
    pricing_pitch,
    settings_text,
    subscription_card,
)
from builder.deploy import DeploymentEngine, TokenError
from builder.keyboards import (
    after_error_kb,
    after_success_kb,
    bot_actions_kb,
    bots_list_kb,
    confirm_kb,
    empty_bots_kb,
    intro_kb,
    main_menu,
    sub_kb,
    support_kb,
)
from builder.ui import present, replace_message, safe_cb, safe_delete_message, show

logger = logging.getLogger("builder.handlers")
router = Router(name="builder")
router.include_router(admin_router)

TOKEN_RE = re.compile(r"^\d{6,15}:[A-Za-z0-9_-]{20,}$")
_active: set[int] = set()


class DeployStates(StatesGroup):
    waiting_token = State()


def _admin(uid: int, s: Settings) -> bool:
    return uid in s.admin_telegram_ids


def _menu(s: Settings, uid: int | None) -> object:
    return main_menu(is_admin=bool(uid and _admin(uid, s)))


def _exp_str(sub) -> str | None:
    if not sub or not sub.expires_at:
        return None
    return fmt_dt(as_utc(sub.expires_at))


# ── Home ───────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    await state.clear()
    u = message.from_user
    if not u:
        return
    await billing.ensure_user(u.id, u.username, u.full_name, u.language_code or settings.default_language)
    await safe_delete_message(message)
    await present(
        message.bot,
        message.chat.id,
        state,
        intro(settings),
        reply_menu=_menu(settings, u.id),
        inline=intro_kb(payments_on=settings.payments_enabled),
        wipe=False,
    )


@router.callback_query(F.data == "ux:home")
async def ux_home(cb: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await safe_cb(cb)
    if not cb.message or not cb.from_user:
        return
    await state.clear()
    try:
        await cb.message.edit_text(
            intro(settings),
            reply_markup=intro_kb(payments_on=settings.payments_enabled),
            disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        await present(
            cb.bot,
            cb.message.chat.id,
            state,
            intro(settings),
            reply_menu=_menu(settings, cb.from_user.id),
            inline=intro_kb(payments_on=settings.payments_enabled),
        )


@router.message(Command("help", "support"))
@router.message(F.text.in_({"❓ Yordam", "❓ Support"}))
@router.callback_query(F.data == "ux:support")
async def ux_support(event: Message | CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if isinstance(event, CallbackQuery):
        await safe_cb(event)
        msg, u = event.message, event.from_user
    else:
        await safe_delete_message(event)
        msg, u = event, event.from_user
    if not msg:
        return
    await show(
        msg.bot,
        msg.chat.id,
        state,
        help_text(settings),
        support_kb(settings.support_url),
    )


@router.message(F.text.in_({"⚙️ Settings", "⚙️ Sozlamalar"}))
async def ux_settings(message: Message, state: FSMContext, settings: Settings) -> None:
    u = message.from_user
    await safe_delete_message(message)
    lang = u.language_code if u else "uz"
    await show(
        message.bot,
        message.chat.id,
        state,
        settings_text(settings, lang or "uz"),
        _menu(settings, u.id if u else None),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, settings: Settings) -> None:
    u = message.from_user
    await safe_delete_message(message)
    await state.clear()
    await show(
        message.bot,
        message.chat.id,
        state,
        "Bekor qilindi.\nMenyudan davom eting 👇",
        _menu(settings, u.id if u else None),
    )


# ── Subscription ───────────────────────────────────────

@router.message(Command("subscription", "renew"))
@router.message(F.text.in_({"💎 Subscription", "💎 Obuna"}))
@router.callback_query(F.data.in_({"ux:sub", "ux:renew", "ux:pay"}))
async def ux_subscription(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    settings: Settings,
    deploy: DeploymentEngine,
) -> None:
    if isinstance(event, CallbackQuery):
        await safe_cb(event)
        msg, u = event.message, event.from_user
        data = event.data
    else:
        await safe_delete_message(event)
        msg, u = event, event.from_user
        data = "ux:sub"
    if not msg or not u:
        return

    await billing.ensure_user(u.id, u.username, u.full_name)
    panel = await billing.get_panel(u.id)
    sub = panel.get("subscription")

    if data == "ux:pay" or (data == "ux:renew" and settings.payments_enabled):
        if settings.payments_enabled:
            payload = await billing.create_invoice_payload(u.id, purpose="renewal")
            await billing.send_stars_invoice(msg.bot, msg.chat.id, payload)
            await msg.answer(payment_sent(settings))
            return
        await msg.answer("🧪 Test rejim: to‘lov o‘chiq.\n✨ Bot ochish orqali davom eting.")
        return

    # Pricing pitch if no sub, card if has sub
    if not sub:
        text = pricing_pitch(settings)
    else:
        text = subscription_card(
            settings,
            status=sub.status if sub else None,
            days_left=panel.get("days_left"),
            expires=_exp_str(sub),
        )
    await show(
        msg.bot,
        msg.chat.id,
        state,
        text,
        sub_kb(payments_on=settings.payments_enabled, price=settings.subscription_price_stars),
    )


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery, settings: Settings) -> None:
    if not settings.payments_enabled:
        await q.answer(ok=False, error_message="Payments are disabled in test mode.")
        return
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(
    message: Message,
    state: FSMContext,
    billing: BillingService,
    settings: Settings,
    deploy: DeploymentEngine,
) -> None:
    if not settings.payments_enabled:
        return
    p = message.successful_payment
    if not p or p.currency != "XTR":
        return
    try:
        res = await billing.activate_from_payment(
            p.invoice_payload, p.telegram_payment_charge_id, p.provider_payment_charge_id
        )
        sub = res["subscription"]
        # restore suspended bot
        if message.from_user:
            panel = await billing.get_panel(message.from_user.id)
            dep = panel.get("deployment")
            if dep and dep.status == "suspended":
                try:
                    await deploy.start(dep.id)
                except Exception:  # noqa: BLE001
                    logger.exception("reactivate failed")
        await state.set_state(DeployStates.waiting_token)
        await state.update_data(subscription_id=sub.id if sub else None, deploying=False)
        await message.answer(payment_ok())
        await message.answer(ask_token())
    except Exception as e:  # noqa: BLE001
        logger.exception("payment activate")
        await message.answer(friendly_error(e), reply_markup=after_error_kb())


# ── Create bot / token ─────────────────────────────────

async def _begin_create(message: Message, state: FSMContext, billing: BillingService, settings: Settings, user) -> None:
    if user.id in _active or (await state.get_data()).get("deploying"):
        await message.answer("A deployment is already in progress. Please wait.")
        return
    await billing.ensure_user(user.id, user.username, user.full_name)

    if settings.payments_enabled:
        panel = await billing.get_panel(user.id)
        sub = panel.get("subscription")
        if not sub or sub.status not in {"active", "grace"}:
            payload = await billing.create_invoice_payload(user.id)
            await billing.send_stars_invoice(message.bot, message.chat.id, payload)
            await message.answer(payment_sent(settings))
            return
    else:
        res = await billing.grant_test_subscription(user.id)
        sub = res["subscription"]

    panel = await billing.get_panel(user.id)
    sub = panel.get("subscription") or sub
    await state.set_state(DeployStates.waiting_token)
    await state.update_data(subscription_id=sub.id if sub else None, deploying=False)
    await show(message.bot, message.chat.id, state, ask_token(), _menu(settings, user.id))


@router.message(Command("create", "open", "buy"))
@router.message(F.text.in_({"✨ Create Bot", "🚀 Ochish", "✨ Bot ochish"}))
@router.callback_query(F.data == "ux:create")
async def ux_create(event: Message | CallbackQuery, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    if isinstance(event, CallbackQuery):
        await safe_cb(event)
        msg, u = event.message, event.from_user
    else:
        await safe_delete_message(event)
        msg, u = event, event.from_user
    if not msg or not u:
        return
    await _begin_create(msg, state, billing, settings, u)


@router.message(StateFilter(DeployStates.waiting_token), F.text)
async def on_token(
    message: Message,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
) -> None:
    u = message.from_user
    if not u:
        return
    raw = (message.text or "").strip()
    await safe_delete_message(message)
    if raw.startswith("/"):
        return
    if not TOKEN_RE.match(raw):
        await message.answer(friendly_error("token format"), reply_markup=after_error_kb())
        await state.set_state(DeployStates.waiting_token)
        return
    if u.id in _active:
        await message.answer("⏳ Deploy allaqachon ketmoqda. Biroz kuting…")
        return

    panel = await billing.get_panel(u.id)
    db_user, sub = panel.get("user"), panel.get("subscription")
    if not db_user:
        db_user = await billing.ensure_user(u.id, u.username, u.full_name)
        panel = await billing.get_panel(u.id)
        sub = panel.get("subscription")
    if not sub or sub.status not in {"active", "grace"}:
        if not settings.payments_enabled:
            res = await billing.grant_test_subscription(u.id)
            sub, db_user = res["subscription"], res["user"]
        else:
            await message.answer(
                "💎 Avval obuna kerak.",
                reply_markup=sub_kb(payments_on=True, price=settings.subscription_price_stars),
            )
            await state.clear()
            return

    progress_msg = await message.answer(deploy_progress(1, "Token tekshirilmoqda…"))
    _active.add(u.id)
    await state.set_state(None)
    await state.update_data(deploying=True)

    try:
        identity = await asyncio.wait_for(deploy.validate_token(raw), timeout=20)
    except TokenError as e:
        _active.discard(u.id)
        await state.update_data(deploying=False)
        await progress_msg.edit_text(friendly_error(e), reply_markup=after_error_kb())
        await state.set_state(DeployStates.waiting_token)
        return
    except Exception as e:  # noqa: BLE001
        _active.discard(u.id)
        await state.update_data(deploying=False)
        logger.exception("token")
        await progress_msg.edit_text(friendly_error(e), reply_markup=after_error_kb())
        return

    asyncio.create_task(
        _bg_deploy(
            bot=message.bot,
            chat_id=message.chat.id,
            mid=progress_msg.message_id,
            tg_id=u.id,
            db_uid=db_user.id,
            sub_id=sub.id,
            token=raw,
            identity=identity,
            deploy=deploy,
            billing=billing,
            settings=settings,
            state=state,
        )
    )


@router.message(F.text.regexp(TOKEN_RE))
async def on_token_any(message: Message, state: FSMContext, billing: BillingService, deploy: DeploymentEngine, settings: Settings) -> None:
    if await state.get_state() == DeployStates.waiting_token.state:
        return
    await state.set_state(DeployStates.waiting_token)
    await on_token(message, state, billing, deploy, settings)


async def _bg_deploy(
    *,
    bot: Bot,
    chat_id: int,
    mid: int,
    tg_id: int,
    db_uid: int,
    sub_id: int,
    token: str,
    identity,
    deploy: DeploymentEngine,
    billing: BillingService,
    settings: Settings,
    state: FSMContext,
) -> None:
    async def edit(text: str, kb=None) -> None:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=mid, reply_markup=kb)
        except Exception:  # noqa: BLE001
            try:
                await bot.send_message(chat_id, text, reply_markup=kb)
            except Exception:  # noqa: BLE001
                pass

    # Map internal steps → premium stages
    async def progress(step: str) -> None:
        s = step.lower()
        if "fayl" in s or "1/4" in s or "copy" in s:
            await edit(deploy_progress(2, "Preparing database…"))
        elif "sozlama" in s or "admin" in s or "2/4" in s or "config" in s:
            await edit(deploy_progress(3, "Writing configuration…"))
        elif "python" in s or "3/4" in s or "runtime" in s:
            await edit(deploy_progress(4, "Starting deployment…"))
        elif "start" in s or "4/4" in s or "health" in s:
            await edit(deploy_progress(5, "Health check…"))
        else:
            await edit(deploy_progress(4, step[:40]))

    try:
        await edit(deploy_progress(1, "Token validated"))
        dep_id = await deploy.deploy_for_user(
            db_uid, sub_id, token, identity, progress, owner_telegram_id=tg_id
        )
        panel = await billing.get_panel(tg_id)
        sub = panel.get("subscription")
        await edit(
            deploy_done(identity.username, settings.subscription_days, _exp_str(sub)),
            after_success_kb(dep_id),
        )
        logger.info("DEPLOY OK user=%s dep=%s", tg_id, dep_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("DEPLOY FAIL user=%s", tg_id)
        await edit(friendly_error(e), after_error_kb())
    finally:
        _active.discard(tg_id)
        try:
            await state.update_data(deploying=False)
        except Exception:  # noqa: BLE001
            pass


# ── My Bots ────────────────────────────────────────────

@router.message(Command("bots", "mybots", "status"))
@router.message(F.text.in_({"🤖 My Bots", "🤖 Botlarim", "📊 Status", "🎛 Boshqaruv"}))
@router.callback_query(F.data.startswith("ux:bots"))
async def ux_bots(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    settings: Settings,
    deploy: DeploymentEngine,
) -> None:
    if isinstance(event, CallbackQuery):
        await safe_cb(event)
        msg, u = event.message, event.from_user
    else:
        await safe_delete_message(event)
        msg, u = event, event.from_user
    if not msg or not u:
        return
    panel = await billing.get_panel(u.id)
    dep = panel.get("deployment")
    if not dep:
        await show(
            msg.bot,
            msg.chat.id,
            state,
            empty_bots(),
            empty_bots_kb(payments_on=settings.payments_enabled),
        )
        return
    await _show_bot_card(msg, state, billing, deploy, settings, u.id, dep.id, engine=deploy)


async def _show_bot_card(
    msg: Message,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
    uid: int,
    dep_id: int,
    engine: DeploymentEngine | None = None,
) -> None:
    panel = await billing.get_panel(uid)
    dep = panel.get("deployment")
    if not dep or dep.id != dep_id:
        dep = await billing.get_deployment(dep_id)
    if not dep or dep.status == "deleted":
        await show(
            msg.bot,
            msg.chat.id,
            state,
            "🔍 Bu bot endi mavjud emas.\nYangi bot ochishingiz mumkin.",
            empty_bots_kb(payments_on=settings.payments_enabled),
        )
        return
    eng = engine or deploy
    metrics = eng.metrics(dep.id, dep.project_path, dep.process_pid, dep.slug)
    sub = panel.get("subscription")
    days = panel.get("days_left")
    if days is None and sub and sub.expires_at:
        exp = as_utc(sub.expires_at)
        if exp:
            days = max(0, int((exp - datetime.now(timezone.utc)).total_seconds() // 86400))

    text = bot_card(
        username=dep.bot_username,
        status=dep.status,
        days_left=days,
        expires=_exp_str(sub) if sub else None,
        cpu=metrics["cpu"],
        ram=metrics["ram"],
        db_size=metrics["db_size"],
        last_backup=metrics["last_backup"],
    )
    await show(
        msg.bot,
        msg.chat.id,
        state,
        text,
        bot_actions_kb(dep.id, status=dep.status),
    )


@router.callback_query(F.data.startswith("bot:view:"))
async def bot_view(
    cb: CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
) -> None:
    await safe_cb(cb)
    if not cb.message or not cb.from_user:
        return
    dep_id = int(cb.data.split(":")[-1])
    panel = await billing.get_panel(cb.from_user.id)
    dep = panel.get("deployment")
    if not dep or dep.id != dep_id:
        await cb.message.answer("🚫 Faqat o‘z botingizni boshqara olasiz.")
        return
    await _show_bot_card(cb.message, state, billing, deploy, settings, cb.from_user.id, dep_id, engine=deploy)


@router.callback_query(F.data.startswith("bot:"))
async def bot_actions(
    cb: CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
) -> None:
    await safe_cb(cb)
    if not cb.message or not cb.from_user:
        return
    parts = (cb.data or "").split(":")
    if len(parts) < 3:
        return
    action, dep_id_s = parts[1], parts[2]
    dep_id = int(dep_id_s)
    panel = await billing.get_panel(cb.from_user.id)
    dep = panel.get("deployment")
    if not dep or dep.id != dep_id:
        await cb.message.answer("🚫 Ruxsat yo‘q.")
        return

    if action == "delask":
        await cb.message.edit_text(
            delete_warning(dep.bot_username),
            reply_markup=confirm_kb(f"bot:delok:{dep_id}", f"bot:view:{dep_id}"),
        )
        return

    try:
        if action == "start":
            if dep.status == "suspended":
                await cb.message.answer(
                    "🔴 Bot suspend.\nAvval obunani yangilang.",
                    reply_markup=sub_kb(payments_on=settings.payments_enabled, price=settings.subscription_price_stars),
                )
                return
            await deploy.start(dep_id)
            note = "Bot ishga tushdi"
        elif action == "stop":
            await deploy.stop(dep_id)
            note = "Bot to‘xtatildi"
        elif action == "restart":
            await deploy.restart(dep_id)
            note = "Bot qayta ishga tushdi"
        elif action == "backup":
            path = await deploy.backup(dep_id)
            note = f"Backup saqlandi: <code>{path.name}</code>"
        elif action == "logs":
            text = await deploy.read_logs(dep_id, 25)
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            await cb.message.answer(f"<pre>{safe[-2500:]}</pre>" if safe else "Log hali yo‘q.")
            return
        elif action == "delok":
            await deploy.purge(dep_id)
            await cb.message.edit_text(
                "🗑 <b>Bot o‘chirildi</b>\n\nBarcha ma’lumotlar butunlay olib tashlandi.",
                reply_markup=empty_bots_kb(payments_on=settings.payments_enabled),
            )
            return
        else:
            return
        await cb.answer(f"✅ {note}", show_alert=False)
        await _show_bot_card(cb.message, state, billing, deploy, settings, cb.from_user.id, dep_id, engine=deploy)
    except Exception as e:  # noqa: BLE001
        logger.exception("bot action")
        await cb.message.answer(friendly_error(e), reply_markup=after_error_kb())


# ── Dashboard ──────────────────────────────────────────

@router.message(Command("dashboard"))
@router.message(F.text.in_({"📊 Dashboard", "📊 Kabinet"}))
async def ux_dashboard(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    u = message.from_user
    if not u:
        return
    await safe_delete_message(message)
    panel = await billing.get_panel(u.id)
    dep = panel.get("deployment")
    sub = panel.get("subscription")
    stats = {
        "bots": 1 if dep else 0,
        "running": 1 if dep and dep.status == "running" else 0,
        "stopped": 1 if dep and dep.status == "stopped" else 0,
        "suspended": 1 if dep and dep.status == "suspended" else 0,
        "sub_status": sub.status if sub else "none",
        "days_left": panel.get("days_left") if panel.get("days_left") is not None else "—",
    }
    await show(message.bot, message.chat.id, state, dashboard(stats), _menu(settings, u.id))
