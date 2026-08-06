"""Telegram chatini firma xodimi bilan bog'lash va tekshirish.

Firma boti **mijozlarga** mo'ljallangan: ular tur ko'radi va bron qiladi.
Lekin ba'zi imkoniyatlar faqat xodim uchun — price-list qabul qilish,
hisobotlar. Bularni yozgan hammaga ochib qo'yish qabul qilib bo'lmaydigan
narsa: mijoz firmaning daromadini ko'rardi yoki soxta narx kiritib
agentni noto'g'ri taklif berishga majburlardi.

Shuning uchun bitta joyda, bitta qoida bo'yicha tekshiriladi.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.utils.security import verify_password


async def find_staff(
    db: AsyncSession, company_id: int, chat_id: str | int
) -> Optional[User]:
    """Shu chat shu firmaning xodimigami?

    To'rtta shart BIRGA tekshiriladi:
      * chat foydalanuvchiga bog'langan;
      * foydalanuvchi AYNAN shu firmaniki (boshqa firma xodimi emas);
      * roli ADMIN yoki OPERATOR (mijoz emas);
      * hisobi faol (ishdan bo'shatilgan emas).

    Bittasi tushib qolsa begona odam maxfiy ma'lumotga yeta olardi.
    """
    result = await db.execute(
        select(User).where(
            User.telegram_chat_id == str(chat_id),
            User.company_id == company_id,
            User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]),
            User.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def link_staff(
    db: AsyncSession, company_id: int, chat_id: str | int, text: str
) -> Optional[str]:
    """`/link email parol` — xodim o'z chatini firma botiga bog'laydi."""
    parts = text.split()
    if len(parts) < 3:
        return (
            "🔗 <b>Hisobingizni bog'lash</b>\n\n"
            "<code>/link email parol</code>\n\n"
            "Bog'langandan keyin:\n"
            "• operator price-list'larini forward qilsangiz narxlar "
            "avtomatik qo'shiladi\n"
            "• <code>/hisobot</code> — firma hisoboti"
        )

    email, password = parts[1], parts[2]
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    # Parol xato bo'lsa ham, boshqa firma xodimi bo'lsa ham, mijoz bo'lsa
    # ham — AYNI javob. Qaysi email mavjudligini oshkor qilmaslik uchun.
    if (
        user is None
        or not verify_password(password, user.hashed_password)
        or user.company_id != company_id
        or user.role not in (UserRole.ADMIN, UserRole.OPERATOR)
    ):
        return "❌ Email yoki parol noto'g'ri."

    user.telegram_chat_id = str(chat_id)
    await db.flush()
    return (
        f"✅ <b>{user.full_name}</b>, hisobingiz bog'landi.\n\n"
        "Endi mumkin:\n"
        "📄 Operator price-list'ini forward qiling — narxlar avtomatik qo'shiladi\n"
        "📊 <code>/hisobot</code> — firma hisoboti\n"
        "🆔 <code>/id</code> — Telegram ID"
    )
