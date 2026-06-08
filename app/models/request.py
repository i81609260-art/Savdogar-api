"""Tour Request model — individual tur so'rovlari."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TourRequest(Base):
    """Individual tur so'rovi."""

    __tablename__ = "tour_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)

    # Lead ma'lumotlari
    lead_name: Mapped[str] = mapped_column(String(255))
    lead_phone: Mapped[str] = mapped_column(String(20))
    lead_email: Mapped[str] = mapped_column(String(255))

    # Tur parametrlari
    destination: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    group_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    group_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Sana
    start_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Mehmonxona
    hotel_rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Ovqatlanish
    meal_plan: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Tur turi
    tour_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Budjet
    budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="Yangi",
        index=True,
    )

    # Qo'shimcha
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Vaqtlar
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
