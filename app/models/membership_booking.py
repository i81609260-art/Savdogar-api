"""Obuna (a'zolik) bronlari.

Bu jadval ilgari FAQAT xom SQL bilan yaratilardi (`db_schema.SCHEMA_PATCHES`)
va ta'rifida `INTEGER PRIMARY KEY AUTOINCREMENT` bor edi — bu SQLite'ga xos
sintaksis. Postgres uni rad etadi, xato esa `ensure_schema` dagi `try/except`
ichida jimgina yutilardi.

Natijada jadval Postgres'da UMUMAN yaratilmasdi va SQLite'dan ko'chirishda
ma'lumot jimgina tushib qolardi — migratsiya "hammasi OK" deb ko'rsatardi,
chunki u faqat IKKALA bazada bor jadvallarni solishtiradi.

Model qo'shilgani bilan `create_all` uni ikkala bazada ham to'g'ri yaratadi.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MembershipBooking(Base):
    """Sayt orqali yuborilgan obuna so'rovi."""

    __tablename__ = "membership_bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan: Mapped[str] = mapped_column(String(50))
    price: Mapped[str] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    people_count: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
