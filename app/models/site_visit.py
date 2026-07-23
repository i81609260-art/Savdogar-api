"""Sayt tashriflari (pageview) — dashboard uchun real tashrif hisobi.

Har bir ochilgan ommaviy sahifa bitta yozuv qoldiradi. `company_id` bo'lsa
— tur firmaning o'z sayti tashrifini alohida hisoblash mumkin; bo'sh bo'lsa
platforma umumiy sahifasi (masalan bosh sahifa).

`visitor_key` — bir kun ichida takroriy hisobni kamaytirish uchun IP + User
Agent'dan olingan qisqa xesh. Shaxsni aniqlamaydi, faqat taxminiy noyoblik.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SiteVisit(Base):
    """Bitta ommaviy sahifa tashrifi."""

    __tablename__ = "site_visits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )
    path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    visitor_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


# Sana bo'yicha tez guruhlash uchun (trend grafigi har kunni sanaydi).
Index("ix_site_visits_created_company", SiteVisit.created_at, SiteVisit.company_id)
