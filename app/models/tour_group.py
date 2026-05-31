"""TourGroup ORM model — specific departure dates under a program (tour)."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.tour import Tour
    from app.models.booking import Booking


class TourGroup(Base):
    """A specific departure group under a tour program.

    Used by single-direction companies (Umra, Haj, regular flights) where
    the same program runs on multiple dates. Customers pick a date, not a package.
    """

    __tablename__ = "tour_groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    departure_date: Mapped[date] = mapped_column(Date, index=True)
    return_date: Mapped[date] = mapped_column(Date)
    hotel_stars: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    price: Mapped[float] = mapped_column(Float)
    total_slots: Mapped[int] = mapped_column(Integer, default=50)
    booked_slots: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tour: Mapped["Tour"] = relationship("Tour", back_populates="groups")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="group")

    @property
    def available_slots(self) -> int:
        return max(0, self.total_slots - self.booked_slots)

    @property
    def duration_days(self) -> int:
        return (self.return_date - self.departure_date).days
