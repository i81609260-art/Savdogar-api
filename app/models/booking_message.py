"""Bron bo'yicha yozishuv — mijoz va turagentlik o'rtasida.

Suhbat HAR DOIM bitta bronga bog'langan. Bu ataylab: "umumiy chat" bo'lsa
kim kim bilan yozishayotgani va kim ko'rish huquqiga ega ekani noaniq bo'lib
qolardi. Bron esa ikkala tomonni ham (`user_id`, `company_id`) o'zida
saqlaydi, ya'ni ruxsatni tekshirish bitta so'rov bilan hal bo'ladi.

Suhbat bron yaratilgan zahoti ochiladi — tasdiqni kutmasdan. Mijozning
savoli aynan tasdiqdan OLDIN bo'ladi ("bolamga chegirma bormi?"), tasdiqdan
keyin ochilsa savol berish joyi qolmasdi.
"""

from datetime import datetime
from enum import StrEnum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageSender(StrEnum):
    """Xabarni kim yozgani.

    `user_id` ham saqlanadi, lekin rol alohida yoziladi: agentlik tomonida
    xodim almashishi mumkin, suhbat esa "mijoz ↔ agentlik" bo'lib qolishi
    kerak. Ya'ni ko'rsatishda rolga qaraladi, aniq xodimga emas.
    """

    CUSTOMER = "mijoz"
    AGENCY = "agentlik"


class BookingMessage(Base):
    """Bron ichidagi bitta xabar."""

    __tablename__ = "booking_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Ijaraviy ajratish. `booking` orqali ham topsa bo'lardi, lekin ustun
    # to'g'ridan-to'g'ri turgani muhim: har bir so'rovda JOIN qilmasdan
    # filtrlash mumkin va noto'g'ri yozilgan so'rov boshqa firmaning
    # yozishuvini qaytarib yubormaydi.
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id"), index=True, nullable=False
    )

    sender_role: Mapped[MessageSender] = mapped_column(String(20), nullable=False)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Qarshi tomon o'qigan vaqt. `None` — hali o'qilmagan.
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Suhbatni ochish — eng tez-tez bajariladigan so'rov.
        Index("ix_booking_messages_booking_created", "booking_id", "created_at"),
    )
