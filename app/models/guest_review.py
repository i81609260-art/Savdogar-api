"""Guest review — public page orqali beriladigan sharh (auth shart emas)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GuestReview(Base):
    """Quick star rating + comment from public company page visitors."""

    __tablename__ = "guest_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    guest_name: Mapped[str] = mapped_column(String(120))
    rating: Mapped[int] = mapped_column(Integer)  # 1–5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
