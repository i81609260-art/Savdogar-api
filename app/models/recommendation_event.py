"""Tavsiya natijasi: qaysi profil qaysi turni tanladi.

Bu jadval AI'ning o'zini o'zi rivojlantirishi uchun. Tavsiya ko'rsatilgan
paytda yozuv `shown` holatida tushadi; mijoz bron qilsa `booked` bo'ladi.
Keyin ballar shu tarixga qarab sozlanadi — ya'ni tizim taxmindan emas,
HAQIQIY tanlovlardan o'rganadi.

Shaxsiy ma'lumot saqlanmaydi: faqat profil ballari va tur toifasi.
Foydalanuvchi ID ixtiyoriy va mehmon uchun bo'sh qoladi.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Mehmon ham tavsiya ola oladi, shuning uchun majburiy emas.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tour_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tours.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Profil ballari — o'lchamlar alohida ustunda, chunki ular bo'yicha
    # guruhlab o'rtacha olinadi. JSON bo'lsa har hisobda ochib chiqishga
    # to'g'ri kelardi.
    sokinlik: Mapped[float] = mapped_column(Float, default=0.5)
    yangilik: Mapped[float] = mapped_column(Float, default=0.5)
    davra: Mapped[float] = mapped_column(Float, default=0.5)
    tartib: Mapped[float] = mapped_column(Float, default=0.5)

    # Tavsiya qilingan tur toifasi (taksonomiyadan) va uning o'rni.
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # "shown" | "opened" | "booked"
    outcome: Mapped[str] = mapped_column(String(16), default="shown", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
