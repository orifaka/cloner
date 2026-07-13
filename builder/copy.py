"""
Premium conversion-focused copy (UZ).
Sales psychology: benefit → proof → price → risk reverse → CTA.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from builder.config import Settings

# visual separators (Telegram-safe)
_HR = "──────────────"


def intro(s: Settings) -> str:
    p, d = s.subscription_price_stars, s.subscription_days
    return (
        f"🕹 <b>{s.brand_name}</b>\n"
        f"<i>Professional Mafia Bot Hosting</i>\n"
        f"{_HR}\n\n"
        "Guruhingiz uchun <b>to‘liq avtomatik Mafia bot</b> —\n"
        "server, sozlash va texnik og‘irlik <b>bizda</b>.\n\n"
        "Siz faqat token berasiz.\n"
        "Biz 60 soniyada ishga tushiramiz.\n\n"
        f"<b>Nega tanlashadi</b>\n"
        "✅ O‘z botingiz · o‘z auditoriyangiz\n"
        "✅ 1-click deploy · start / stop / restart\n"
        "✅ Token shifrlanadi · ma’lumot himoyalangan\n"
        "✅ Backup · monitoring · 24/7 online\n"
        "✅ Texnik bilim shart emas\n\n"
        f"<b>Tarif</b>\n"
        f"⭐ <b>{p} Stars</b>  ·  {d} kun to‘liq hosting\n"
        "Kuniga atigi ~10 Stars\n\n"
        f"<b>Xavfsizlik</b>\n"
        "🔐 AES encryption · alohida izolyatsiya\n"
        "👑 Siz — botning yagona egasi va admini\n\n"
        f"{_HR}\n"
        "👇 <b>Hoziroq boshlang</b> — birinchi botingiz tayyor"
    )


def pricing_pitch(s: Settings) -> str:
    p, d = s.subscription_price_stars, s.subscription_days
    return (
        f"💎 <b>Premium Plan</b>\n"
        f"{_HR}\n\n"
        f"⭐ <b>{p} Telegram Stars</b>\n"
        f"📅 <b>{d} kun</b> to‘liq xizmat\n\n"
        "<b>Ichiga kiradi</b>\n"
        "• Mustaqil Mafia bot\n"
        "• Avtomatik hosting & deploy\n"
        "• Restart / backup / loglar\n"
        "• Yangilanishlar & support\n\n"
        "<b>Kafolat</b>\n"
        "Muddat tugasa — avval suspend.\n"
        "7 kun ichida to‘lov → hammasi tiklanadi.\n"
        "Hech narsa yashirin emas.\n\n"
        f"{_HR}\n"
        "Eng arzon yo‘l — o‘zingiz server sotib olish emas,\n"
        f"<b>{p} Stars</b> bilan tayyor yechim."
    )


def help_text(s: Settings) -> str:
    return (
        f"❓ <b>Qanday ishlaydi?</b>\n"
        f"{_HR}\n\n"
        "<b>3 oddiy qadam</b>\n"
        "1️⃣ <b>Bot ochish</b> tugmasini bosing\n"
        "2️⃣ @BotFather dan token yuboring\n"
        "3️⃣ 1 daqiqada bot <b>Online</b>\n\n"
        "Keyin botni guruhga admin qilib qo‘shing\n"
        "va <code>/game</code> yozing — o‘yin boshlandi.\n\n"
        f"<b>Menyu</b>\n"
        "✨ Bot ochish — yangi deploy\n"
        "🤖 Botlarim — boshqaruv\n"
        "💎 Obuna — to‘lov & muddat\n"
        "📊 Kabinet — umumiy holat\n\n"
        f"💬 Yordam: {s.support_url}"
    )


def subscription_card(
    s: Settings,
    *,
    status: Optional[str],
    days_left: Optional[int],
    expires: Optional[str],
) -> str:
    st_map = {
        "active": "🟢 Faol",
        "grace": "🟡 Suspend · 7 kun ichida tiklash mumkin",
        "expired": "🔴 Muddati o‘tgan",
        "pending": "⚪ Kutilmoqda",
        None: "⚪ Hali obuna yo‘q",
    }
    st = st_map.get(status, f"⚪ {status}")
    left = "—" if days_left is None else f"<b>{days_left}</b> kun"
    exp = expires or "—"
    p, d = s.subscription_price_stars, s.subscription_days
    cta = (
        "Obunani yangilang — botingiz to‘xtab qolmasin."
        if status in {"active", "grace"}
        else "Obuna oling va o‘z botingizni ishga tushiring."
    )
    return (
        f"💎 <b>Obuna</b>\n"
        f"{_HR}\n\n"
        f"Tarif: <b>{p} Stars</b> / {d} kun\n"
        f"Holat: {st}\n"
        f"Qolgan: {left}\n"
        f"Tugash: <code>{exp}</code>\n\n"
        f"<b>Qoidalar</b>\n"
        "• Muddat tugashi → bot darhol suspend\n"
        "• 7 kun grace → renew = to‘liq tiklash\n"
        "• 7 kundan keyin → ma’lumotlar o‘chiriladi\n\n"
        f"{cta}"
    )


def dashboard(stats: dict[str, Any]) -> str:
    return (
        f"📊 <b>Kabinet</b>\n"
        f"{_HR}\n\n"
        f"🤖 Botlar: <b>{stats.get('bots', 0)}</b>\n"
        f"🟢 Online: <b>{stats.get('running', 0)}</b>\n"
        f"⏸ Stop: <b>{stats.get('stopped', 0)}</b>\n"
        f"🔴 Suspend: <b>{stats.get('suspended', 0)}</b>\n\n"
        f"💎 Obuna: <b>{stats.get('sub_status', '—')}</b>\n"
        f"⏳ Qolgan kun: <b>{stats.get('days_left', '—')}</b>\n\n"
        "Boshqarish: <b>🤖 Botlarim</b>"
    )


def ask_token() -> str:
    return (
        f"🔑 <b>Oxirgi qadam — token</b>\n"
        f"{_HR}\n\n"
        "1. Telegramda <b>@BotFather</b> oching\n"
        "2. <code>/newbot</code> yoki mavjud botni tanlang\n"
        "3. API token ni nusxalang\n"
        "4. <b>Shu yerga yuboring</b>\n\n"
        "🔒 Token shifrlanadi va chatdan o‘chiriladi\n"
        "👑 Siz avtomatik bot admini bo‘lasiz\n\n"
        "<i>Bekor: /cancel</i>"
    )


def deploy_progress(step: int, label: str = "") -> str:
    stages = [
        ("1", "Token tekshiruvi"),
        ("2", "Ma’lumotlar bazasi"),
        ("3", "Sozlamalar"),
        ("4", "Deploy"),
        ("5", "Health check"),
        ("6", "Online"),
    ]
    lines = [f"🚀 <b>Botingiz yaratilmoqda</b>\n{ _HR }\n"]
    for i, (_, name) in enumerate(stages, start=1):
        if i < step:
            mark = "✅"
        elif i == step:
            mark = "🔵"
        else:
            mark = "⚪"
        extra = f"\n   <i>{label}</i>" if i == step and label else ""
        lines.append(f"{mark}  {name}{extra}")
    lines.append(f"\n{_HR}\n<i>Odatda 30–90 soniya…</i>")
    return "\n".join(lines)


def deploy_done(username: Optional[str], days: int, expires: Optional[str] = None) -> str:
    name = f"@{username}" if username else "Botingiz"
    exp = f"\n📅 Amal qiladi: <code>{expires}</code>" if expires else ""
    return (
        f"🎉 <b>Tabriklaymiz!</b>\n"
        f"{_HR}\n\n"
        f"{name}  ·  🟢 <b>ONLINE</b>\n"
        f"⏱ Tarif: <b>{days} kun</b>{exp}\n\n"
        f"<b>Keyingi 2 qadam</b>\n"
        f"1. Botni guruhga <b>admin</b> qilib qo‘shing\n"
        f"2. Guruhda <code>/game</code> yozing\n\n"
        f"Boshqaruv: <b>🤖 Botlarim</b>\n"
        f"{_HR}\n"
        f"Omad! 🕹"
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
        "running": "🟢  Online",
        "stopped": "⏸  To‘xtatilgan",
        "suspended": "🔴  Suspend (to‘lov kutilmoqda)",
        "failed": "⚠️  Diqqat talab qiladi",
        "provisioning": "🟡  Deploy jarayoni",
        "deleted": "🗑  O‘chirilgan",
    }.get(status, f"⚪  {status}")
    name = f"@{username}" if username else "Bot"
    left = "—" if days_left is None else f"{days_left} kun"
    # urgency strip
    urgency = ""
    if days_left is not None:
        if days_left <= 1:
            urgency = "\n\n🔴 <b>Ertaga muddat tugaydi!</b> Obunani yangilang."
        elif days_left <= 3:
            urgency = "\n\n🟠 <b>3 kun qoldi</b> — renew qilishni unutmang."
        elif days_left <= 7:
            urgency = "\n\n🟡 Obuna tez orada tugaydi."
    text = (
        f"🤖 <b>{name}</b>\n"
        f"{_HR}\n\n"
        f"<b>Holat</b>\n{icon}\n\n"
        f"<b>Obuna</b>\n"
        f"⏳ Qolgan: <b>{left}</b>\n"
        f"📅 Tugash: <code>{expires or '—'}</code>\n\n"
        f"<b>Resurslar</b>\n"
        f"CPU  ·  <b>{cpu}</b>\n"
        f"RAM  ·  <b>{ram}</b>\n"
        f"DB   ·  <b>{db_size}</b>\n"
        f"Backup · <b>{last_backup}</b>"
        f"{urgency}"
    )
    if error_friendly:
        text += f"\n\nℹ️ {error_friendly}"
    return text


def empty_bots() -> str:
    return (
        f"🤖 <b>Botlarim</b>\n"
        f"{_HR}\n\n"
        "Hali bot yo‘q.\n\n"
        "Birinchi Mafia botingizni oching —\n"
        "1 daqiqada guruhingiz o‘ynashga tayyor."
    )


def friendly_error(exc: BaseException | str) -> str:
    raw = str(exc).lower()
    if "token" in raw or "yaroqsiz" in raw or "formati" in raw or "invalid" in raw:
        return (
            f"❌ <b>Token qabul qilinmadi</b>\n"
            f"{_HR}\n\n"
            "Token noto‘g‘ri yoki eskirgan.\n"
            "@BotFather dan yangi token oling va qayta yuboring."
        )
    if "python" in raw or "runtime" in raw or "import" in raw:
        return (
            f"⚙️ <b>Vaqtinchalik nosozlik</b>\n"
            f"{_HR}\n\n"
            "Server sozlamasi yakunlanmoqda.\n"
            "Birozdan keyin qayta urinib ko‘ring yoki Support ga yozing."
        )
    if "permission" in raw or "access" in raw or "ruxsat" in raw:
        return f"🚫 <b>Ruxsat yo‘q</b>\n\nBu amal uchun huquqingiz yetarli emas."
    if "not found" in raw or "yo'q" in raw or "topilmadi" in raw:
        return (
            f"🔍 <b>Topilmadi</b>\n\n"
            "Bu bot mavjud emas yoki o‘chirilgan.\n"
            "Yangi bot ochishingiz mumkin."
        )
    return (
        f"😕 <b>Kutilmagan xato</b>\n"
        f"{_HR}\n\n"
        "Qayta urinib ko‘ring.\n"
        "Davom etsa — Support orqali yozing.\n"
        "Biz tez yordam beramiz."
    )


def remind_7d(s: Settings) -> str:
    return (
        f"📅 <b>7 kun qoldi</b>\n\n"
        f"Obunangiz tez orada tugaydi.\n"
        f"⭐ {s.subscription_price_stars} Stars — uzluksiz hosting.\n\n"
        f"💎 Obuna → Yangilash"
    )


def remind_3d(s: Settings) -> str:
    return (
        f"🟠 <b>3 kun qoldi</b>\n\n"
        f"Bot suspend bo‘lishidan oldin renew qiling.\n"
        f"⭐ {s.subscription_price_stars} Stars / {s.subscription_days} kun"
    )


def remind_24h(s: Settings) -> str:
    return (
        f"🔴 <b>24 soat qoldi!</b>\n\n"
        f"Ertaga bot avtomatik to‘xtatiladi.\n"
        f"Hozir yangilang — hech narsa yo‘qolmasin.\n\n"
        f"⭐ {s.subscription_price_stars} Stars"
    )


def remind_expired(s: Settings) -> str:
    return (
        f"⏸ <b>Obuna tugadi — bot suspend</b>\n"
        f"{_HR}\n\n"
        f"Botingiz to‘xtatildi, lekin ma’lumotlar saqlanmoqda.\n\n"
        f"⏳ <b>7 kun</b> ichida to‘lov qilsangiz —\n"
        f"hammasi to‘liq tiklanadi.\n\n"
        f"⚠️ 7 kundan keyin bot, baza va backuplar\n"
        f"<b>butunlay o‘chiriladi</b>.\n\n"
        f"⭐ Yangilash: <b>{s.subscription_price_stars} Stars</b>"
    )


def remind_grace_daily(days_left: int) -> str:
    return (
        f"🔴 <b>Suspend</b> · o‘chirishga {days_left} kun\n\n"
        f"Hozir renew qiling — bot va ma’lumotlar qaytadi.\n"
        f"💎 Obuna bo‘limini oching."
    )


def delete_warning(username: Optional[str]) -> str:
    name = f"@{username}" if username else "bot"
    return (
        f"🗑 <b>{name} ni o‘chirish</b>\n"
        f"{_HR}\n\n"
        f"Bu amal <b>qaytarilmaydi</b>.\n\n"
        f"O‘chadi:\n"
        f"• Bot jarayoni\n"
        f"• Ma’lumotlar bazasi\n"
        f"• Fayllar va backuplar\n\n"
        f"Rostdan ham o‘chirasizmi?"
    )


def settings_text(s: Settings, lang: str) -> str:
    pay = "⭐ Stars yoqilgan" if s.payments_enabled else "🧪 Test rejim (bepul deploy)"
    return (
        f"⚙️ <b>Sozlamalar</b>\n"
        f"{_HR}\n\n"
        f"Til: <b>{lang or 'uz'}</b>\n"
        f"To‘lov: <b>{pay}</b>\n"
        f"Support: {s.support_url}\n\n"
        f"Profil va bildirishnomalar tez orada."
    )


def payment_sent(s: Settings) -> str:
    return (
        f"⭐ <b>To‘lov oynasi yuborildi</b>\n\n"
        f"Summa: <b>{s.subscription_price_stars} Stars</b>\n"
        f"Muddat: <b>{s.subscription_days} kun</b>\n\n"
        f"Telegram ichida to‘lovni tasdiqlang."
    )


def payment_ok() -> str:
    return (
        f"✅ <b>To‘lov qabul qilindi!</b>\n"
        f"{_HR}\n\n"
        f"Obuna faol.\n"
        f"Endi BotFather token yuboring —\n"
        f"botingiz avtomatik ishga tushadi."
    )


def action_ok(title: str) -> str:
    return f"✅ <b>{title}</b>"


def fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M UTC")
