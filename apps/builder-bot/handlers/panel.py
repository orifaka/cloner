from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from platform_billing.service import BillingService
from platform_core.config import Settings
from platform_deploy.engine import DeploymentEngine
from platform_monitoring.service import MonitoringService

from keyboards import main_menu, status_kb
from texts import t_done_action, t_no_bot, t_status
from ui import safe_callback_answer, safe_delete_message, show

router = Router(name="panel")


async def _panel(message: Message, state: FSMContext, billing: BillingService) -> None:
    user = message.from_user
    if not user:
        return
    panel = await billing.get_user_panel(user.id)
    dep = panel.get("deployment")
    sub = panel.get("subscription")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), main_menu())
        return
    text = t_status(
        username=dep.bot_username,
        status=dep.status,
        days_left=panel.get("days_left"),
        sub_status=sub.status if sub else None,
        error=dep.last_error,
    )
    await show(message.bot, message.chat.id, state, text, status_kb())


@router.message(Command("mybot", "status"))
@router.message(F.text.in_({"📊 Status", "📊 Mening botim"}))
async def my_bot(message: Message, state: FSMContext, billing: BillingService) -> None:
    await safe_delete_message(message)
    await _panel(message, state, billing)


@router.message(Command("restart"))
@router.message(F.text.in_({"🔁 Restart"}))
@router.callback_query(F.data == "ctl:restart")
async def restart_bot(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    message, user = _mu(event)
    if isinstance(event, CallbackQuery):
        await safe_callback_answer(event)
    else:
        await safe_delete_message(message)
    if not message or not user:
        return
    dep = (await billing.get_user_panel(user.id)).get("deployment")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), main_menu())
        return
    wait = await show(message.bot, message.chat.id, state, "⏳ Restart…", main_menu())
    try:
        await deploy.restart(dep.id)
        await wait.edit_text(t_done_action("Restart"))
    except Exception as exc:  # noqa: BLE001
        await wait.edit_text(f"❌ {exc}")


@router.message(Command("stopbot", "stop"))
@router.message(F.text.in_({"⏹ Stop"}))
@router.callback_query(F.data == "ctl:stop")
async def stop_bot(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    message, user = _mu(event)
    if isinstance(event, CallbackQuery):
        await safe_callback_answer(event)
    else:
        await safe_delete_message(message)
    if not message or not user:
        return
    dep = (await billing.get_user_panel(user.id)).get("deployment")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), main_menu())
        return
    await deploy.stop(dep.id)
    await show(message.bot, message.chat.id, state, t_done_action("Stop"), main_menu())


@router.message(Command("startbot"))
@router.message(F.text.in_({"▶️ Start"}))
@router.callback_query(F.data == "ctl:start")
async def start_bot(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    message, user = _mu(event)
    if isinstance(event, CallbackQuery):
        await safe_callback_answer(event)
    else:
        await safe_delete_message(message)
    if not message or not user:
        return
    panel = await billing.get_user_panel(user.id)
    dep = panel.get("deployment")
    sub = panel.get("subscription")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), main_menu())
        return
    if sub and sub.status == "expired":
        await show(message.bot, message.chat.id, state, "Obuna tugagan. 🚀 Ochish", main_menu())
        return
    await deploy.start(dep.id)
    await show(message.bot, message.chat.id, state, t_done_action("Start"), main_menu())


@router.message(Command("logs"))
@router.message(F.text.in_({"🧾 Log", "🧾 Loglar"}))
@router.callback_query(F.data == "ctl:logs")
async def logs_bot(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    message, user = _mu(event)
    if isinstance(event, CallbackQuery):
        await safe_callback_answer(event)
    else:
        await safe_delete_message(message)
    if not message or not user:
        return
    dep = (await billing.get_user_panel(user.id)).get("deployment")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), main_menu())
        return
    text = await deploy.read_logs(dep.id, lines=30)
    if len(text) > 3000:
        text = text[-3000:]
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    await show(message.bot, message.chat.id, state, f"<pre>{safe}</pre>" if safe else "Log bo'sh.", main_menu())


@router.callback_query(F.data == "ctl:backup")
@router.message(Command("backup"))
async def backup_bot(
    event: Message | CallbackQuery,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
) -> None:
    message, user = _mu(event)
    if isinstance(event, CallbackQuery):
        await safe_callback_answer(event)
    else:
        await safe_delete_message(message)
    if not message or not user:
        return
    dep = (await billing.get_user_panel(user.id)).get("deployment")
    if not dep:
        await show(message.bot, message.chat.id, state, t_no_bot(), main_menu())
        return
    path = await deploy.backup(dep.id)
    await show(message.bot, message.chat.id, state, f"💾 <code>{path.name}</code>", main_menu())


@router.message(Command("admin_stats"))
async def admin_stats(
    message: Message,
    state: FSMContext,
    settings: Settings,
    monitor: MonitoringService,
) -> None:
    user = message.from_user
    if not user or user.id not in settings.admin_telegram_ids:
        return
    await safe_delete_message(message)
    from platform_core.database import get_session_factory
    from platform_core.repositories import DeploymentRepository, PaymentRepository, UserRepository

    factory = get_session_factory()
    async with factory() as session:
        users = await UserRepository(session).list_all(200)
        deps = await DeploymentRepository(session).list_all(200)
        stars = await PaymentRepository(session).total_stars_income()
    host = monitor.host_metrics()
    running = sum(1 for d in deps if d.status == "running")
    await show(
        message.bot,
        message.chat.id,
        state,
        (
            f"🛠 <b>Admin</b>\n"
            f"Users {len(users)} · Bots {len(deps)} · Run {running}\n"
            f"Stars {stars}\n"
            f"CPU {host.cpu_percent}% · RAM {host.ram_percent}%"
        ),
        main_menu(),
    )


def _mu(event: Message | CallbackQuery):
    if isinstance(event, CallbackQuery):
        return event.message, event.from_user
    return event, event.from_user
