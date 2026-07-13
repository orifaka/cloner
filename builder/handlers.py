from __future__ import annotations

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from builder.admin import router as admin_router
from builder.billing import BillingService
from builder.config import Settings
from builder.deploy import DeploymentEngine, TokenError
from builder.keyboards import control_kb, home_inline, main_menu, status_kb
from builder.texts import (
    t_ask_token,
    t_busy,
    t_cancelled,
    t_checking,
    t_deploying,
    t_failed,
    t_help,
    t_home,
    t_invalid,
    t_need_sub,
    t_no_bot,
    t_progress,
    t_ready,
    t_status,
)
from builder.ui import replace_message, safe_cb, safe_delete_message, show

logger = logging.getLogger("builder.handlers")
router = Router(name="builder")
router.include_router(admin_router)

TOKEN_RE = re.compile(r"^\d{6,15}:[A-Za-z0-9_-]{20,}$")
_active: set[int] = set()


class DeployStates(StatesGroup):
    waiting_token = State()


def _is_admin(uid: int, settings: Settings) -> bool:
    return uid in settings.admin_telegram_ids


def _menu(settings: Settings, uid: int | None = None) -> object:
    return main_menu(is_admin=bool(uid and _is_admin(uid, settings)))


# ── start / nav ────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    await state.clear()
    u = message.from_user
    if not u:
        return
    await billing.ensure_user(u.id, u.username, u.full_name, u.language_code or settings.default_language)
    await safe_delete_message(message)
    is_adm = _is_admin(u.id, settings)
    await show(
        message.bot,
        message.chat.id,
        state,
        t_home(settings, is_admin=is_adm),
        _menu(settings, u.id),
        wipe=False,
    )
    await message.bot.send_message(
        message.chat.id,
        "Quyidagidan tanlang 👇",
        reply_markup=home_inline(payments_enabled=settings.payments_enabled),
    )
    logger.info("start user=%s admin=%s", u.id, is_adm)


@router.message(Command("help"))
@router.message(F.text.in_({"ℹ️ Yordam", "🆘 Support"}))
async def cmd_help(message: Message, state: FSMContext, settings: Settings) -> None:
    u = message.from_user
    await safe_delete_message(message)
    await show(
        message.bot,
        message.chat.id,
        state,
        t_help(settings),
        _menu(settings, u.id if u else None),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, settings: Settings) -> None:
    u = message.from_user
    await safe_delete_message(message)
    await state.clear()
    await show(message.bot, message.chat.id, state, t_cancelled(), _menu(settings, u.id if u else None))


@router.callback_query(F.data == "nav:home")
async def nav_home(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await safe_cb(callback)
    u = callback.from_user
    if not callback.message or not u:
        return
    await state.clear()
    is_adm = _is_admin(u.id, settings)
    try:
        await callback.message.edit_text(t_home(settings, is_admin=is_adm), reply_markup=home_inline(payments_enabled=settings.payments_enabled))
    except Exception:  # noqa: BLE001
        await show(
            callback.bot,
            callback.message.chat.id,
            state,
            t_home(settings, is_admin=is_adm),
            home_inline(payments_enabled=settings.payments_enabled),
        )


@router.callback_query(F.data == "nav:help")
async def nav_help(callback: CallbackQuery, settings: Settings) -> None:
    await safe_cb(callback)
    if callback.message:
        await callback.message.answer(t_help(settings))


@router.callback_query(F.data == "nav:open")
async def nav_open(callback: CallbackQuery, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    await safe_cb(callback)
    if not callback.message or not callback.from_user:
        return
    # reuse open flow via fake message path
    await _open_flow(callback.message, state, billing, settings, callback.from_user)


@router.callback_query(F.data == "nav:token")
async def nav_token(callback: CallbackQuery, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    await safe_cb(callback)
    if not callback.message or not callback.from_user:
        return
    u = callback.from_user
    panel = await billing.get_panel(u.id)
    sub = panel.get("subscription")
    if not sub or sub.status not in {"active", "grace"}:
        if not settings.payments_enabled:
            await billing.ensure_user(u.id, u.username, u.full_name)
            res = await billing.grant_test_subscription(u.id)
            sub = res["subscription"]
        else:
            await callback.message.answer(t_need_sub())
            return
    await state.set_state(DeployStates.waiting_token)
    await state.update_data(subscription_id=sub.id, deploying=False)
    await callback.message.answer(t_ask_token())


@router.callback_query(F.data == "nav:status")
@router.callback_query(F.data == "nav:panel")
async def nav_status(callback: CallbackQuery, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    await safe_cb(callback)
    if not callback.message or not callback.from_user:
        return
    await _send_status(callback.message, state, billing, settings, callback.from_user.id)


# ── open / pay ─────────────────────────────────────────

async def _open_flow(message: Message, state: FSMContext, billing: BillingService, settings: Settings, user) -> None:
    if user.id in _active or (await state.get_data()).get("deploying"):
        await show(message.bot, message.chat.id, state, t_busy(), _menu(settings, user.id))
        return
    await billing.ensure_user(user.id, user.username, user.full_name)

    if not settings.payments_enabled:
        res = await billing.grant_test_subscription(user.id)
        await state.set_state(DeployStates.waiting_token)
        await state.update_data(subscription_id=res["subscription"].id, deploying=False)
        await show(message.bot, message.chat.id, state, t_ask_token(), _menu(settings, user.id))
        logger.info("open test user=%s", user.id)
        return

    payload = await billing.create_invoice_payload(user.id)
    await billing.send_stars_invoice(message.bot, message.chat.id, payload)
    await show(
        message.bot,
        message.chat.id,
        state,
        f"⭐ <b>{settings.subscription_price_stars} Stars</b>\nTo'lovni tasdiqlang.",
        _menu(settings, user.id),
    )


@router.message(Command("buy", "open", "subscribe"))
@router.message(F.text.in_({"🚀 Ochish", "🚀 Bot ochish"}))
async def cmd_open(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    u = message.from_user
    if not u:
        return
    await safe_delete_message(message)
    await _open_flow(message, state, billing, settings, u)


@router.message(Command("renew"))
async def cmd_renew(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    u = message.from_user
    if not u:
        return
    await safe_delete_message(message)
    if not settings.payments_enabled:
        await _open_flow(message, state, billing, settings, u)
        return
    await billing.ensure_user(u.id, u.username, u.full_name)
    payload = await billing.create_invoice_payload(u.id, purpose="renewal")
    await billing.send_stars_invoice(message.bot, message.chat.id, payload)


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery, settings: Settings) -> None:
    if not settings.payments_enabled:
        await q.answer(ok=False, error_message="Test rejim")
        return
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    if not settings.payments_enabled:
        return
    p = message.successful_payment
    if not p or p.currency != "XTR":
        return
    res = await billing.activate_from_payment(p.invoice_payload, p.telegram_payment_charge_id, p.provider_payment_charge_id)
    sub = res["subscription"]
    await state.set_state(DeployStates.waiting_token)
    await state.update_data(subscription_id=sub.id, deploying=False)
    u = message.from_user
    await show(message.bot, message.chat.id, state, t_ask_token(), _menu(settings, u.id if u else None))
    logger.info("paid user=%s", u.id if u else "?")


# ── token + deploy ─────────────────────────────────────

@router.message(Command("token"))
async def cmd_token(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    u = message.from_user
    if not u:
        return
    await safe_delete_message(message)
    panel = await billing.get_panel(u.id)
    sub = panel.get("subscription")
    if not sub or sub.status not in {"active", "grace"}:
        if settings.payments_enabled:
            await show(message.bot, message.chat.id, state, t_need_sub(), _menu(settings, u.id))
            return
        await billing.ensure_user(u.id, u.username, u.full_name)
        res = await billing.grant_test_subscription(u.id)
        sub = res["subscription"]
    await state.set_state(DeployStates.waiting_token)
    await state.update_data(subscription_id=sub.id, deploying=False)
    await show(message.bot, message.chat.id, state, t_ask_token(), _menu(settings, u.id))


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
        await show(
            message.bot,
            message.chat.id,
            state,
            t_invalid("Format: <code>123456:AA...</code>"),
            _menu(settings, u.id),
        )
        await state.set_state(DeployStates.waiting_token)
        return
    if u.id in _active:
        await show(message.bot, message.chat.id, state, t_busy(), _menu(settings, u.id))
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
            await show(message.bot, message.chat.id, state, t_need_sub(), _menu(settings, u.id))
            await state.clear()
            return

    msg = await show(message.bot, message.chat.id, state, t_checking(), _menu(settings, u.id))
    try:
        identity = await asyncio.wait_for(deploy.validate_token(raw), timeout=20)
        logger.info("token ok user=%s @%s admin_id=%s", u.id, identity.username, u.id)
    except TokenError as e:
        await replace_message(msg, t_invalid(str(e)))
        await state.set_state(DeployStates.waiting_token)
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("token fail")
        await replace_message(msg, t_invalid(str(e)[:200]))
        await state.set_state(DeployStates.waiting_token)
        return

    await state.set_state(None)
    await state.update_data(deploying=True, subscription_id=sub.id)
    await replace_message(msg, t_deploying(identity.username))
    _active.add(u.id)

    asyncio.create_task(
        _bg_deploy(
            bot=message.bot,
            chat_id=message.chat.id,
            mid=msg.message_id,
            tg_id=u.id,
            db_uid=db_user.id,
            sub_id=sub.id,
            token=raw,
            identity=identity,
            deploy=deploy,
            settings=settings,
            state=state,
        )
    )


@router.message(F.text.regexp(TOKEN_RE))
async def on_token_free(
    message: Message,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
) -> None:
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
    settings: Settings,
    state: FSMContext,
) -> None:
    async def edit(text: str, kb=None) -> None:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=mid, reply_markup=kb)
        except Exception:  # noqa: BLE001
            try:
                await bot.send_message(chat_id, text, reply_markup=kb or _menu(settings, tg_id))
            except Exception:  # noqa: BLE001
                pass

    async def progress(step: str) -> None:
        await edit(t_progress(identity.username, step))

    try:
        dep_id = await deploy.deploy_for_user(
            db_uid,
            sub_id,
            token,
            identity,
            progress,
            owner_telegram_id=tg_id,
        )
        await edit(
            t_ready(identity.username, settings.subscription_days, owner_id=tg_id),
            control_kb(),
        )
        try:
            await bot.send_message(
                chat_id,
                f"#{dep_id} · boshqaruv paneli",
                reply_markup=control_kb(),
            )
        except Exception:  # noqa: BLE001
            pass
        logger.info("DEPLOY OK user=%s dep=%s @%s ADMIN_IDS=%s", tg_id, dep_id, identity.username, tg_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("DEPLOY FAIL user=%s", tg_id)
        await edit(t_failed(str(e)))
    finally:
        _active.discard(tg_id)
        try:
            await state.update_data(deploying=False)
        except Exception:  # noqa: BLE001
            pass


# ── user panel ─────────────────────────────────────────

async def _send_status(message: Message, state: FSMContext, billing: BillingService, settings: Settings, uid: int) -> None:
    p = await billing.get_panel(uid)
    dep, sub = p.get("deployment"), p.get("subscription")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), _menu(settings, uid))
        return
    await show(
        message.bot,
        message.chat.id,
        state,
        t_status(
            dep.bot_username,
            dep.status,
            p.get("days_left"),
            sub.status if sub else None,
            dep.last_error,
            owner_id=uid,
        ),
        control_kb(),
    )


@router.message(Command("status", "mybot"))
@router.message(F.text.in_({"📊 Status", "📊 Mening botim", "🎛 Boshqaruv"}))
async def cmd_status(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    await safe_delete_message(message)
    u = message.from_user
    if not u:
        return
    await _send_status(message, state, billing, settings, u.id)


async def _ctl(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
    action: str,
) -> None:
    if isinstance(event, CallbackQuery):
        await safe_cb(event)
        message, u = event.message, event.from_user
    else:
        await safe_delete_message(event)
        message, u = event, event.from_user
    if not message or not u:
        return
    dep = (await billing.get_panel(u.id)).get("deployment")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), _menu(settings, u.id))
        return
    try:
        if action == "restart":
            await show(message.bot, message.chat.id, state, "⏳ Restart…", _menu(settings, u.id))
            await deploy.restart(dep.id)
            await show(message.bot, message.chat.id, state, "✅ Restart qilindi", control_kb())
        elif action == "stop":
            await deploy.stop(dep.id)
            await show(message.bot, message.chat.id, state, "⏹ To'xtatildi", control_kb())
        elif action == "start":
            await deploy.start(dep.id)
            await show(message.bot, message.chat.id, state, "▶️ Ishga tushdi", control_kb())
        elif action == "logs":
            text = await deploy.read_logs(dep.id, 30)
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            await show(
                message.bot,
                message.chat.id,
                state,
                f"<pre>{safe[-3000:]}</pre>" if safe else "Log bo'sh",
                control_kb(),
            )
        elif action == "backup":
            path = await deploy.backup(dep.id)
            await show(
                message.bot,
                message.chat.id,
                state,
                f"💾 Backup: <code>{path.name}</code>",
                control_kb(),
            )
    except Exception as e:  # noqa: BLE001
        await show(message.bot, message.chat.id, state, f"❌ {e}", _menu(settings, u.id))


@router.message(Command("restart"))
@router.message(F.text == "🔁 Restart")
@router.callback_query(F.data == "ctl:restart")
async def ctl_restart(e, state: FSMContext, billing: BillingService, deploy: DeploymentEngine, settings: Settings) -> None:
    await _ctl(e, state, billing, deploy, settings, "restart")


@router.message(Command("stop", "stopbot"))
@router.message(F.text == "⏹ Stop")
@router.callback_query(F.data == "ctl:stop")
async def ctl_stop(e, state: FSMContext, billing: BillingService, deploy: DeploymentEngine, settings: Settings) -> None:
    await _ctl(e, state, billing, deploy, settings, "stop")


@router.message(Command("startbot"))
@router.message(F.text == "▶️ Start")
@router.callback_query(F.data == "ctl:start")
async def ctl_start(e, state: FSMContext, billing: BillingService, deploy: DeploymentEngine, settings: Settings) -> None:
    await _ctl(e, state, billing, deploy, settings, "start")


@router.message(Command("logs"))
@router.message(F.text.in_({"🧾 Log", "🧾 Loglar"}))
@router.callback_query(F.data == "ctl:logs")
async def ctl_logs(e, state: FSMContext, billing: BillingService, deploy: DeploymentEngine, settings: Settings) -> None:
    await _ctl(e, state, billing, deploy, settings, "logs")


@router.callback_query(F.data == "ctl:backup")
async def ctl_backup(e, state: FSMContext, billing: BillingService, deploy: DeploymentEngine, settings: Settings) -> None:
    await _ctl(e, state, billing, deploy, settings, "backup")
