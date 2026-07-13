from __future__ import annotations

"""Subscription entry. Test mode skips Stars and opens token step immediately."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from platform_billing.service import BillingService
from platform_core.config import Settings
from platform_core.enums import PaymentPurpose

from handlers.deploy import DeployStates
from keyboards import main_menu
from texts import t_ask_token
from ui import safe_callback_answer, safe_delete_message, show

router = Router(name="payment")


async def _open_token_flow(
    message: Message,
    state: FSMContext,
    billing: BillingService,
    settings: Settings,
    user_id: int,
    username: str | None,
    full_name: str,
) -> None:
    await billing.ensure_user(user_id, username, full_name)

    if not settings.payments_enabled:
        result = await billing.grant_test_subscription(user_id)
        sub = result["subscription"]
        await state.set_state(DeployStates.waiting_token)
        await state.update_data(subscription_id=sub.id, deploying=False)
        await show(message.bot, message.chat.id, state, t_ask_token(), main_menu())
        return

    # Production: Stars invoice
    payload = await billing.create_invoice_payload(
        user_id, purpose=PaymentPurpose.NEW_SUBSCRIPTION.value
    )
    await billing.send_stars_invoice(message.bot, message.chat.id, payload)
    await show(
        message.bot,
        message.chat.id,
        state,
        f"⭐ <b>{settings.subscription_price_stars} Stars</b>\nTo'lovni tasdiqlang.",
        main_menu(),
    )


@router.message(Command("buy", "subscribe", "open", "new"))
@router.message(F.text.in_({"🚀 Ochish", "🚀 Bot ochish"}))
async def open_bot(
    message: Message,
    billing: BillingService,
    settings: Settings,
    state: FSMContext,
) -> None:
    user = message.from_user
    if not user:
        return
    await safe_delete_message(message)
    data = await state.get_data()
    if data.get("deploying"):
        await show(message.bot, message.chat.id, state, "⏳ Deploy ketmoqda…", main_menu())
        return
    await _open_token_flow(
        message, state, billing, settings, user.id, user.username, user.full_name
    )


@router.message(Command("renew"))
@router.message(F.text.in_({"🔄 Yangilash"}))
async def renew(
    message: Message,
    billing: BillingService,
    settings: Settings,
    state: FSMContext,
) -> None:
    user = message.from_user
    if not user:
        return
    await safe_delete_message(message)
    if not settings.payments_enabled:
        await _open_token_flow(
            message, state, billing, settings, user.id, user.username, user.full_name
        )
        return
    await billing.ensure_user(user.id, user.username, user.full_name)
    payload = await billing.create_invoice_payload(
        user.id, purpose=PaymentPurpose.RENEWAL.value
    )
    await billing.send_stars_invoice(message.bot, message.chat.id, payload)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, settings: Settings) -> None:
    if not settings.payments_enabled:
        await query.answer(ok=False, error_message="Test rejim")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(message: Message, billing: BillingService, state: FSMContext, settings: Settings) -> None:
    if not settings.payments_enabled:
        return
    payment = message.successful_payment
    if not payment or payment.currency != "XTR":
        return
    result = await billing.activate_subscription_from_payment(
        payload=payment.invoice_payload,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
        raw=payment.model_dump(),
    )
    sub = result["subscription"]
    await state.set_state(DeployStates.waiting_token)
    await state.update_data(subscription_id=sub.id, deploying=False)
    await show(message.bot, message.chat.id, state, t_ask_token(), main_menu())
