"""Review ORM model — tur tugagandan keyin mijoz bahosi."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.tour import Tour
    from app.models.user import User


class Review(Base):
    """Post-tour review submitted by a confirmed booking user."""

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("booking_id", name="uq_booking_review"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True, unique=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1–5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")
    tour: Mapped["Tour"] = relationship("Tour")
    booking: Mapped["Booking"] = relationship("Booking")
