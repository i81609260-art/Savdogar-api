"""Promo code and discount management."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, Integer, String, func, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.tour import Tour


class PromoCode(Base):
    """Discount promo codes."""

    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    discount_percent: Mapped[float] = mapped_column(Float)  # 0-100
    discount_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Fixed amount
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    min_booking_amount: Mapped[float] = mapped_column(Float, default=0)  # Minimum booking amount
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Specific tours this code applies to (if empty, applies to all)
    tour_ids: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # comma-separated tour IDs
