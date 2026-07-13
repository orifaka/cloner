"""
Full Admin Panel — statistics, payments config, bots, promo, broadcast, cache.
Only ADMIN_TELEGRAM_IDS.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from builder.billing import BillingService, as_utc
from builder.config import ROOT_DIR, Settings, clear_settings_cache
from builder.copy import friendly_error
from builder.deploy import DeploymentEngine
from builder.keyboards import main_menu
from builder.store import KEY_PAYMENTS, KEY_PRICE, KEY_PROMO_DISC, KEY_PROMO_ON, Store, gen_code
from builder.ui import safe_cb, safe_delete_message, show

logger = logging.getLogger("builder.admin")
router = Router(name="admin")
DIV = "━━━━━━━━━━━━━━━━"


class AdminStates(StatesGroup):
    broadcast = State()
    msg_owner = State()
    set_price = State()
    promo_create = State()
    promo_user = State()  # unused


def _ok(uid: int | None, s: Settings) -> bool:
    return bool(uid and uid in s.admin_telegram_ids)


async def _guard(event: Message | CallbackQuery, settings: Settings) -> bool:
    u = event.from_user
    if not _ok(u.id if u else None, settings):
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


def home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Statistika", callback_data="adm:stats"),
                InlineKeyboardButton(text="🖥 System", callback_data="adm:sys"),
            ],
            [
                InlineKeyboardButton(text="🤖 Botlar", callback_data="adm:bots:0"),
                InlineKeyboardButton(text="🟢 Online", callback_data="adm:botsf:running:0"),
            ],
            [
                InlineKeyboardButton(text="🔴 Suspend", callback_data="adm:botsf:suspended:0"),
                InlineKeyboardButton(text="⚠️ Failed", callback_data="adm:botsf:failed:0"),
            ],
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users:0"),
                InlineKeyboardButton(text="💰 Payments", callback_data="adm:pays"),
            ],
            [
                InlineKeyboardButton(text="💳 To‘lov sozlamalari", callback_data="adm:paycfg"),
                InlineKeyboardButton(text="🏷 Promokodlar", callback_data="adm:promo"),
            ],
            [
                InlineKeyboardButton(text="📢 Reklama / BC", callback_data="adm:bc"),
                InlineKeyboardButton(text="🧹 Kesh tozalash", callback_data="adm:cache"),
            ],
            [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="adm:menu"),
                InlineKeyboardButton(text="🏠 User menyu", callback_data="ux:home"),
            ],
        ]
    )


def bots_kb(deps: list, page: int = 0, filt: str = "all") -> InlineKeyboardMarkup:
    items = deps if filt == "all" else [d for d in deps if d.status == filt]
    per = 6
    chunk = items[page * per : (page + 1) * per]
    rows: list[list[InlineKeyboardButton]] = []
    for d in chunk:
        icon = {"running": "🟢", "stopped": "⏸", "suspended": "🔴", "failed": "⚠️"}.get(d.status, "⚪")
        name = f"@{d.bot_username}" if d.bot_username else f"#{d.id}"
        rows.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"adm:bot:{d.id}")])
    prefix = f"adm:botsf:{filt}" if filt != "all" else "adm:bots"
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page - 1}"))
    if (page + 1) * per < len(items):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🛠 Admin", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_kb(dep_id: int) -> InlineKeyboardMarkup:
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
            [InlineKeyboardButton(text="🗑 Purge", callback_data=f"adm:act:delask:{dep_id}")],
            [
                InlineKeyboardButton(text="◀️", callback_data="adm:bots:0"),
                InlineKeyboardButton(text="🛠", callback_data="adm:menu"),
            ],
        ]
    )


def paycfg_kb(payments_on: bool) -> InlineKeyboardMarkup:
    toggle = "🟢 To‘lov YOQISH" if not payments_on else "🔴 To‘lov O‘CHIRISH"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle, callback_data="adm:pay:toggle")],
            [
                InlineKeyboardButton(text="⭐ 200", callback_data="adm:pay:price:200"),
                InlineKeyboardButton(text="⭐ 250", callback_data="adm:pay:price:250"),
                InlineKeyboardButton(text="⭐ 300", callback_data="adm:pay:price:300"),
            ],
            [
                InlineKeyboardButton(text="⭐ 350", callback_data="adm:pay:price:350"),
                InlineKeyboardButton(text="⭐ 500", callback_data="adm:pay:price:500"),
            ],
            [InlineKeyboardButton(text="✏️ Boshqa narx", callback_data="adm:pay:custom")],
            [
                InlineKeyboardButton(text="🔥 Promo ON/OFF", callback_data="adm:pay:promo"),
                InlineKeyboardButton(text="Promo −50", callback_data="adm:pay:pdisc:50"),
            ],
            [InlineKeyboardButton(text="🛠 Admin", callback_data="adm:menu")],
        ]
    )


def promo_kb(promos: list) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in promos[:12]:
        st = "✅" if p.active else "⏸"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{st} {p.code} · {p.kind}:{p.value} ({p.used_count}/{p.max_uses})",
                    callback_data=f"adm:ptog:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Yangi kod", callback_data="adm:pnew")])
    rows.append(
        [
            InlineKeyboardButton(text="🎲 Auto STARS50", callback_data="adm:pauto:stars:50"),
            InlineKeyboardButton(text="🎲 Auto +7kun", callback_data="adm:pauto:days:7"),
        ]
    )
    rows.append([InlineKeyboardButton(text="🛠 Admin", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(yes: str, no: str = "adm:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=yes),
                InlineKeyboardButton(text="❌ Yo‘q", callback_data=no),
            ]
        ]
    )


def _stats(data: dict, settings: Settings, price: int, pay_on: bool) -> str:
    total = max(1, data["deployments"])
    online_pct = int(data["running"] * 100 / total) if data["deployments"] else 0
    return (
        f"📈 <b>Statistika</b>\n"
        f"<i>{settings.brand_name}</i>\n"
        f"{DIV}\n\n"
        f"<b>Biznes</b>\n"
        f"👥 Users: <b>{data['users']}</b>\n"
        f"💎 Active sub: <b>{data['active_subs']}</b>\n"
        f"⭐ Stars jami: <b>{data['stars']}</b>\n"
        f"💳 Success to‘lov: <b>{data['payments']}</b>\n"
        f"💵 Joriy narx: <b>{price}★</b>\n"
        f"Toggle: <b>{'ON' if pay_on else 'OFF (test)'}</b>\n\n"
        f"<b>Infratuzilma</b>\n"
        f"🤖 Bots: <b>{data['deployments']}</b>\n"
        f"🟢 Online: <b>{data['running']}</b> ({online_pct}%)\n"
        f"⏸ Stop: <b>{data['stopped']}</b>\n"
        f"🔴 Suspend: <b>{data['suspended']}</b>\n"
        f"⚠️ Failed: <b>{data['failed']}</b>\n"
        f"🟡 Provision: <b>{data.get('provisioning', 0)}</b>\n\n"
        f"{DIV}\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )


def _system() -> str:
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.2)
        vm = psutil.virtual_memory()
        disk = shutil.disk_usage(str(ROOT_DIR))
        return (
            f"🖥 <b>System</b>\n{DIV}\n\n"
            f"CPU: <b>{cpu:.0f}%</b>\n"
            f"RAM: <b>{vm.percent:.0f}%</b> ({vm.used//1024//1024}/{vm.total//1024//1024} MB)\n"
            f"Disk: <b>{disk.used/1024**3:.1f}/{disk.total/1024**3:.1f} GB</b>\n"
            f"Path: <code>{ROOT_DIR}</code>"
        )
    except Exception as e:  # noqa: BLE001
        return f"🖥 System\n\n{e}"


def _bot_card(dep, metrics: dict) -> str:
    name = f"@{dep.bot_username}" if dep.bot_username else f"#{dep.id}"
    owner = f"<code>{dep.user.telegram_id}</code> @{dep.user.username or '—'}" if dep.user else "—"
    err = f"\n⚠️ <code>{(dep.last_error or '')[:140]}</code>" if dep.last_error else ""
    return (
        f"🤖 <b>{name}</b> #{dep.id}\n{DIV}\n\n"
        f"Status: <b>{dep.status}</b>\n"
        f"Owner: {owner}\n"
        f"Slug: <code>{dep.slug}</code>\n"
        f"PID: <code>{dep.process_pid or '—'}</code>\n"
        f"CPU {metrics.get('cpu','—')} · RAM {metrics.get('ram','—')}\n"
        f"DB {metrics.get('db_size','—')} · Backup {metrics.get('last_backup','—')}{err}"
    )


# ── Entry ──────────────────────────────────────────────

@router.message(Command("admin"))
@router.message(F.text == "🛠 Admin")
async def admin_entry(
    message: Message,
    state: FSMContext,
    settings: Settings,
    billing: BillingService,
    store: Store,
) -> None:
    await safe_delete_message(message)
    if not message.from_user or not _ok(message.from_user.id, settings):
        await message.answer("🚫 Admin panel faqat egasi uchun.\nADMIN_TELEGRAM_IDS ni .env ga yozing.")
        return
    await state.clear()
    data = await billing.admin_overview()
    price = await store.price_stars()
    pay = await store.payments_on()
    await show(
        message.bot,
        message.chat.id,
        state,
        _stats(data, settings, price, pay),
        home_kb(),
    )


@router.callback_query(F.data == "adm:menu")
@router.callback_query(F.data == "adm:stats")
async def adm_stats(cb: CallbackQuery, settings: Settings, billing: BillingService, store: Store) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    data = await billing.admin_overview()
    text = _stats(data, settings, await store.price_stars(), await store.payments_on())
    try:
        await cb.message.edit_text(text, reply_markup=home_kb())
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=home_kb())


@router.callback_query(F.data == "adm:sys")
async def adm_sys(cb: CallbackQuery, settings: Settings) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    try:
        await cb.message.edit_text(_system(), reply_markup=home_kb())
    except Exception:  # noqa: BLE001
        await cb.message.answer(_system(), reply_markup=home_kb())


# ── Cache ──────────────────────────────────────────────

@router.callback_query(F.data == "adm:cache")
async def adm_cache(cb: CallbackQuery, settings: Settings, store: Store) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    store.clear_cache()
    clear_settings_cache()
    # pycache light clean under builder/
    removed = 0
    for p in Path(ROOT_DIR / "builder").rglob("__pycache__"):
        try:
            shutil.rmtree(p, ignore_errors=True)
            removed += 1
        except Exception:  # noqa: BLE001
            pass
    # clear failed deploy error fields? optional no
    await cb.message.answer(
        f"🧹 <b>Kesh tozalandi</b>\n\n"
        f"• Settings cache\n"
        f"• Store cache\n"
        f"• __pycache__ papkalar: {removed}\n\n"
        f"Bot restart shart emas.",
        reply_markup=home_kb(),
    )


# ── Payment settings ───────────────────────────────────

@router.callback_query(F.data == "adm:paycfg")
async def adm_paycfg(cb: CallbackQuery, settings: Settings, store: Store, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    price = await store.price_stars()
    pay = await store.payments_on()
    promo = await store.promo_cfg()
    days = await store.sub_days()
    text = (
        f"💳 <b>To‘lov sozlamalari</b>\n{DIV}\n\n"
        f"Holat: <b>{'🟢 YOQILGAN (Stars)' if pay else '🔴 O‘CHIQ (test)'}</b>\n"
        f"Asosiy narx: <b>{price}★</b> / <b>{days}</b> kun\n"
        f"Promo: <b>{'ON' if promo['enabled'] else 'OFF'}</b> (−{promo['discount']}★)\n"
        f"Effective: <b>{await store.effective_base_price()}★</b>\n"
        f"Grace: <b>{settings.grace_period_days}</b> kun\n\n"
        f"⭐ Telegram Stars (XTR) · o‘zgarish darhol."
    )
    try:
        await cb.message.edit_text(text, reply_markup=paycfg_kb(pay))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=paycfg_kb(pay))


@router.callback_query(F.data.startswith("adm:pay:"))
async def adm_pay_act(cb: CallbackQuery, state: FSMContext, settings: Settings, store: Store) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    parts = (cb.data or "").split(":")
    act = parts[2] if len(parts) > 2 else ""

    if act == "toggle":
        cur = await store.payments_on()
        await store.set(KEY_PAYMENTS, "0" if cur else "1")
        await cb.message.answer(f"To‘lov: <b>{'O‘CHIRILDI' if cur else 'YOQILDI'}</b>")
    elif act == "price" and len(parts) > 3:
        await store.set(KEY_PRICE, parts[3])
        await cb.message.answer(f"Narx: <b>{parts[3]}★</b>")
    elif act == "promo":
        cfg = await store.promo_cfg()
        await store.set(KEY_PROMO_ON, "0" if cfg["enabled"] else "1")
        await cb.message.answer(f"Promo: <b>{'OFF' if cfg['enabled'] else 'ON'}</b>")
    elif act == "pdisc" and len(parts) > 3:
        await store.set(KEY_PROMO_DISC, parts[3])
        await cb.message.answer(f"Promo chegirma: −{parts[3]}★")
    elif act == "custom":
        await state.set_state(AdminStates.set_price)
        await cb.message.answer("Yangi narxni yozing (masalan 280):\n/cancel")
        return
    # refresh
    price = await store.price_stars()
    pay = await store.payments_on()
    promo = await store.promo_cfg()
    days = await store.sub_days()
    text = (
        f"💳 <b>To‘lov sozlamalari</b>\n{DIV}\n\n"
        f"Holat: <b>{'🟢 YOQILGAN (Stars)' if pay else '🔴 O‘CHIQ'}</b>\n"
        f"Narx: <b>{price}★</b> / <b>{days}</b> kun\n"
        f"Promo: {'ON' if promo['enabled'] else 'OFF'} (−{promo['discount']})\n"
        f"Effective: <b>{await store.effective_base_price()}★</b>"
    )
    try:
        await cb.message.edit_text(text, reply_markup=paycfg_kb(pay))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=paycfg_kb(pay))


@router.message(AdminStates.set_price, F.text)
async def adm_set_price(message: Message, state: FSMContext, settings: Settings, store: Store) -> None:
    if not message.from_user or not _ok(message.from_user.id, settings):
        return
    t = (message.text or "").strip()
    if t.startswith("/"):
        await state.clear()
        await message.answer("Bekor.", reply_markup=main_menu(is_admin=True))
        return
    if not t.isdigit() or int(t) < 50:
        await message.answer("Minimum 50 Stars. Qayta yozing.")
        return
    await store.set(KEY_PRICE, t)
    await state.clear()
    await message.answer(f"✅ Narx: <b>{t}★</b>", reply_markup=main_menu(is_admin=True))


# ── Promo codes ────────────────────────────────────────

@router.callback_query(F.data == "adm:promo")
async def adm_promo(cb: CallbackQuery, settings: Settings, store: Store) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    promos = await store.list_promos()
    text = (
        f"🏷 <b>Promokodlar</b>\n{DIV}\n\n"
        f"Jami: <b>{len(promos)}</b>\n"
        f"Turlar: stars · percent · days · credit\n"
        f"Tugmani bosing → ON/OFF"
    )
    try:
        await cb.message.edit_text(text, reply_markup=promo_kb(promos))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=promo_kb(promos))


@router.callback_query(F.data.startswith("adm:ptog:"))
async def adm_ptog(cb: CallbackQuery, settings: Settings, store: Store) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    pid = int((cb.data or "").split(":")[-1])
    p = await store.toggle_promo(pid)
    await cb.message.answer(f"{'✅' if p and p.active else '⏸'} {p.code if p else '?'}")
    promos = await store.list_promos()
    try:
        await cb.message.edit_reply_markup(reply_markup=promo_kb(promos))
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("adm:pauto:"))
async def adm_pauto(cb: CallbackQuery, settings: Settings, store: Store) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    # adm:pauto:stars:50
    parts = (cb.data or "").split(":")
    kind = parts[2] if len(parts) > 2 else "stars"
    val = int(parts[3]) if len(parts) > 3 else 50
    code = gen_code("MF")
    try:
        p = await store.create_promo(code, kind, val, max_uses=50, note="auto", days_valid=30)
        await cb.message.answer(f"✅ Yaratildi: <code>{p.code}</code>\n{kind}:{val}")
    except Exception as e:  # noqa: BLE001
        await cb.message.answer(friendly_error(e))
    promos = await store.list_promos()
    try:
        await cb.message.edit_text(
            f"🏷 <b>Promokodlar</b> · {len(promos)}",
            reply_markup=promo_kb(promos),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "adm:pnew")
async def adm_pnew(cb: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    await state.set_state(AdminStates.promo_create)
    await cb.message.answer(
        "🏷 <b>Yangi promokod</b>\n\n"
        "Format:\n"
        "<code>KOD TUR QIYMAT LIMIT</code>\n\n"
        "Misollar:\n"
        "<code>SALE50 stars 50 100</code>\n"
        "<code>WEEK days 7 50</code>\n"
        "<code>HALF percent 50 20</code>\n"
        "<code>BONUS credit 100 30</code>\n\n"
        "/cancel"
    )


@router.message(AdminStates.promo_create, F.text)
async def adm_pcreate(message: Message, state: FSMContext, settings: Settings, store: Store) -> None:
    if not message.from_user or not _ok(message.from_user.id, settings):
        return
    t = (message.text or "").strip()
    if t.startswith("/"):
        await state.clear()
        await message.answer("Bekor.", reply_markup=main_menu(is_admin=True))
        return
    parts = t.split()
    if len(parts) < 3:
        await message.answer("Format: KOD TUR QIYMAT [LIMIT]")
        return
    code, kind, val = parts[0], parts[1].lower(), parts[2]
    limit = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 100
    if kind not in {"stars", "percent", "days", "credit"}:
        await message.answer("TUR: stars | percent | days | credit")
        return
    if not val.isdigit():
        await message.answer("QIYMAT raqam bo‘lsin")
        return
    try:
        p = await store.create_promo(code, kind, int(val), max_uses=limit, note="admin")
        await state.clear()
        await message.answer(f"✅ <code>{p.code}</code> yaratildi", reply_markup=main_menu(is_admin=True))
    except Exception as e:  # noqa: BLE001
        await message.answer(str(e)[:200])


# ── Bots ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:bots"))
async def adm_bots(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    page = 0
    parts = (cb.data or "").split(":")
    if len(parts) >= 3 and parts[2].isdigit():
        page = int(parts[2])
    data = await billing.admin_overview()
    deps = [d for d in data["deps"] if d.status != "deleted"]
    text = f"🤖 <b>Botlar</b> · {len(deps)}"
    try:
        await cb.message.edit_text(text, reply_markup=bots_kb(deps, page=page))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=bots_kb(deps, page=page))


@router.callback_query(F.data.startswith("adm:botsf:"))
async def adm_botsf(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    parts = (cb.data or "").split(":")
    filt = parts[2] if len(parts) > 2 else "running"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    data = await billing.admin_overview()
    deps = [d for d in data["deps"] if d.status != "deleted"]
    n = sum(1 for d in deps if d.status == filt)
    text = f"🤖 <b>{filt}</b> · {n}"
    try:
        await cb.message.edit_text(text, reply_markup=bots_kb(deps, page=page, filt=filt))
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=bots_kb(deps, page=page, filt=filt))


@router.callback_query(F.data.startswith("adm:bot:"))
async def adm_bot(
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
        await cb.message.answer("Topilmadi")
        return
    m = deploy.metrics(dep.id, dep.project_path, dep.process_pid, dep.slug)
    try:
        await cb.message.edit_text(_bot_card(dep, m), reply_markup=bot_kb(dep_id))
    except Exception:  # noqa: BLE001
        await cb.message.answer(_bot_card(dep, m), reply_markup=bot_kb(dep_id))


@router.callback_query(F.data.startswith("adm:act:"))
async def adm_act(
    cb: CallbackQuery,
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
            f"🗑 <b>{name}</b> purge?\nDB+fayl+backup o‘chadi.",
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
            p = await deploy.backup(dep_id)
            note = f"💾 {p.name}"
        elif action == "logs":
            t = await deploy.read_logs(dep_id, 40)
            safe = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            await cb.message.answer(f"<pre>{safe[-3500:]}</pre>" if safe else "Log yo‘q")
            return
        elif action == "days7":
            if dep and dep.user:
                await billing.grant_bonus_days(dep.user.telegram_id, 7)
                note = "➕ +7 kun"
            else:
                note = "Owner yo‘q"
        elif action == "purge":
            await deploy.purge(dep_id)
            await cb.message.edit_text("🗑 Purge OK", reply_markup=home_kb())
            return
        else:
            note = "OK"
        await cb.answer(note, show_alert=False)
        await cb.message.answer(note)
        dep2 = await billing.get_deployment(dep_id)
        if dep2:
            m = deploy.metrics(dep2.id, dep2.project_path, dep2.process_pid, dep2.slug)
            await cb.message.answer(_bot_card(dep2, m), reply_markup=bot_kb(dep_id))
    except Exception as e:  # noqa: BLE001
        logger.exception("adm act")
        await cb.message.answer(friendly_error(e))


@router.callback_query(F.data.startswith("adm:msg:"))
async def adm_msg(cb: CallbackQuery, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    dep_id = int((cb.data or "").split(":")[-1])
    dep = await billing.get_deployment(dep_id)
    if not dep or not dep.user:
        await cb.message.answer("Owner yo‘q")
        return
    await state.set_state(AdminStates.msg_owner)
    await state.update_data(msg_tg=dep.user.telegram_id)
    await cb.message.answer(f"📨 <code>{dep.user.telegram_id}</code> ga yozing\n/cancel")


@router.message(AdminStates.msg_owner, F.text)
async def adm_msg_send(message: Message, state: FSMContext, settings: Settings) -> None:
    if not message.from_user or not _ok(message.from_user.id, settings):
        return
    t = (message.text or "").strip()
    if t.startswith("/"):
        await state.clear()
        await message.answer("Bekor.", reply_markup=main_menu(is_admin=True))
        return
    tg = (await state.get_data()).get("msg_tg")
    await state.clear()
    try:
        await message.bot.send_message(int(tg), f"📩 <b>Admin</b>\n\n{t}")
        await message.answer("✅", reply_markup=main_menu(is_admin=True))
    except Exception as e:  # noqa: BLE001
        await message.answer(friendly_error(e))


# ── Users / pays / broadcast ───────────────────────────

@router.callback_query(F.data.startswith("adm:users"))
async def adm_users(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    page = int((cb.data or "adm:users:0").split(":")[-1] or 0)
    users = await billing.list_users(300)
    per = 15
    chunk = users[page * per : (page + 1) * per]
    lines = [f"👥 <b>Users</b> · {len(users)}\n{DIV}"]
    for u in chunk:
        lines.append(f"• <code>{u.telegram_id}</code> @{u.username or '—'} · ★{u.credit_stars or 0}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️", callback_data=f"adm:users:{max(0, page - 1)}"),
                InlineKeyboardButton(text="▶️", callback_data=f"adm:users:{page + 1}"),
            ],
            [InlineKeyboardButton(text="🛠", callback_data="adm:menu")],
        ]
    )
    try:
        await cb.message.edit_text("\n".join(lines), reply_markup=kb)
    except Exception:  # noqa: BLE001
        await cb.message.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(F.data == "adm:pays")
async def adm_pays(cb: CallbackQuery, settings: Settings, billing: BillingService) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    data = await billing.admin_overview()
    from sqlalchemy import select
    from builder.db import get_session_factory
    from builder.models import Payment, User

    sf = get_session_factory()
    lines = [
        f"💰 <b>Payments</b>\n{DIV}",
        f"Success: <b>{data['payments']}</b> · Stars: <b>{data['stars']}</b>\n",
    ]
    async with sf() as s:
        pays = (await s.execute(select(Payment).order_by(Payment.id.desc()).limit(20))).scalars().all()
        for p in pays:
            u = await s.get(User, p.user_id)
            un = f"@{u.username}" if u and u.username else str(getattr(u, "telegram_id", p.user_id))
            st = "✅" if p.status == "success" else "⏳"
            lines.append(f"{st} <b>{p.amount_stars}</b>★ · {un} · {p.purpose}")
    try:
        await cb.message.edit_text("\n".join(lines), reply_markup=home_kb())
    except Exception:  # noqa: BLE001
        await cb.message.answer("\n".join(lines), reply_markup=home_kb())


@router.callback_query(F.data == "adm:bc")
async def adm_bc(cb: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await safe_cb(cb)
    if not await _guard(cb, settings) or not cb.message:
        return
    await state.set_state(AdminStates.broadcast)
    await cb.message.answer("📢 Reklama matnini yozing (HTML mumkin)\n/cancel")


@router.message(AdminStates.broadcast, F.text)
async def adm_bc_send(message: Message, state: FSMContext, settings: Settings, billing: BillingService) -> None:
    if not message.from_user or not _ok(message.from_user.id, settings):
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("Bekor.", reply_markup=main_menu(is_admin=True))
        return
    users = await billing.list_users(2000)
    ok = fail = 0
    prog = await message.answer(f"⏳ 0/{len(users)}")
    for i, u in enumerate(users, 1):
        try:
            await message.bot.send_message(u.telegram_id, f"📢 <b>E’lon</b>\n\n{text}")
            ok += 1
        except Exception:  # noqa: BLE001
            fail += 1
        if i % 30 == 0:
            try:
                await prog.edit_text(f"⏳ {i}/{len(users)}")
            except Exception:  # noqa: BLE001
                pass
    await state.clear()
    await message.answer(f"✅ {ok} · ❌ {fail}", reply_markup=main_menu(is_admin=True))
