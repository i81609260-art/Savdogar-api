"""Waitlist ORM model — tour to'la bo'lganda navbat."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.tour import Tour
    from app.models.user import User


class Waitlist(Base):
    """User waiting for a slot to open on a fully-booked tour."""

    __tablename__ = "waitlists"
    __table_args__ = (UniqueConstraint("user_id", "tour_id", name="uq_user_tour_waitlist"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")
    tour: Mapped["Tour"] = relationship("Tour")
