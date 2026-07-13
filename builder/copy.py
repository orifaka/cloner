"""Premium conversion UI — visual blocks, sales psychology, UZ."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from builder.config import Settings

DIV = "━━━━━━━━━━━━━━━━"


def intro(s: Settings) -> str:
    base, d = s.subscription_price_stars, s.subscription_days
    price = s.effective_price
    promo = ""
    if s.promo_enabled and price < base:
        promo = (
            f"\n┏━━━━━━━━━━━━━━━━┓\n"
            f"  {s.promo_title}\n"
            f"  {s.promo_text}\n"
            f"  ⭐ <s>{base}</s> → <b>{price}</b> Stars\n"
            f"┗━━━━━━━━━━━━━━━━┛\n"
        )
    per = max(1, price // max(1, d))
    return (
        f"🕹 <b>{s.brand_name}</b>\n"
        f"<i>Guruhingiz uchun professional Mafia hosting</i>\n"
        f"{promo}\n"
        f"<b>1 daqiqada o‘z botingiz</b>\n"
        f"Token berasiz → biz deploy qilamiz → guruh o‘ynaydi.\n\n"
        f"<b>Nima olasiz</b>\n"
        f"├ Mustaqil bot (sizning token)\n"
        f"├ Avto hosting · start/stop/restart\n"
        f"├ AES shifr · backup · monitoring\n"
        f"└ Texnik bilim <b>shart emas</b>\n\n"
        f"<b>Narx</b>\n"
        f"⭐ <b>{price} Stars</b> / {d} kun  ·  ~{per}/kun\n\n"
        f"🔐 Token faqat shifrlangan holda saqlanadi\n"
        f"👑 Siz — yagona egasi va admin\n\n"
        f"{DIV}\n"
        f"👇 <b>Tanlang va boshlang</b>"
    )


def pricing_pitch(s: Settings, *, final_price: Optional[int] = None, tags: Optional[list[str]] = None) -> str:
    base, d = s.subscription_price_stars, s.subscription_days
    p = final_price if final_price is not None else s.effective_price
    tags_s = (" · ".join(tags) + "\n\n") if tags else ""
    price_l = f"⭐ <s>{base}</s> → <b>{p} Stars</b>" if p < base else f"⭐ <b>{p} Stars</b>"
    return (
        f"💎 <b>Premium obuna</b>\n"
        f"{DIV}\n\n"
        f"{tags_s}"
        f"{price_l}\n"
        f"📅 {d} kun to‘liq xizmat\n\n"
        f"<b>Paket ichida</b>\n"
        f"• Mafia bot + hosting\n"
        f"• Deploy · backup · log\n"
        f"• Support · yangilanishlar\n\n"
        f"<b>Kafolat</b>\n"
        f"Muddat tugasa → suspend\n"
        f"7 kun ichida renew → to‘liq tiklash\n"
        f"Keyin ma’lumotlar o‘chiriladi\n\n"
        f"{DIV}\n"
        f"💳 To‘lov oldidan: xizmat avtomatik, token shifrlangan,\n"
        f"bekor qilish My Bots → O‘chirish orqali."
    )


def faq_text(s: Settings) -> str:
    p = s.effective_price
    return (
        f"❓ <b>Tez-tez so‘raladigan savollar</b>\n"
        f"{DIV}\n\n"
        f"<b>1. Server kerakmi?</b>\n"
        f"Yo‘q. Hammasi bizning hostingda.\n\n"
        f"<b>2. Token xavfsizmi?</b>\n"
        f"Ha. AES bilan shifrlanadi, chatdan o‘chiriladi.\n\n"
        f"<b>3. Qancha turadi?</b>\n"
        f"⭐ {p} Stars / {s.subscription_days} kun.\n\n"
        f"<b>4. Bot o‘chib qolsa?</b>\n"
        f"Monitoring qayta yoqadi / restart tugmasi bor.\n\n"
        f"<b>5. Obuna tugasa nima bo‘ladi?</b>\n"
        f"Darhol suspend. 7 kun ichida renew = tiklanadi.\n\n"
        f"<b>6. O‘zim admin bo‘lamanmi?</b>\n"
        f"Ha. Sizning ID avtomatik ADMIN_IDS ga yoziladi.\n\n"
        f"Yana savol? 💬 Support"
    )


def help_text(s: Settings) -> str:
    return (
        f"📘 <b>3 qadamda start</b>\n"
        f"{DIV}\n\n"
        f"1️⃣ <b>Bot ochish</b>\n"
        f"2️⃣ @BotFather token yuboring\n"
        f"3️⃣ Guruhga admin qilib qo‘shing → <code>/game</code>\n\n"
        f"<b>Menyu</b>\n"
        f"✨ Bot ochish · 🤖 Botlarim · 💎 Obuna\n"
        f"🎁 Referal · 📋 To‘lovlar · ❓ FAQ\n\n"
        f"Support: {s.support_url}"
    )


def subscription_card(
    s: Settings,
    *,
    status: Optional[str],
    days_left: Optional[int],
    expires: Optional[str],
    keep_offer: bool = False,
) -> str:
    st = {
        "active": "🟢 Faol",
        "grace": "🟡 Suspend · tiklash mumkin",
        "expired": "🔴 Tugagan",
        "pending": "⚪ Kutilmoqda",
        None: "⚪ Obuna yo‘q",
    }.get(status, f"⚪ {status}")
    left = "—" if days_left is None else f"<b>{days_left}</b> kun"
    offer = ""
    if keep_offer:
        off = getattr(s, "keep_offer_discount", 30)
        offer = (
            f"\n\n┏━━━━━━━━━━━━━━┓\n"
            f"  🧡 SAQLAB QOLING\n"
            f"  Oxirgi kunlar · −{off} Stars\n"
            f"┗━━━━━━━━━━━━━━┛"
        )
    return (
        f"💎 <b>Obuna holati</b>\n"
        f"{DIV}\n\n"
        f"Tarif: <b>{s.subscription_price_stars}★</b> / {s.subscription_days} kun\n"
        f"Holat: {st}\n"
        f"Qolgan: {left}\n"
        f"Tugash: <code>{expires or '—'}</code>"
        f"{offer}\n\n"
        f"Suspend bo‘lsa — 7 kun ichida renew qiling."
    )


def dashboard(stats: dict[str, Any]) -> str:
    return (
        f"📊 <b>Kabinet</b>\n"
        f"{DIV}\n\n"
        f"┌ Botlar     <b>{stats.get('bots', 0)}</b>\n"
        f"│ Online     <b>{stats.get('running', 0)}</b>\n"
        f"│ Stop       <b>{stats.get('stopped', 0)}</b>\n"
        f"└ Suspend    <b>{stats.get('suspended', 0)}</b>\n\n"
        f"Obuna: <b>{stats.get('sub_status', '—')}</b>\n"
        f"Qolgan: <b>{stats.get('days_left', '—')}</b> kun"
    )


def payments_history(rows: list[dict]) -> str:
    if not rows:
        return (
            f"📋 <b>To‘lovlarim</b>\n"
            f"{DIV}\n\n"
            f"Hali to‘lov yo‘q.\n"
            f"Birinchi obunani oching ⭐"
        )
    lines = [f"📋 <b>To‘lovlarim</b>\n{DIV}\n"]
    for r in rows[:15]:
        lines.append(
            f"{'✅' if r['status']=='success' else '⏳'} "
            f"<b>{r['amount']}</b>★ · {r['purpose']} · <code>{r['date']}</code>"
        )
    return "\n".join(lines)


def ask_token() -> str:
    return (
        f"🔑 <b>Token yuboring</b>\n"
        f"{DIV}\n\n"
        f"1. <b>@BotFather</b> oching\n"
        f"2. Token nusxalang\n"
        f"3. Shu chatga yuboring\n\n"
        f"🔒 Shifrlanadi · chatdan o‘chiriladi\n"
        f"👑 Siz avtomatik admin bo‘lasiz\n\n"
        f"<i>/cancel — bekor</i>"
    )


def deploy_progress(step: int, label: str = "") -> str:
    stages = [
        "Token tekshiruvi",
        "Ma’lumotlar bazasi",
        "Konfiguratsiya",
        "Deploy",
        "Health check",
        "Online",
    ]
    bar = ""
    for i, name in enumerate(stages, 1):
        if i < step:
            bar += "█"
        elif i == step:
            bar += "▓"
        else:
            bar += "░"
    lines = [
        f"🚀 <b>Deploy</b>",
        f"<code>[{bar}]</code>  {min(step,6)}/6",
        f"{DIV}",
    ]
    for i, name in enumerate(stages, 1):
        if i < step:
            m = "✅"
        elif i == step:
            m = "🔵"
        else:
            m = "⚪"
        extra = f"\n    <i>{label}</i>" if i == step and label else ""
        lines.append(f"{m} {name}{extra}")
    lines.append(f"\n<i>30–90 soniya…</i>")
    return "\n".join(lines)


def deploy_done(username: Optional[str], days: int, expires: Optional[str] = None) -> str:
    name = f"@{username}" if username else "Bot"
    exp = f"\n📅 <code>{expires}</code>" if expires else ""
    return (
        f"🎉 <b>Bot tayyor!</b>\n"
        f"{DIV}\n\n"
        f"{name}  ·  🟢 <b>ONLINE</b>\n"
        f"⏱ {days} kun{exp}\n\n"
        f"<b>Checklist</b>\n"
        f"☐ Botni guruhga <b>admin</b> qilib qo‘shing\n"
        f"☐ Guruhda <code>/game</code> yozing\n"
        f"☐ Do‘stlarni chaqiring 🎮\n\n"
        f"Pastdagi tugma bilan guruhga qo‘shing 👇"
    )


def bot_card(
    *,
    username: Optional[str],
    status: str,
    days_left: Optional[int],
    expires: Optional[str],
    cpu: str,
    ram: str,
    db_size: str,
    last_backup: str,
    error_friendly: Optional[str] = None,
) -> str:
    icon = {
        "running": "🟢 Online",
        "stopped": "⏸ Stop",
        "suspended": "🔴 Suspend",
        "failed": "⚠️ Diqqat",
        "provisioning": "🟡 Deploy",
        "deleted": "🗑",
    }.get(status, status)
    name = f"@{username}" if username else "Bot"
    left = "—" if days_left is None else f"{days_left} kun"
    urgency = ""
    if days_left is not None:
        if days_left <= 1:
            urgency = "\n\n🔴 <b>Ertaga tugaydi!</b> Yangilang."
        elif days_left <= 3:
            urgency = "\n\n🧡 <b>3 kun qoldi</b> — maxsus keep-offer bor."
        elif days_left <= 7:
            urgency = "\n\n🟡 Tez orada tugaydi."
    text = (
        f"🤖 <b>{name}</b>\n"
        f"{DIV}\n\n"
        f"{icon}\n"
        f"⏳ {left}  ·  📅 <code>{expires or '—'}</code>\n\n"
        f"<b>Resurs</b>\n"
        f"CPU <b>{cpu}</b>  ·  RAM <b>{ram}</b>\n"
        f"DB <b>{db_size}</b>  ·  Backup <b>{last_backup}</b>"
        f"{urgency}"
    )
    if error_friendly:
        text += f"\n\nℹ️ {error_friendly}"
    return text


def empty_bots() -> str:
    return (
        f"🤖 <b>Botlarim</b>\n"
        f"{DIV}\n\n"
        f"Hali bot yo‘q.\n\n"
        f"Birinchi Mafia botingizni oching —\n"
        f"guruhingiz bugun o‘ynashi mumkin."
    )


def friendly_error(exc: BaseException | str) -> str:
    raw = str(exc).lower()
    if "token" in raw or "yaroqsiz" in raw or "formati" in raw or "invalid" in raw:
        return (
            f"❌ <b>Token qabul qilinmadi</b>\n{DIV}\n\n"
            f"@BotFather dan yangi token oling va qayta yuboring."
        )
    if "python" in raw or "runtime" in raw or "import" in raw:
        return (
            f"⚙️ <b>Vaqtinchalik nosozlik</b>\n{DIV}\n\n"
            f"Birozdan keyin qayta urinib ko‘ring yoki Support."
        )
    if "permission" in raw or "access" in raw:
        return "🚫 <b>Ruxsat yo‘q</b>"
    if "not found" in raw or "yo'q" in raw:
        return "🔍 Topilmadi. Yangi bot oching."
    return (
        f"😕 <b>Xato yuz berdi</b>\n{DIV}\n\n"
        f"Qayta urinib ko‘ring. Davom etsa — Support."
    )


def remind_7d(s: Settings) -> str:
    return (
        f"📅 <b>7 kun qoldi</b>\n\n"
        f"Obuna tez orada tugaydi.\n"
        f"⭐ {s.effective_price} Stars — uzluksiz ishlash.\n"
        f"💎 Obuna → Yangilash"
    )


def remind_3d(s: Settings) -> str:
    off = getattr(s, "keep_offer_discount", 30)
    return (
        f"🧡 <b>3 kun qoldi · KEEP OFFER</b>\n\n"
        f"Hozir yangilasangiz −{off} Stars chegirma.\n"
        f"⭐ ~{max(50, s.effective_price - off)} Stars\n"
        f"💎 Obuna"
    )


def remind_24h(s: Settings) -> str:
    return (
        f"🔴 <b>24 soat!</b>\n\n"
        f"Ertaga bot suspend bo‘ladi.\n"
        f"Hozir yangilang — hech narsa yo‘qolmasin.\n"
        f"⭐ {s.effective_price} Stars"
    )


def remind_expired(s: Settings) -> str:
    return (
        f"⏸ <b>Suspend</b>\n{DIV}\n\n"
        f"Bot to‘xtatildi. Ma’lumotlar 7 kun saqlanadi.\n"
        f"Renew → to‘liq tiklanadi.\n"
        f"⚠️ 7 kundan keyin butunlay o‘chadi.\n\n"
        f"⭐ {s.effective_price} Stars"
    )


def remind_grace_daily(days_left: int) -> str:
    return (
        f"🔴 Suspend · o‘chirishga <b>{days_left}</b> kun\n\n"
        f"Hozir renew — bot qaytadi."
    )


def delete_warning(username: Optional[str]) -> str:
    name = f"@{username}" if username else "bot"
    return (
        f"🗑 <b>{name} o‘chirilsinmi?</b>\n{DIV}\n\n"
        f"Qaytarib bo‘lmaydi:\n"
        f"• Process · DB · fayllar · backup\n\n"
        f"Davom etasizmi?"
    )


def settings_text(s: Settings, lang: str) -> str:
    pay = "⭐ Stars" if s.payments_enabled else "🧪 Test"
    return (
        f"⚙️ <b>Sozlamalar</b>\n{DIV}\n\n"
        f"Til: <b>{lang or 'uz'}</b>\n"
        f"To‘lov: <b>{pay}</b>\n"
        f"Support: {s.support_url}"
    )


def payment_sent(s: Settings) -> str:
    return (
        f"⭐ <b>Hisob-faktura yuborildi</b>\n\n"
        f"Telegramda to‘lovni tasdiqlang.\n"
        f"Chegirma bo‘lsa — summa kamaygan."
    )


def payment_ok() -> str:
    return (
        f"✅ <b>To‘lov qabul qilindi!</b>\n{DIV}\n\n"
        f"Obuna faol. Token yuboring — deploy boshlanadi."
    )


def referral_card(stats: dict, s: Settings) -> str:
    return (
        f"🎁 <b>Referal dasturi</b>\n{DIV}\n\n"
        f"Linkingiz:\n<code>{stats.get('link','—')}</code>\n\n"
        f"Kod: <code>{stats.get('code','—')}</code>\n"
        f"Takliflar: <b>{stats.get('invites',0)}</b>\n"
        f"Bonus: <b>{stats.get('credit',0)}</b>★\n\n"
        f"Do‘st kirsa → u −{s.referral_invitee_discount}★\n"
        f"U to‘lasa → siz +{s.referral_reward_days} kun"
    )


def fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M UTC")
