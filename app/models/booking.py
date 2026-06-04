"""Booking ORM model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.tour import Tour
    from app.models.tour_group import TourGroup
    from app.models.user import User


class BookingStatus(str, enum.Enum):
    """Booking lifecycle status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Booking(Base):
    """User tour booking."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id"), index=True)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tour_groups.id"), nullable=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus), default=BookingStatus.PENDING
    )
    guests_count: Mapped[int] = mapped_column(Integer, default=1)
    total_price: Mapped[float] = mapped_column(Float)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="bookings")
    tour: Mapped["Tour"] = relationship("Tour", back_populates="bookings")
    group: Mapped[Optional["TourGroup"]] = relationship("TourGroup", back_populates="bookings")
